from django.shortcuts import reverse

import pytest
from pathlib import Path
import datetime
import os.path

from .utils import FIXTURE_DIR, SurfaceFactory, TopographyFactory, UserFactory, \
    two_topos, one_line_scan, user_three_topographies_three_surfaces_three_tags
from ..models import Topography, Surface, MAX_LENGTH_DATAFILE_FORMAT
from ..forms import TopographyForm, TopographyWizardUnitsForm

from topobank.utils import assert_in_content, \
    assert_redirects, assert_no_form_errors, assert_form_error


#######################################################################
# Selections
#######################################################################

@pytest.mark.django_db
def test_empty_surface_selection(client):

    #
    # database objects
    #
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    assert surface.topography_set.count() == 0

    client.force_login(user)

    client.post(reverse('manager:surface-select', kwargs=dict(pk=surface.pk)))

    #
    # Now the selection should contain one empty surface
    #
    assert client.session['selection'] == [f'surface-{surface.pk}']




#######################################################################
# Topographies
#######################################################################

#
# Different formats are handled by PyCo
# and should be tested there in general, but
# we add some tests for formats which had problems because
# of the topobank code
#
@pytest.mark.django_db
def test_upload_topography_di(client):

    input_file_path = Path(FIXTURE_DIR + '/example3.di')  # maybe use package 'pytest-datafiles' here instead
    description = "test description"
    category = 'exp'

    user = UserFactory()

    client.force_login(user)

    # first create a surface
    response = client.post(reverse('manager:surface-create'),
                               data={
                                'name': 'surface1',
                                'creator': user.id,
                                'category': category,
                               }, follow=True)

    assert_no_form_errors(response)

    assert response.status_code == 200

    surface = Surface.objects.get(name='surface1')

    #
    # open first step of wizard: file upload
    #
    with open(str(input_file_path), mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': 'upload',
                                'upload-datafile': fp,
                                'upload-datafile_format': '',
                                'upload-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 200
    assert_no_form_errors(response)

    #
    # check contents of second page
    #

    # now we should be on the page with second step
    assert_in_content(response, "Step 2 of 3")

    # we should have two datasources as options, "ZSensor" and "Height"
    assert_in_content(response, '<option value="0">ZSensor</option>')
    assert_in_content(response, '<option value="3">Height</option>')

    assert response.context['form'].initial['name'] == 'example3.di'

    #
    # Send data for second page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                            'topography_create_wizard-current_step': 'metadata',
                            'metadata-name': 'topo1',
                            'metadata-measurement_date': '2018-06-21',
                            'metadata-data_source': 0,
                            'metadata-description': description,
                           })

    assert response.status_code == 200
    assert_no_form_errors(response)

    assert_in_content(response, "Step 3 of 3")

    #
    # Send data for third page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': 'units',
                               'units-size_x': '9000',
                               'units-size_y': '9000',
                               'units-unit': 'nm',
                               'units-height_scale': 0.3,
                               'units-detrend_mode': 'height',
                               'units-resolution_x': 256,
                               'units-resolution_y': 256,
                           }, follow=True)

    assert response.status_code == 200
    # assert reverse('manager:topography-detail', kwargs=dict(pk=1)) == response.url
    # export_reponse_as_html(response)

    assert 'form' not in response.context, "Errors:" + str(response.context['form'].errors)

    surface = Surface.objects.get(name='surface1')
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018,6,21)
    assert t.description == description
    assert "example3" in t.datafile.name
    assert 256 == t.resolution_x
    assert 256 == t.resolution_y
    assert t.creator == user
    assert t.datafile_format == 'di'

@pytest.mark.parametrize(("input_filename", "exp_datafile_format",
                          "exp_resolution_x", "exp_resolution_y",
                          "physical_sizes_to_be_set", "exp_physical_sizes"),
                         [(FIXTURE_DIR + "/10x10.txt", 'asc', 10, 10, (1, 1), (1, 1)),
                          (FIXTURE_DIR + "/line_scan_1.asc", 'xyz', 11, None, None, (9.0,)),
                          (FIXTURE_DIR + "/line_scan_1_minimal_spaces.asc", 'xyz', 11, None, None, (9.0,)),
                          (FIXTURE_DIR + "/example6.txt", 'asc', 10, None, (1.,), (1.,))])
# Add this for a larger file: ("topobank/manager/fixtures/500x500_random.txt", 500)]) # takes quire long
@pytest.mark.django_db
def test_upload_topography_txt(client, django_user_model, input_filename,
                               exp_datafile_format,
                               exp_resolution_x, exp_resolution_y,
                               physical_sizes_to_be_set, exp_physical_sizes):

    input_file_path = Path(input_filename)
    expected_toponame = input_file_path.name

    description = "test description"

    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    # first create a surface
    response = client.post(reverse('manager:surface-create'),
                               data={
                                'name': 'surface1',
                                'creator': user.id,
                                'category': 'sim'
                               }, follow=True)

    assert_no_form_errors(response)
    assert response.status_code == 200

    surface = Surface.objects.get(name='surface1')

    #
    # open first step of wizard: file upload
    #
    with input_file_path.open(mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': 'upload',
                                'upload-datafile': fp,
                                'upload-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 200
    assert_no_form_errors(response)

    #
    # check contents of second page
    #

    # now we should be on the page with second step
    assert b"Step 2 of 3" in response.content, "Errors:"+str(response.context['form'].errors)

    assert_in_content(response, '<option value="0">Default</option>')

    assert response.context['form'].initial['name'] == expected_toponame

    #
    # Send data for second page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                            'topography_create_wizard-current_step': 'metadata',
                            'metadata-name': 'topo1',
                            'metadata-measurement_date': '2018-06-21',
                            'metadata-data_source': 0,
                            'metadata-description': description,
                           })

    assert response.status_code == 200
    assert_no_form_errors(response)
    assert_in_content(response, "Step 3 of 3")

    #
    # Send data for third page
    #
    if exp_resolution_y is None:
        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                   'topography_create_wizard-current_step': "units",
                                   'units-size_editable': physical_sizes_to_be_set is not None,  # would be sent when initialize form
                                   'units-size_x': physical_sizes_to_be_set[0] if physical_sizes_to_be_set else '',
                                   'units-unit': 'nm',
                                   'units-height_scale': 1,
                                   'units-detrend_mode': 'height',
                                   'units-resolution_x': exp_resolution_x,
                               }, follow=True)
    else:
        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                   'topography_create_wizard-current_step': "units",
                                   'units-size_editable': True,  # would be sent when initialize form
                                   'units-unit_editable': True,  # would be sent when initialize form
                                   'units-size_x': physical_sizes_to_be_set[0],
                                   'units-size_y': physical_sizes_to_be_set[1],
                                   'units-unit': 'nm',
                                   'units-height_scale': 1,
                                   'units-detrend_mode': 'height',
                                   'units-resolution_x': exp_resolution_x,
                                   'units-resolution_y': exp_resolution_y,
                               }, follow=True)

    assert response.status_code == 200
    assert_no_form_errors(response)

    surface = Surface.objects.get(name='surface1')
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018,6,21)
    assert t.description == description
    assert input_file_path.stem in t.datafile.name
    assert exp_resolution_x == t.resolution_x
    assert exp_resolution_y == t.resolution_y
    assert t.datafile_format == exp_datafile_format

    #
    # Also check some properties of the PyCo Topography
    #
    pyco_t = t.topography()
    assert pyco_t.physical_sizes == exp_physical_sizes

@pytest.mark.django_db
def test_upload_topography_and_name_like_an_exisiting_for_same_surface(client):

    input_file_path = Path(FIXTURE_DIR + "/10x10.txt")

    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    TopographyFactory(surface=surface, name="TOPO")   # <-- we will try to create another topography named TOPO later

    client.force_login(user)

    # Try to create topography with same name again
    #
    # open first step of wizard: file upload
    #
    with input_file_path.open(mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': 'upload',
                                'upload-datafile': fp,
                                'upload-datafile_format': '',
                                'upload-surface': surface.id,
                               })

    assert response.status_code == 200
    assert_no_form_errors(response)

    #
    # check contents of second page
    #
    assert_in_content(response, "Step 2 of 3")

    #
    # Send data for second page, with same name as exisiting topography
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                            'topography_create_wizard-current_step': 'metadata',
                            'metadata-name': 'TOPO', # <----- already exisiting for this surface
                            'metadata-measurement_date': '2018-06-21',
                            'metadata-data_source': 0,
                            'metadata-description': "bla",
                           })

    assert response.status_code == 200
    assert_form_error(response, "A topography with same name 'TOPO' already exists for same surface", 'name')

@pytest.mark.django_db
def test_trying_upload_of_topography_file_with_unkown_format(client, django_user_model):

    input_file_path = Path(FIXTURE_DIR + '/../views.py') # this is nonsense and cannot be interpreted

    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    # first create a surface
    response = client.post(reverse('manager:surface-create'),
                               data={
                                'name': 'surface1',
                                'creator': user.id,
                                'category': 'dum',
                               }, follow=True)
    assert response.status_code == 200

    surface = Surface.objects.get(name='surface1')

    #
    # open first step of wizard: file upload
    #
    with open(str(input_file_path), mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': 'upload',
                                'upload-datafile': fp,
                                'upload-datafile_format': '',
                               })
    assert response.status_code == 200
    assert_form_error(response, 'Cannot determine file format')

@pytest.mark.django_db
def test_trying_upload_of_topography_file_with_too_long_format_name(client, django_user_model, mocker):

    import PyCo.Topography.IO

    m = mocker.patch('PyCo.Topography.IO.detect_format')
    m.return_value='a'*(MAX_LENGTH_DATAFILE_FORMAT+1)
    # this special detect_format function returns a format which is too long
    # this should result in an error message
    assert PyCo.Topography.IO.detect_format("does_not_matter_what_we_pass_here") == 'a'*(MAX_LENGTH_DATAFILE_FORMAT+1)

    input_file_path = Path(FIXTURE_DIR + '/example3.di')

    user = UserFactory()

    client.force_login(user)

    surface = SurfaceFactory(creator=user)

    #
    # open first step of wizard: file upload
    #
    with open(str(input_file_path), mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': 'upload',
                                'upload-datafile': fp,
                                'upload-datafile_format': '',
                                'upload-surface': surface.id,
                               })
    assert response.status_code == 200
    assert_form_error(response, 'Too long name for datafile format')


@pytest.mark.django_db
def test_trying_upload_of_corrupted_topography_file(client, django_user_model):

    input_file_path = Path(FIXTURE_DIR + '/example3_corrupt.di')
    # I used the correct file "example3.di" and broke it on purpose
    # The headers are still okay, but the topography can't be read by PyCo
    # using .topography() and leads to a "ValueError: buffer is smaller
    # than requested size"

    description = "test description"
    category = 'exp'

    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    # first create a surface
    response = client.post(reverse('manager:surface-create'),
                               data={
                                'name': 'surface1',
                                'creator': user.id,
                                'category': category,
                               }, follow=True)

    assert_no_form_errors(response)

    assert response.status_code == 200

    surface = Surface.objects.get(name='surface1')

    #
    # open first step of wizard: file upload
    #
    with open(str(input_file_path), mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': 'upload',
                                'upload-datafile': fp,
                                'upload-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 200

    #
    # check contents of second page
    #

    # now we should be on the page with second step
    assert b"Step 2 of 3" in response.content, "Errors:"+str(response.context['form'].errors)

    assert_in_content(response, '<option value="2">Height</option>')

    assert response.context['form'].initial['name'] == 'example3_corrupt.di'

    #
    # Send data for second page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                            'topography_create_wizard-current_step': 'metadata',
                            'metadata-name': 'topo1',
                            'metadata-measurement_date': '2018-06-21',
                            'metadata-data_source': 2,
                            'metadata-description': description,
                           })

    assert response.status_code == 200
    assert b"Step 3 of 3" in response.content, "Errors:" + str(response.context['form'].errors)

    #
    # Send data for third page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': 'units',
                               'units-size_x': '9000',
                               'units-size_y': '9000',
                               'units-unit': 'nm',
                               'units-height_scale': 0.3,
                               'units-detrend_mode': 'height',
                               'units-resolution_x': 256,
                               'units-resolution_y': 256,
                           }, follow=True)

    assert response.status_code == 200

    assert_in_content(response, 'seems to be corrupted')
    # assert_in_content(response, 'example3_corrupted.di')
    # don't know yet how to pass the filename

    #
    # Topography has not been saved
    #
    surface = Surface.objects.get(name='surface1')
    topos = surface.topography_set.all()

    assert len(topos) == 0


@pytest.mark.django_db
def test_topography_list(client, two_topos, django_user_model):

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    # response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=1)))

    #
    # all topographies for 'testuser' and surface1 should be listed
    #
    surface = Surface.objects.get(name="Surface 1", creator__username=username)
    topos = Topography.objects.filter(surface=surface)

    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)))

    content = str(response.content)
    for t in topos:
        # currently 'listed' means: name in list
        assert t.name in content

        # click on a bar should lead to details, so URL must be included
        assert reverse('manager:topography-detail', kwargs=dict(pk=t.pk)) in content

        # TODO tests missing for bar length and position (selenium??)

@pytest.fixture
def topo_example3():
    return Topography.objects.get(name='Example 3 - ZSensor')

@pytest.fixture
def topo_example4():
    return Topography.objects.get(name='Example 4 - Default')


@pytest.mark.django_db
def test_edit_topography(client, two_topos, django_user_model, topo_example3):

    new_name = "This is a better name"
    new_measurement_date = "2018-07-01"
    new_description = "New results available"

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    #
    # First get the form and look whether all the expected data is in there
    #
    response = client.get(reverse('manager:topography-update', kwargs=dict(pk=topo_example3.pk)))
    assert response.status_code == 200

    assert 'form' in response.context

    form = response.context['form']
    initial = form.initial

    assert initial['name'] == topo_example3.name
    assert initial['measurement_date'] == datetime.date(2018,1,1)
    assert initial['description'] == 'description1'
    assert initial['size_x'] == pytest.approx(10)
    assert initial['size_y'] == pytest.approx(10)
    assert pytest.approx(initial['height_scale']) == 0.29638271279074097
    assert initial['detrend_mode'] == 'height'

    #
    # Then send a post with updated data
    #
    response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo_example3.pk)),
                           data={
                            'save-stay': 1, # we want to save, but stay on page
                            'surface': topo_example3.surface.pk,
                            'data_source': 0,
                            'name': new_name,
                            'measurement_date': new_measurement_date,
                            'description': new_description,
                            'size_x': 500,
                            'size_y': 1000,
                            'unit': 'nm',
                            'height_scale': 0.1,
                            'detrend_mode': 'height',
                           }, follow=True)

    assert_no_form_errors(response)

    # we should stay on the update page for this topography
    assert_redirects(response, reverse('manager:topography-update', kwargs=dict(pk=topo_example3.pk)))

    #
    # let's check whether it has been changed
    #
    topos = Topography.objects.filter(surface=topo_example3.surface).order_by('pk')

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 7, 1)
    assert t.description == new_description
    assert t.name == new_name
    assert "example3" in t.datafile.name
    assert pytest.approx(t.size_x) == 500
    assert pytest.approx(t.size_y) == 1000

    #
    # the changed topography should also appear in the list of topographies
    #
    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=t.surface.pk)))
    assert bytes(new_name, 'utf-8') in response.content



@pytest.mark.django_db
def test_edit_line_scan(client, one_line_scan, django_user_model):

    new_name = "This is a better name"
    new_measurement_date = "2018-07-01"
    new_description = "New results available"

    username = 'testuser'
    password = 'abcd$1234'

    topo_id = one_line_scan.id
    surface_id = one_line_scan.surface.id

    assert client.login(username=username, password=password)

    #
    # First get the form and look whether all the expected data is in there
    #
    response = client.get(reverse('manager:topography-update', kwargs=dict(pk=topo_id)))
    assert response.status_code == 200

    assert 'form' in response.context

    form = response.context['form']
    initial = form.initial

    assert initial['name'] == 'Simple Line Scan'
    assert initial['measurement_date'] == datetime.date(2018,1,1)
    assert initial['description'] == 'description1'
    assert initial['size_x'] == 9
    assert pytest.approx(initial['height_scale']) == 1.
    assert initial['detrend_mode'] == 'height'
    assert 'size_y' not in form.fields # should have been removed by __init__
    assert initial['is_periodic'] == False

    #
    # Then send a post with updated data
    #
    response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo_id)),
                           data={
                            'save-stay': 1,  # we want to save, but stay on page
                            'surface': surface_id,
                            'data_source': 0,
                            'name': new_name,
                            'measurement_date': new_measurement_date,
                            'description': new_description,
                            'size_x': 500,
                            'unit': 'nm',
                            'height_scale': 0.1,
                            'detrend_mode': 'height',
                           })

    assert response.context is None, "Errors in form: {}".format(response.context['form'].errors)
    assert response.status_code == 302

    # due to the changed topography editing, we should stay on update page
    assert reverse('manager:topography-update', kwargs=dict(pk=topo_id)) == response.url

    topos = Topography.objects.filter(surface__creator__username=username).order_by('pk')

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 7, 1)
    assert t.description == new_description
    assert t.name == new_name
    assert "line_scan_1" in t.datafile.name
    assert pytest.approx(t.size_x) == 500
    assert t.size_y is None

    #
    # should also appear in the list of topographies
    #
    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=t.surface.pk)))
    assert bytes(new_name, 'utf-8') in response.content

@pytest.mark.django_db
def test_edit_topography_only_detrend_center_when_periodic(client, django_user_model):

    input_file_path = Path(FIXTURE_DIR + "/10x10.txt")
    user = UserFactory()
    surface = SurfaceFactory(creator=user)
    client.force_login(user)

    #
    # Create a topography without sizes given in original file
    #
    # Step 1
    with input_file_path.open(mode='rb') as fp:
        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                   'topography_create_wizard-current_step': 'upload',
                                   'upload-datafile': fp,
                                   'upload-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 200
    assert_no_form_errors(response)

    #
    # Step 2
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': 'metadata',
                               'metadata-name': 'topo1',
                               'metadata-measurement_date': '2019-11-22',
                               'metadata-data_source': 0,
                               'metadata-description': "only for test",
                           })

    assert response.status_code == 200
    assert_no_form_errors(response)

    #
    # Step 3
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': 'units',
                               'units-size_x': '9',
                               'units-size_y': '9',
                               'units-unit': 'nm',
                               'units-height_scale': 1,
                               'units-detrend_mode': 'height',
                               'units-resolution_x': 10,
                               'units-resolution_y': 10,
                           })

    assert response.status_code == 302

    # there should be only one topography now
    topo = Topography.objects.get(surface=surface)

    #
    # First get the form and look whether all the expected data is in there
    #
    response = client.get(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)))
    assert response.status_code == 200
    assert 'form' in response.context

    #
    # Then send a post with updated data
    #
    response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo.pk)),
                           data={
                            'save-stay': 1, # we want to save, but stay on page
                            'surface': surface.pk,
                            'data_source': 0,
                            'name': topo.name,
                            'measurement_date': topo.measurement_date,
                            'description': topo.description,
                            'size_x': 500,
                            'size_y': 1000,
                            'unit': 'nm',
                            'height_scale': 0.1,
                            'detrend_mode': 'height',
                            'is_periodic': True, # <--------- this should not be allowed with detrend_mode 'height'
                           }, follow=True)

    assert Topography.DETREND_MODE_CHOICES[0][0] == 'center'
    # this asserts that the clean() method of form has the correct reference

    assert_form_error(response, "When enabling periodicity only detrend mode", "detrend_mode")


@pytest.mark.django_db
def test_topography_detail(client, two_topos, django_user_model, topo_example4):

    username = 'testuser'
    password = 'abcd$1234'

    topo_pk = topo_example4.pk

    django_user_model.objects.get(username=username)

    assert client.login(username=username, password=password)


    response = client.get(reverse('manager:topography-detail', kwargs=dict(pk=topo_pk)))
    assert response.status_code == 200

    # resolution should be written somewhere
    assert_in_content(response, "305 x 75")

    # .. as well as Detrending mode
    assert_in_content(response, "Remove tilt")

    # .. description
    assert_in_content(response, "description2")

    # .. physical size
    assert_in_content(response, "112.80791 µm x 27.73965 µm")

@pytest.mark.django_db
def test_delete_topography(client, two_topos, django_user_model, topo_example3):

    username = 'testuser'
    password = 'abcd$1234'

    # topography 1 is still in database
    topo = topo_example3
    surface = topo.surface

    topo_datafile_path = topo.datafile.path

    assert client.login(username=username, password=password)

    response = client.get(reverse('manager:topography-delete', kwargs=dict(pk=topo.pk)))

    # user should be asked if he/she is sure
    assert b'Are you sure' in response.content

    response = client.post(reverse('manager:topography-delete', kwargs=dict(pk=topo.pk)))

    # user should be redirected to surface details
    assert reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)) == response.url

    # topography topo_id is no more in database
    assert not Topography.objects.filter(pk=topo.pk).exists()

    # topography file should also be deleted
    assert not os.path.exists(topo_datafile_path)

@pytest.mark.skip("Cannot be implemented up to now, because don't know how to reuse datafile")
@pytest.mark.django_db
def test_delete_topography_with_its_datafile_used_by_others(client, two_topos, django_user_model):

    username = 'testuser'
    password = 'abcd$1234'
    topo_id = 1

    # topography 1 is still in database
    topo = Topography.objects.get(pk=topo_id)
    surface = topo.surface

    topo_datafile_path = topo.datafile.path

    # make topography 2 use the same datafile
    topo2 = Topography.objects.get(pk=2)
    topo2.datafile.path = topo_datafile_path # This does not work

    assert client.login(username=username, password=password)

    response = client.get(reverse('manager:topography-delete', kwargs=dict(pk=topo_id)))

    # user should be asked if he/she is sure
    assert b'Are you sure' in response.content

    response = client.post(reverse('manager:topography-delete', kwargs=dict(pk=topo_id)))

    # user should be redirected to surface details
    assert reverse('manager:surface-detail', kwargs=dict(pk=surface.pk)) == response.url

    # topography topo_id is no more in database
    assert not Topography.objects.filter(pk=topo_id).exists()

    # topography file should **not** have been deleted, because still used by topo2
    assert os.path.exists(topo_datafile_path)

def test_only_positive_size_values_on_edit(client, django_user_model):

    #
    # prepare database
    #
    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    surface = SurfaceFactory(creator=user)
    topography = TopographyFactory(surface=surface, size_y=1024) # pass size_y in order to have a map

    assert client.login(username=username, password=password)

    #
    # Then send a post with negative size values
    #
    response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topography.pk)),
                           data={
                               'surface': surface.id,
                               'data_source': topography.data_source,
                               'name': topography.name,
                               'measurement_date': topography.measurement_date,
                               'description': topography.description,
                               'size_x': -500.0, # negative, should be > 0
                               'size_y': 0,  # zero, should be > 0
                               'unit': 'nm',
                               'height_scale': 0.1,
                               'detrend_mode': 'height',
                           })

    assert 'form' in response.context
    assert "Size x must be greater than zero" in response.context['form'].errors['size_x'][0]
    assert "Size y must be greater than zero" in response.context['form'].errors['size_y'][0]


#######################################################################
# Surfaces
#######################################################################

@pytest.mark.django_db
def test_create_surface(client, django_user_model):

    description = "My description. hasdhahdlahdla"
    name = "Surface 1 kjfhakfhökadsökdf"
    category = "exp"

    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    assert 0 == Surface.objects.count()

    #
    # Create first surface
    #
    response = client.post(reverse('manager:surface-create'),
                           data={
                            'name': name,
                            'creator': user.id,
                            'description': description,
                            'category': category,
                           }, follow=True)

    assert ('context' not in response) or ('form' not in response.context), "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 200

    assert description.encode() in response.content
    assert name.encode() in response.content
    assert b"Experimental data" in response.content

    assert 1 == Surface.objects.count()

@pytest.mark.django_db
def test_edit_surface(client, django_user_model):

    surface_id = 1
    username = 'testuser'
    password = 'abcd$1234'
    category = 'sim'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    surface = Surface.objects.create(id=surface_id, name="Surface 1", creator=user, category=category)
    surface.save()

    new_name = "This is a better surface name"
    new_description = "This is new description"
    new_category = 'dum'

    response = client.post(reverse('manager:surface-update', kwargs=dict(pk=surface_id)),
                           data={
                            'name': new_name,
                            'creator': user.id,
                            'description': new_description,
                            'category': new_category
                           })

    assert ('context' not in response) or ('form' not in response.context), "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 302
    assert reverse('manager:surface-detail', kwargs=dict(pk=surface_id)) == response.url

    surface = Surface.objects.get(pk=surface_id)

    assert new_name == surface.name
    assert new_description == surface.description
    assert new_category == surface.category

@pytest.mark.django_db
def test_delete_surface(client, django_user_model):

    surface_id = 1
    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    surface = Surface.objects.create(id=surface_id, name="Surface 1", creator=user)
    surface.save()

    assert Surface.objects.all().count() == 1

    response = client.get(reverse('manager:surface-delete', kwargs=dict(pk=surface_id)))

    # user should be asked if he/she is sure
    assert b'Are you sure' in response.content

    response = client.post(reverse('manager:surface-delete', kwargs=dict(pk=surface_id)))

    assert ('context' not in response) or ('form' not in response.context), "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 302
    assert reverse('manager:select') == response.url

    assert Surface.objects.all().count() == 0


def test_topography_form_field_is_periodic():

    data = {
        'size_editable': True,
        'unit_editable': True,
        'height_scale_editable': True,
        'size_x': 1,
        'unit': 'm',
        'is_periodic': False,
        'height_scale': 1,
        'detrend_mode': 'center',
        'resolution_x': '1',
    }

    form = TopographyWizardUnitsForm(initial=data, allow_periodic=False, has_size_y=False)
    assert form.fields['is_periodic'].disabled

    data['size_y'] = 1

    form = TopographyWizardUnitsForm(initial=data, allow_periodic=False, has_size_y=True)
    assert form.fields['is_periodic'].disabled

    form = TopographyWizardUnitsForm(initial=data, allow_periodic=True, has_size_y=True)
    assert not form.fields['is_periodic'].disabled

    form = TopographyForm(initial=data, has_size_y=True, allow_periodic=True, autocomplete_tags=[])
    assert not form.fields['is_periodic'].disabled

    form = TopographyForm(initial=data, has_size_y=True, allow_periodic=False, autocomplete_tags=[])
    assert form.fields['is_periodic'].disabled


@pytest.mark.django_db
def test_select_state(client, user_three_topographies_three_surfaces_three_tags):
    """
    There should be an internal state saved in each session which represents
    the settings on the "Select" tab page. These settings comprise

    - search_term
    - category
    - sharing_status
    - page_size
    - current page
    - type of view ("tag tree" or "surface list")

    similar to the selection.

    Via AJAX calls or page requests, this state can change.
    Then also the settings should change in the session such that
    on the next request for the "Select" tab page, the same settings are chosen for
    the user.
    """
    # unpack fixture data
    user, (topo1a, topo1b, topo2a), (surface1, surface2, surface3), (tag1, tag2, tag3) = \
        user_three_topographies_three_surfaces_three_tags

    client.force_login(user)

    response = client.get(reverse("manager:select"))
    assert response.status_code == 200

    assert_in_content(response, 'Previous')
    assert_in_content(response, 'Next')
    assert_in_content(response, 'Page size')
    assert_in_content(response, 'All categories')

    select_tab_state = response.context['select_tab_state']

    expected_select_tab_state = dict(
        search_term='',  # empty string means: no search
        category='all',
        sharing_status='all',
        page_size=10,
        current_page=1,
        tree_mode='surface list',
    )

    assert select_tab_state == expected_select_tab_state

    #
    # Select other values via AJAX,
    # this should be visible in the Select page's context
    #
    select_tab_state['category'] = 'exp'
    select_tab_state['sharing_status'] = 'shared'

    response = client.post(reverse("manager:save-select-state"),
                           data=select_tab_state,
                           HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request)
    assert response.status_code == 200

    response = client.get(reverse("manager:select"))
    assert response.status_code == 200
    expected_select_tab_state = select_tab_state

    select_tab_state = response.context['select_tab_state']
    assert select_tab_state == expected_select_tab_state
