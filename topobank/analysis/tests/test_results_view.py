"""
Test for results view.
"""

import datetime
import openpyxl
import pickle
import tempfile
import json

import ContactMechanics
import NuMPI
import SurfaceTopography
import muFFT
import numpy as np
import pytest
from django.urls import reverse

from topobank.manager.models import Topography, Surface
from topobank.manager.utils import subjects_to_json
from topobank.manager.tests.utils import SurfaceFactory, UserFactory, \
    Topography1DFactory, Topography2DFactory, two_topos
from topobank.taskapp.tasks import current_configuration
from topobank.utils import assert_in_content, assert_not_in_content
from .utils import AnalysisFunctionFactory, AnalysisFunctionImplementationFactory, \
    TopographyAnalysisFactory, SurfaceAnalysisFactory

from ..models import Analysis, AnalysisFunction
from ..views import NUM_SIGNIFICANT_DIGITS_RMS_VALUES
from ...statistical_analysis.views import RoughnessParametersCardView


def selection_from_instances(instances):
    """A little helper for constructing a selection."""
    x = []
    for i in instances:
        prefix = i.__class__.__name__.lower()
        x.append("{}-{}".format(prefix, i.id))

    return x


def test_selection_from_instances(mocker):
    mocker.patch('topobank.manager.models.Topography')
    mocker.patch('topobank.manager.models.Surface')

    instances = [Surface(id=1, name="S1"),
                 Surface(id=2, name="S2"),
                 Topography(id=1, name="T1"),
                 Topography(id=2, name="T2"),
                 Topography(id=3, name="T3"),
                 ]

    expected = ['surface-1', 'surface-2', 'topography-1', 'topography-2', 'topography-3']

    assert expected == selection_from_instances(instances)


@pytest.mark.django_db
def test_analysis_times(client, two_topos, django_user_model, handle_usage_statistics):
    user = django_user_model.objects.get(username='testuser')
    client.force_login(user)

    topo = Topography.objects.first()
    af = AnalysisFunction.objects.first()

    result = {'name': 'test function',
              'xlabel': 'x',
              'ylabel': 'y',
              'xunit': '1',
              'yunit': '1',
              'series': [],
              }

    analysis = TopographyAnalysisFactory.create(
        subject=topo,
        function=af,
        task_state=Analysis.SUCCESS,
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),  # duration: 1 hour, 1 minute, 1 sec
        result=result,
    )
    analysis.users.add(user)
    analysis.save()

    response = client.post(reverse("analysis:card"),
                           data={
                               'subjects_ids_json': subjects_to_json([topo]),
                               'function_id': af.id,
                               'card_id': "card-1",
                               'template_flavor': 'list',
                           },
                           HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                           follow=True)

    assert response.status_code == 200

    assert_in_content(response, "2018-01-01 12:00:00")  # start_time
    assert_in_content(response, "1:01:01")  # duration


@pytest.mark.django_db
def test_show_only_last_analysis(client, two_topos, django_user_model, handle_usage_statistics):
    username = 'testuser'
    user = django_user_model.objects.get(username=username)
    client.force_login(user)

    topo1 = Topography.objects.first()
    topo2 = Topography.objects.last()
    af = AnalysisFunction.objects.first()

    result = {'name': 'test function',
              'xlabel': 'x',
              'ylabel': 'y',
              'xunit': '1',
              'yunit': '1',
              'series': [],
              }

    #
    # Topography 1
    #
    analysis = TopographyAnalysisFactory.create(
        subject=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 1, 12),
        end_time=datetime.datetime(2018, 1, 1, 13, 1, 1),
        result=result,
    )
    analysis.users.add(user)
    analysis.save()

    # save a second only, which has a later start time
    analysis = TopographyAnalysisFactory.create(
        subject=topo1,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 2, 12),
        end_time=datetime.datetime(2018, 1, 2, 13, 1, 1),
        result=result,
    )
    analysis.users.add(user)
    analysis.save()

    #
    # Topography 2
    #
    analysis = TopographyAnalysisFactory.create(
        subject=topo2,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 3, 12),
        end_time=datetime.datetime(2018, 1, 3, 13, 1, 1),
        result=result,
    )
    analysis.users.add(user)
    analysis.save()

    # save a second only, which has a later start time
    analysis = TopographyAnalysisFactory.create(
        subject=topo2,
        function=af,
        task_state=Analysis.SUCCESS,
        kwargs=pickle.dumps({}),
        start_time=datetime.datetime(2018, 1, 4, 12),
        end_time=datetime.datetime(2018, 1, 4, 13, 1, 1),
        result=result,
    )
    analysis.users.add(user)
    analysis.save()

    #
    # Check response, for both topographies only the
    # latest results should be shown
    #
    response = client.post(reverse("analysis:card"),
                           data={
                               'subjects_ids_json': subjects_to_json([topo1, topo2]),
                               'function_id': af.id,
                               'card_id': 1,
                               'template_flavor': 'list'
                           },
                           HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                           follow=True)

    assert response.status_code == 200

    assert b"2018-01-02 12:00:00" in response.content
    assert b"2018-01-04 12:00:00" in response.content

    assert b"2018-01-01 12:00:00" not in response.content
    assert b"2018-01-03 12:00:00" not in response.content


@pytest.mark.django_db
def test_warnings_for_different_arguments(client, handle_usage_statistics):
    user = UserFactory()
    surf1 = SurfaceFactory(creator=user)
    surf2 = SurfaceFactory(creator=user)
    topo1a = Topography1DFactory(surface=surf1)
    topo1b = Topography1DFactory(surface=surf1)
    topo2a = Topography1DFactory(surface=surf2)

    func = AnalysisFunctionFactory()
    topo_impl = AnalysisFunctionImplementationFactory(function=func,
                                                      subject_type=topo1a.get_content_type(),
                                                      code_ref='topography_analysis_function_for_tests')
    surf_impl = AnalysisFunctionImplementationFactory(function=func,
                                                      subject_type=surf1.get_content_type(),
                                                      code_ref='surface_analysis_function_for_tests')

    #
    # Generate analyses for topographies with differing arguments
    #
    kwargs_1a = pickle.dumps(dict(a=1, b=2))
    kwargs_1b = pickle.dumps(dict(a=1, b=3))  # differing from kwargs_1a!
    ana1a = TopographyAnalysisFactory(subject=topo1a, function=func, kwargs=kwargs_1a)
    ana1b = TopographyAnalysisFactory(subject=topo1b, function=func, kwargs=kwargs_1b)
    ana2a = TopographyAnalysisFactory(subject=topo2a, function=func)  # default arguments

    #
    # Generate analyses for surfaces with differing arguments
    #
    kwargs_1 = pickle.dumps(dict(a=1, c=2))
    kwargs_2 = pickle.dumps(dict(a=1, c=3))  # differing from kwargs_1a!
    ana1 = SurfaceAnalysisFactory(subject=surf1, function=func, kwargs=kwargs_1)
    ana2 = SurfaceAnalysisFactory(subject=surf2, function=func, kwargs=kwargs_2)

    client.force_login(user)

    #
    # request card, there should be warnings, one for topographies and one for surfaces
    #
    response = client.post(reverse("analysis:card"),
                           data={
                               'subjects_ids_json': subjects_to_json([topo1a, topo1b, topo2a, surf1, surf2]),
                               'function_id': func.id,
                               'card_id': "card-1",
                               'template_flavor': 'list'
                           },
                           HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                           follow=True)

    assert response.status_code == 200

    assert_in_content(response,
                      "Arguments for this analysis function differ among chosen "
                      "subjects of type 'manager | topography'")
    assert_in_content(response,
                      "Arguments for this analysis function differ among chosen "
                      "subjects of type 'manager | surface'")

    # arguments should be visible in output
    #
    # import html.parser
    # unescaped = html.unescape(response.content.decode())
    #
    # assert str(dict(bins=10)) in unescaped
    # assert str(dict(bins=20)) in unescaped


# Maybe the following test can be rewritten as an integration test for usage with selenium
@pytest.mark.skip("Test makes no sense, because it needs AJAX call to be executed.")
@pytest.mark.django_db
def test_show_multiple_analyses_for_two_functions(client, two_topos):
    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    topo1 = Topography.objects.first()
    topo2 = Topography.objects.last()
    af1 = AnalysisFunction.objects.first()
    af2 = AnalysisFunction.objects.last()

    assert topo1 != topo2
    assert af1 != af2

    #
    # Create analyses for two functions and two different topographies
    #
    counter = 0
    for af in [af1, af2]:
        for topo in [topo1, topo2]:
            counter += 1
            analysis = TopographyAnalysisFactory.create(
                subject=topo,
                function=af,
                task_state=Analysis.SUCCESS,
                kwargs=pickle.dumps({'bins': 10}),
                start_time=datetime.datetime(2018, 1, 1, counter),
                end_time=datetime.datetime(2018, 1, 1, counter + 1),
            )
            analysis.save()

    #
    # Select both topographies
    #
    client.post(reverse("manager:topography-select", kwargs=dict(pk=topo1.pk)))
    client.post(reverse("manager:topography-select", kwargs=dict(pk=topo2.pk)))

    #
    # Check response when selecting only first function, both analyses should be shown
    #
    response = client.post(reverse("analysis:list"),
                           data={
                               'functions': [af1.id],
                           }, follow=True)

    assert response.status_code == 200

    assert_in_content(response, "Example 3 - ZSensor")
    assert_in_content(response, "Example 4 - Default")

    #
    # Check response when selecting only both functions, both analyses should be shown
    #
    response = client.post(reverse("analysis:list"),
                           data={
                               'functions': [af1.id, af2.id],
                           }, follow=True)

    assert response.status_code == 200

    assert_in_content(response, "Example 3 - ZSensor")
    assert_in_content(response, "Example 4 - Default")


@pytest.fixture
def ids_downloadable_analyses(two_topos):
    config = current_configuration()

    #
    # create two analyses with results
    #
    topos = [Topography.objects.get(name="Example 3 - ZSensor"), Topography.objects.get(name="Example 4 - Default")]
    # function = AnalysisFunction.objects.create(name="Test Function")
    function = AnalysisFunctionFactory()
    AnalysisFunctionImplementationFactory(function=function)

    v = np.arange(5)
    ids = []

    for k in range(2):
        result = dict(
            name=f'Test Results {k}',
            scalars=dict(
                nice_value=13,
                bad_value=-99,
            ),
            xlabel='time',
            ylabel='distance',
            xunit='s',
            yunit='m',
            series=[
                dict(name='First Series',
                     x=v + k,
                     y=2 * v + k,
                     ),
                dict(name='Second Series',
                     x=v + 1 + k,
                     y=3 * (v + 1) + k,
                     )
            ])

        analysis = TopographyAnalysisFactory.create(
            subject=topos[k],
            function=function,
            result=result,
            kwargs=pickle.dumps({}),
            configuration=config)
        ids.append(analysis.id)

    return ids


@pytest.mark.django_db
def test_analysis_download_as_txt(client, two_topos, ids_downloadable_analyses, settings, handle_usage_statistics):
    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    ids_str = ",".join(str(i) for i in ids_downloadable_analyses)
    download_url = reverse('analysis:download', kwargs=dict(ids=ids_str, card_view_flavor='plot', file_format='txt'))

    response = client.get(download_url)

    from io import StringIO

    txt = response.content.decode()

    assert "Test Function" in txt  # function name should be in there

    # check whether version numbers are in there
    assert SurfaceTopography.__version__.split('+')[0] in txt
    assert ContactMechanics.__version__ in txt
    assert NuMPI.__version__ in txt
    assert muFFT.version.description() in txt
    assert settings.TOPOBANK_VERSION in txt

    # check whether creator of topography is listed
    topo1, topo2 = two_topos

    assert "Creator" in txt
    assert topo1.creator.name in txt
    assert topo1.creator.orcid_id in txt
    assert topo2.creator.name in txt
    assert topo2.creator.orcid_id in txt

    # remove comments and empty lines
    filtered_lines = []
    for line in txt.splitlines():
        line = line.strip()
        if not line.startswith('#') and len(line) > 0:
            filtered_lines.append(line)
    filtered_txt = "\n".join(filtered_lines)

    arr = np.loadtxt(StringIO(filtered_txt))

    expected_arr = np.array([
        (0, 0),
        (1, 2),
        (2, 4),
        (3, 6),
        (4, 8),
        (1, 3),
        (2, 6),
        (3, 9),
        (4, 12),
        (5, 15),
        (1, 1),
        (2, 3),
        (3, 5),
        (4, 7),
        (5, 9),
        (2, 4),
        (3, 7),
        (4, 10),
        (5, 13),
        (6, 16),
    ])

    assert arr == pytest.approx(expected_arr)


@pytest.mark.parametrize('file_format', ['txt', 'xlsx'])
@pytest.mark.django_db
def test_roughness_params_download_as_txt(client, two_topos, file_format, handle_usage_statistics):
    # This is only a simple test which checks whether the file can be downloaded
    t1, t2 = two_topos

    func = AnalysisFunction.objects.get(name='Roughness parameters')

    import pickle
    pickled_kwargs = pickle.dumps({})

    ana1 = TopographyAnalysisFactory.create(subject=t1, function=func, kwargs=pickled_kwargs)
    ana2 = TopographyAnalysisFactory.create(subject=t1, function=func, kwargs=pickled_kwargs)

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    ids_downloadable_analyses = [ana1.id, ana2.id]

    ids_str = ",".join(str(i) for i in ids_downloadable_analyses)
    download_url = reverse('analysis:download',
                           kwargs=dict(ids=ids_str,
                                       card_view_flavor='roughness parameters',
                                       file_format=file_format))

    response = client.get(download_url)

    if file_format == 'txt':
        txt = response.content.decode()

        assert "Roughness parameters" in txt  # function name should be in there
        assert "RMS height" in txt
        assert "RMS slope" in txt
        assert "RMS curvature" in txt
    else:
        # Resulting workbook should have two sheets
        tmp = tempfile.NamedTemporaryFile(suffix='.xlsx')  # will be deleted automatically
        tmp.write(response.content)
        tmp.seek(0)

        xlsx = openpyxl.load_workbook(tmp.name)

        print(xlsx.sheetnames)

        assert len(xlsx.worksheets) == 2

        ws = xlsx.get_sheet_by_name("Roughness parameters")

        all_values_list = list(np.array(list(ws.values)).flatten())

        assert 'RMS height' in all_values_list
        assert 'RMS slope' in all_values_list
        assert 'RMS curvature' in all_values_list

        xlsx.get_sheet_by_name("INFORMATION")


@pytest.mark.django_db
def test_roughness_params_rounded(rf, mocker):
    from django.core.management import call_command
    call_command('register_analysis_functions')

    m = mocker.patch('topobank.analysis.functions.roughness_parameters')
    m.return_value = [  # some fake values for rounding
        {
            'quantity': 'RMS Height',
            'direction': None,
            'from': 'area (2D)',
            'symbol': 'Sq',
            'value': np.float32(1.2345678),
            'unit': 'm',
        },
        {
            'quantity': 'RMS Height',
            'direction': 'x',
            'from': 'profile (1D)',
            'symbol': 'Rq',
            'value': np.float32(8.7654321),
            'unit': 'm',
        },
        {
            'quantity': 'RMS Curvature',
            'direction': None,
            'from': 'profile (1D)',
            'symbol': '',
            'value': np.float32(0.9),
            'unit': '1/m',
        },
        {
            'quantity': 'RMS Slope',
            'direction': 'x',
            'from': 'profile (1D)',
            'symbol': 'S&Delta;q',
            'value': np.float32(-1.56789),
            'unit': 1,
        },
        {
            'quantity': 'RMS Slope',
            'direction': 'y',
            'from': 'profile (1D)',
            'symbol': 'S&Delta;q',
            'value': np.float32('nan'),
            'unit': 1,
        }
    ]

    topo = Topography2DFactory(size_x=1, size_y=1)

    func = AnalysisFunction.objects.get(name='Roughness parameters')
    TopographyAnalysisFactory(subject=topo, function=func)

    request = rf.post(reverse('analysis:card'), data={
        'function_id': func.id,
        'card_id': 'card',
        'template_flavor': 'list',
        'subjects_ids_json': subjects_to_json([topo]),
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    request.user = topo.surface.creator
    request.session = {}

    rms_table_card_view = RoughnessParametersCardView.as_view()
    response = rms_table_card_view(request)
    assert response.status_code == 200

    response.render()
    # we want rounding to 5 digits
    assert NUM_SIGNIFICANT_DIGITS_RMS_VALUES == 5
    assert b"1.2346" in response.content
    assert b"8.7654" in response.content
    assert b"0.9" in response.content
    assert b"-1.5679" in response.content
    assert b"NaN" in response.content


@pytest.mark.parametrize("same_names", [False, True])
@pytest.mark.django_db
def test_analysis_download_as_xlsx(client, two_topos, ids_downloadable_analyses, same_names, settings,
                                   handle_usage_statistics):
    topos = Topography.objects.all()
    assert len(topos) == 2

    # if tested with "same_names=True", make sure both topographies have the same name
    if same_names:
        topos[0].name = topos[1].name
        topos[0].save()

    first_topo_name = topos[0].name
    second_topo_name = topos[1].name

    first_topo_name_in_sheet_name = first_topo_name
    second_topo_name_in_sheet_name = second_topo_name
    if same_names:
        first_topo_name_in_sheet_name += " (1)"
        second_topo_name_in_sheet_name += " (2)"

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    ids_str = ",".join(str(i) for i in ids_downloadable_analyses)
    download_url = reverse('analysis:download', kwargs=dict(ids=ids_str, card_view_flavor='plot', file_format='xlsx'))

    response = client.get(download_url)

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx')  # will be deleted automatically
    tmp.write(response.content)
    tmp.seek(0)

    xlsx = openpyxl.load_workbook(tmp.name)

    print(xlsx.sheetnames)

    assert len(xlsx.worksheets) == 1 + 1 + 2 * 2  # INDEX, META DATA, 2*2 analysis sheets

    def assert_data_equal(sheet, exp_data):
        first_data_row = 5
        last_data_col = 2
        data = np.array(list(sheet.values))[first_data_row:, :last_data_col + 1]
        np.testing.assert_equal(data, exp_data)

    assert_data_equal(xlsx.get_sheet_by_name(f"analysis-0-series-0"),
                      [
                          (None, 'time (s)', 'distance (m)'),
                          (0, 0, 0),
                          (1, 1, 2),
                          (2, 2, 4),
                          (3, 3, 6),
                          (4, 4, 8),
                      ]
                      )

    assert_data_equal(xlsx.get_sheet_by_name(f"analysis-0-series-1"),
                      [
                          (None, 'time (s)', 'distance (m)'),
                          (0, 1, 3),
                          (1, 2, 6),
                          (2, 3, 9),
                          (3, 4, 12),
                          (4, 5, 15),
                      ]
                      )

    assert_data_equal(xlsx.get_sheet_by_name(f"analysis-0-series-1"),
                      [
                          (None, 'time (s)', 'distance (m)'),
                          (0, 1, 3),
                          (1, 2, 6),
                          (2, 3, 9),
                          (3, 4, 12),
                          (4, 5, 15),
                      ]
                      )

    assert_data_equal(xlsx.get_sheet_by_name(f"analysis-1-series-0"),
                      [
                          (None, 'time (s)', 'distance (m)'),
                          (0, 1, 1),
                          (1, 2, 3),
                          (2, 3, 5),
                          (3, 4, 7),
                          (4, 5, 9),
                      ]
                      )

    assert_data_equal(xlsx.get_sheet_by_name(f"analysis-1-series-1"),
                      [
                          (None, 'time (s)', 'distance (m)'),
                          (0, 2, 4),
                          (1, 3, 7),
                          (2, 4, 10),
                          (3, 5, 13),
                          (4, 6, 16),
                      ]
                      )

    # check whether version numbers are available in INFORMATION sheet
    ws = xlsx.get_sheet_by_name("INFORMATION")

    vals = list(ws.values)

    def assert_version_in_vals(modname, version):
        assert (f"Version of '{modname}'", version) in vals

    assert_version_in_vals('SurfaceTopography', SurfaceTopography.__version__.split('+')[0])
    assert_version_in_vals('ContactMechanics', ContactMechanics.__version__)
    assert_version_in_vals('NuMPI', NuMPI.__version__)
    assert_version_in_vals('muFFT', muFFT.version.description())
    assert_version_in_vals('topobank', settings.TOPOBANK_VERSION)

    # subject names should also be included, as well as the creator
    for t in topos:
        assert ('Subject Type', 'topography') in vals
        assert ('Subject Name', t.name) in vals
        assert ('Creator', str(t.creator)) in vals

    # Check links on INDEX sheet
    ws = xlsx.get_sheet_by_name("INDEX")

    function_name = Analysis.objects.get(id=ids_downloadable_analyses[0]).function.name

    assert list(ws.values) == [
        ("Subject Name", "Subject Type", "Function Name", "Data Series", "Link"),
        (first_topo_name, "measurement", function_name,
         "First Series", "Click to jump to sheet 'analysis-0-series-0'"),
        (first_topo_name, "measurement", function_name,
         "Second Series", "Click to jump to sheet 'analysis-0-series-1'"),
        (second_topo_name, "measurement", function_name,
         "First Series", "Click to jump to sheet 'analysis-1-series-0'"),
        (second_topo_name, "measurement", function_name,
         "Second Series", "Click to jump to sheet 'analysis-1-series-1'"),
    ]

    first_link_cell = ws["E2"]
    assert first_link_cell.style == "Hyperlink"
    from openpyxl.worksheet.hyperlink import Hyperlink
    assert isinstance(first_link_cell.hyperlink, Hyperlink)


@pytest.mark.django_db
def test_analysis_download_as_xlsx_despite_slash_in_sheetname(client, two_topos, ids_downloadable_analyses,
                                                              django_user_model, handle_usage_statistics):
    topos = Topography.objects.all()
    assert len(topos) == 2

    # change topography name such that a slash is in there
    topos[0].name = "This is a slash: /"
    topos[0].save()

    #
    # download analysis data as xlsx, the slash should be replaced by "div"
    #
    user = django_user_model.objects.get(username='testuser')
    client.force_login(user)

    ids_str = ",".join(str(i) for i in ids_downloadable_analyses)
    download_url = reverse('analysis:download', kwargs=dict(ids=ids_str, card_view_flavor='plot', file_format='xlsx'))

    response = client.get(download_url)

    # if this works without error, it's okay, let's test also if the sheet can be loaded:

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx')  # will be deleted automatically
    tmp.write(response.content)
    tmp.seek(0)

    xlsx = openpyxl.load_workbook(tmp.name)

    print(xlsx.sheetnames)

    assert len(xlsx.worksheets) == 1 + 1 + 2 * 2


@pytest.mark.django_db
def test_download_analysis_results_without_permission(client, two_topos, ids_downloadable_analyses, django_user_model,
                                                      handle_usage_statistics):
    # two_topos belong to a user "testuser"
    user_2 = django_user_model.objects.create_user(username="attacker")
    client.force_login(user_2)

    ids_str = ",".join(str(i) for i in ids_downloadable_analyses)
    download_url = reverse('analysis:download', kwargs=dict(ids=ids_str, card_view_flavor='plot', file_format='txt'))

    response = client.get(download_url)
    assert response.status_code == 403  # Permission denied

    # when user_2 has view permissions for one topography of both, it's still not okay to download
    two_topos[0].surface.share(user_2)
    response = client.get(download_url)
    assert response.status_code == 403  # Permission denied

    # when user_2 has view permissions for all related surfaces, it's okay to download
    two_topos[1].surface.share(user_2)
    response = client.get(download_url)
    assert response.status_code == 200


@pytest.fixture
def two_analyses_two_publications():
    surface1 = SurfaceFactory()
    Topography1DFactory(surface=surface1)
    surface2 = SurfaceFactory()
    Topography1DFactory(surface=surface2)
    pub1 = surface1.publish('cc0-1.0', surface1.creator.name)
    pub2 = surface2.publish('cc0-1.0', surface1.creator.name + ", " + surface2.creator.name)
    pub_topo1 = pub1.surface.topography_set.first()
    pub_topo2 = pub2.surface.topography_set.first()

    func = AnalysisFunctionFactory()
    AnalysisFunctionImplementationFactory(function=func)
    analysis1 = TopographyAnalysisFactory(subject=pub_topo1, function=func)
    analysis2 = TopographyAnalysisFactory(subject=pub_topo2, function=func)

    return analysis1, analysis2, pub1, pub2


@pytest.mark.django_db
def test_publication_link_in_txt_download(client, two_analyses_two_publications, handle_usage_statistics):
    (analysis1, analysis2, pub1, pub2) = two_analyses_two_publications

    #
    # Now two publications are involved in these analyses
    #
    download_url = reverse('analysis:download', kwargs=dict(ids=f"{analysis1.id},{analysis2.id}",
                                                            card_view_flavor='plot',
                                                            file_format='txt'))
    user = UserFactory(username='testuser')
    client.force_login(user)
    response = client.get(download_url)
    assert response.status_code == 200

    txt = response.content.decode()

    assert pub1.get_absolute_url() in txt
    assert pub2.get_absolute_url() in txt


@pytest.mark.django_db
def test_publication_link_in_xlsx_download(client, two_analyses_two_publications, handle_usage_statistics):
    (analysis1, analysis2, pub1, pub2) = two_analyses_two_publications

    #
    # Now two publications are involved in these analyses
    #
    download_url = reverse('analysis:download', kwargs=dict(ids=f"{analysis1.id},{analysis2.id}",
                                                            card_view_flavor='plot',
                                                            file_format='xlsx'))
    user = UserFactory(username='testuser')
    client.force_login(user)
    response = client.get(download_url)
    assert response.status_code == 200

    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx')  # will be deleted automatically
    tmp.write(response.content)
    tmp.seek(0)

    xlsx = openpyxl.load_workbook(tmp.name)

    sheet = xlsx['INFORMATION']
    col_B = sheet['B']
    col_B_values = [str(c.value) for c in col_B]
    assert any(pub1.get_absolute_url() in v for v in col_B_values)
    assert any(pub2.get_absolute_url() in v for v in col_B_values)


@pytest.mark.django_db
def test_view_shared_analysis_results(client, handle_usage_statistics):
    password = 'abcd$1234'

    #
    # create database objects
    #
    user1 = UserFactory(password=password)
    user2 = UserFactory(password=password)

    surface1 = SurfaceFactory(creator=user1)
    surface2 = SurfaceFactory(creator=user2)

    # create topographies + functions + analyses
    func1 = AnalysisFunctionFactory()
    impl1 = AnalysisFunctionImplementationFactory(function=func1)
    # func2 = AnalysisFunctionFactory()

    # Two topographies for surface1
    topo1a = Topography1DFactory(surface=surface1, name='topo1a')
    topo1b = Topography1DFactory(surface=surface1, name='topo1b')

    # One topography for surface2
    topo2a = Topography1DFactory(surface=surface2, name='topo2a')

    # analyses, differentiate by start time
    analysis1a_1 = TopographyAnalysisFactory(subject=topo1a, function=func1,
                                             start_time=datetime.datetime(2019, 1, 1, 12))
    analysis1b_1 = TopographyAnalysisFactory(subject=topo1b, function=func1,
                                             start_time=datetime.datetime(2019, 1, 1, 13))
    analysis2a_1 = TopographyAnalysisFactory(subject=topo2a, function=func1,
                                             start_time=datetime.datetime(2019, 1, 1, 14))

    # Function should have three analyses, all successful (the default when using the factory)
    assert func1.analysis_set.count() == 3
    assert all(a.task_state == 'su' for a in func1.analysis_set.all())

    # user2 shares surfaces, so user 1 should see surface1+surface2
    surface2.share(user1)

    #
    # Now we change to the analysis card view and look what we get
    #
    assert client.login(username=user1.username, password=password)

    response = client.post(reverse("analysis:card"),
                           data={
                               'subjects_ids_json': subjects_to_json([topo1a, topo1b, topo2a]),
                               'function_id': func1.id,
                               'card_id': 1,
                               'template_flavor': 'list'
                           },
                           HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                           follow=True)

    # Function should still have three analyses, all successful (the default when using the factory)
    assert func1.analysis_set.count() == 3
    assert all(a.task_state == 'su' for a in func1.analysis_set.all())

    assert response.status_code == 200

    # We should see start times of all three topographies
    assert_in_content(response, '2019-01-01 12:00:00')  # topo1a
    assert_in_content(response, '2019-01-01 13:00:00')  # topo1b
    assert_in_content(response, '2019-01-01 14:00:00')  # topo2a

    client.logout()

    #
    # user 2 cannot access results from topo1, it is not shared
    #
    assert client.login(username=user2.username, password=password)

    response = client.post(reverse("analysis:card"),
                           data={
                               'subjects_ids_json': subjects_to_json([topo1a, topo1b, topo2a]),
                               'function_id': func1.id,
                               'card_id': 1,
                               'template_flavor': 'list'
                           },
                           HTTP_X_REQUESTED_WITH='XMLHttpRequest',
                           follow=True)

    assert response.status_code == 200

    assert_not_in_content(response, '2019-01-01 12:00:00')  # topo1a
    assert_not_in_content(response, '2019-01-01 13:00:00')  # topo1b
    assert_in_content(response, '2019-01-01 14:00:00')  # topo2a

    client.logout()
