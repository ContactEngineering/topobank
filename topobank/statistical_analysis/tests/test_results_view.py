import pytest

from django.shortcuts import reverse

import tempfile
import numpy as np
import openpyxl

from topobank.manager.utils import subjects_to_json
from topobank.manager.tests.utils import two_topos
from topobank.analysis.models import AnalysisFunction
from topobank.analysis.tests.utils import TopographyAnalysisFactory, Topography2DFactory
from topobank.analysis.registry import AnalysisRegistry

from ..views import RoughnessParametersCardView, NUM_SIGNIFICANT_DIGITS_RMS_VALUES

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
                                       art='roughness parameters',
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


@pytest.mark.parametrize('template_flavor', ['list', 'detail'])
@pytest.mark.django_db
def test_roughness_params_rounded(rf, mocker, template_flavor):

    def myfunc(*args, **kwargs):
        """Return some fake values for testing rounding"""
        return [
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

    m = mocker.patch('topobank.analysis.registry.AnalysisFunctionImplementation.python_function')
    m.return_value = myfunc

    topo = Topography2DFactory(size_x=1, size_y=1)

    func = AnalysisFunction.objects.get(name='Roughness parameters')
    TopographyAnalysisFactory(subject=topo, function=func)

    request = rf.post(reverse('analysis:card'), data={
        'function_id': func.id,
        'card_id': 'card',
        'template_flavor': template_flavor,
        'subjects_ids_json': subjects_to_json([topo]),
    }, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
    request.user = topo.surface.creator
    request.session = {}

    reg = AnalysisRegistry()
    card_view_class = reg.get_card_view_class(reg.get_analysis_result_type_for_function_name(func.name))

    assert card_view_class == RoughnessParametersCardView

    card_view = card_view_class.as_view()
    response = card_view(request)
    assert response.status_code == 200
    assert response.template_name == [f'statistical_analysis/roughnessparameters_card_{template_flavor}.html']

    response.render()
    # we want rounding to 5 digits
    assert NUM_SIGNIFICANT_DIGITS_RMS_VALUES == 5
    assert b"1.2346" in response.content
    assert b"8.7654" in response.content
    assert b"0.9" in response.content
    assert b"-1.5679" in response.content
    assert b"NaN" in response.content
