
import pytest
from django.shortcuts import reverse

from pathlib import Path
import datetime
import os.path

# from topobank.manager.tests.utils import export_reponse_as_html
from ..tests.utils import two_topos
from ..models import Topography, Surface

#
# Different formats are handled by PyCo
# and should be tested there in general, but
# we add some tests for formats which had problems because
# of the topobank code
#
@pytest.mark.django_db
def test_upload_topography_di(client, django_user_model):

    input_file_path = Path('topobank/manager/fixtures/example3.di') # TODO use standardized way to find files
    description = "test description"

    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    # first create a surface
    response = client.post(reverse('manager:surface-create'),
                               data={
                                'name': 'surface1',
                                'user': user.id,
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
                                'topography_create_wizard-current_step': '0',
                                '0-datafile': fp,
                                '0-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 200

    #
    # check contents of second page
    #

    # now we should be on the page with second step
    assert b"Step 2 of 3" in response.content, "Errors:"+str(response.context['form'].errors)

    # we should have two datasources as options, "ZSensor" and "Height"

    assert b'<option value="0">ZSensor</option>' in response.content
    assert b'<option value="1">Height</option>' in response.content

    assert response.context['form'].initial['name'] == 'example3.di'

    #
    # Send data for second page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                            'topography_create_wizard-current_step': '1',
                            '1-name': 'topo1',
                            '1-measurement_date': '2018-06-21',
                            '1-data_source': 0,
                            '1-description': description,
                           })

    assert response.status_code == 200
    assert b"Step 3 of 3" in response.content, "Errors:" + str(response.context['form'].errors)

    #
    # Send data for third page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': '2',
                               '2-size_x': '9000',
                               '2-size_y': '9000',
                               '2-size_unit': 'nm',
                               '2-height_scale': 0.3,
                               '2-height_unit': 'nm',
                               '2-detrend_mode': 'height',
                               '2-resolution_x': 256,
                               '2-resolution_y': 256,
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

@pytest.mark.parametrize(("input_filename", "exp_resolution_x", "exp_resolution_y"),
                         [("topobank/manager/fixtures/10x10.txt", 10, 10),
                          ("topobank/manager/fixtures/line_scan_1.asc", 11, None),
                          ("topobank/manager/fixtures/line_scan_1_minimal_spaces.asc", 11, None)])
# Add this for a larger file: ("topobank/manager/fixtures/500x500_random.txt", 500)]) # takes quire long
@pytest.mark.django_db
def test_upload_topography_txt(client, django_user_model, input_filename,
                               exp_resolution_x, exp_resolution_y):

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
                                'user': user.id,
                               }, follow=True)
    assert response.status_code == 200

    surface = Surface.objects.get(name='surface1')

    #
    # open first step of wizard: file upload
    #
    with input_file_path.open(mode='rb') as fp:

        response = client.post(reverse('manager:topography-create',
                                       kwargs=dict(surface_id=surface.id)),
                               data={
                                'topography_create_wizard-current_step': '0',
                                '0-datafile': fp,
                                '0-surface': surface.id,
                               }, follow=True)

    assert response.status_code == 200

    #
    # check contents of second page
    #

    # now we should be on the page with second step
    assert b"Step 2 of 3" in response.content, "Errors:"+str(response.context['form'].errors)

    # we should have two datasources as options, "ZSensor" and "Height"

    assert b'<option value="0">Default</option>' in response.content

    assert response.context['form'].initial['name'] == expected_toponame

    #
    # Send data for second page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                            'topography_create_wizard-current_step': '1',
                            '1-name': 'topo1',
                            '1-measurement_date': '2018-06-21',
                            '1-data_source': 0,
                            '1-description': description,
                           })

    assert response.status_code == 200
    assert b"Step 3 of 3" in response.content, "Errors:" + str(response.context['form'].errors)

    #
    # Send data for third page
    #
    response = client.post(reverse('manager:topography-create',
                                   kwargs=dict(surface_id=surface.id)),
                           data={
                               'topography_create_wizard-current_step': '2',
                               '2-size_x': '1',
                               '2-size_y': '' if exp_resolution_y is None else '1', # No y size for line scans
                               '2-size_unit': 'nm',
                               '2-height_scale': 1,
                               '2-height_unit': 'nm',
                               '2-detrend_mode': 'height',
                               '2-resolution_x': exp_resolution_x,
                               '2-resolution_y': exp_resolution_y or '', # empty string if NULL expected
                           }, follow=True)

    assert response.status_code == 200

    # there is no form, if there is a form, it probably shows an error
    assert 'form' not in response.context, "Errors:" + str(response.context['form'].errors)

    surface = Surface.objects.get(name='surface1')
    topos = surface.topography_set.all()

    assert len(topos) == 1

    t = topos[0]

    assert t.measurement_date == datetime.date(2018,6,21)
    assert t.description == description
    assert input_file_path.stem in t.datafile.name
    assert exp_resolution_x == t.resolution_x
    assert exp_resolution_y == t.resolution_y


@pytest.mark.django_db
def test_trying_upload_of_invalid_topography_file(client, django_user_model):

    # input_file_path = Path('../../../PyCo-web/PyCo_app/data/gain_control_uncd_dlc_4.004')
    input_file_path = Path('topobank/manager/fixtures/two_topographies.yaml')
    description = "invalid file"

    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    # first create a surface
    response = client.post(reverse('manager:surface-create'),
                               data={
                                'name': 'surface1',
                                'user': user.id,
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
                                'topography_create_wizard-current_step': '0',
                                '0-datafile': fp,
                               })
    assert response.status_code == 200

    form = response.context['form']
    assert 'Error while reading file contents' in form.errors['datafile'][0]

@pytest.mark.django_db
def test_topography_list(client, two_topos, django_user_model):

    username = 'testuser'
    password = 'abcd$1234'

    assert client.login(username=username, password=password)

    # response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=1)))

    #
    # all topographies for 'testuser' and surface1 should be listed
    #
    topos = Topography.objects.filter(surface__user__username=username)

    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=1)))

    content = str(response.content)
    for t in topos:
        # currently 'listed' means: name in list
        assert t.name in content

        # click on a bar should lead to details, so URL must be included
        assert reverse('manager:topography-detail', kwargs=dict(pk=t.pk)) in content

        # TODO tests missing for bar length and position (selenium??)

# TODO add test with predefined height conversion
# TODO add test with predefined physical size


@pytest.mark.django_db
def test_edit_topography(client, two_topos, django_user_model):

    new_name = "This is a better name"
    new_measurement_date = "2018-07-01"
    new_description = "New results available"
    #input_file_path = Topography.objects.get(pk=1).datafile.name

    username = 'testuser'
    password = 'abcd$1234'

    topo_id = 1

    user = django_user_model.objects.get(username=username)

    assert client.login(username=username, password=password)

    #with open(str(input_file_path)) as fp:

    response = client.post(reverse('manager:topography-update', kwargs=dict(pk=topo_id)),
                           data={
                            'surface': 1,
                            'data_source': 0,
                            'name': new_name,
                            'measurement_date': new_measurement_date,
                            'description': new_description,
                            'size_x': 500,
                            'size_y': 1000,
                            'size_unit': 'nm',
                            'height_scale': 0.1,
                            'height_unit': 'nm',
                            'detrend_mode': 'height',
                           })


    # assert 'form' not in response.context, "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 302
    assert reverse('manager:topography-detail', kwargs=dict(pk=topo_id)) == response.url

    # export_reponse_as_html(response) # TODO remove, only for debugging

    topos = Topography.objects.filter(surface__user__username=username).order_by('pk')

    assert len(topos) == 2

    t = topos[0]

    assert t.measurement_date == datetime.date(2018, 7, 1)
    assert t.description == new_description
    assert "example3" in t.datafile.name

    #
    # should also appear in the list of topographies
    #
    response = client.get(reverse('manager:surface-detail', kwargs=dict(pk=topo_id)))
    assert bytes(new_name, 'utf-8') in response.content

@pytest.mark.django_db
def test_topography_detail(client, two_topos, django_user_model):

    username = 'testuser'
    password = 'abcd$1234'

    topo_id = 2

    django_user_model.objects.get(username=username)

    assert client.login(username=username, password=password)


    response = client.get(reverse('manager:topography-detail', kwargs=dict(pk=topo_id)))
    assert response.status_code == 200

    # resolution should be written somewhere
    assert b"305 x 75" in response.content

    # .. as well as Detrending mode
    assert b"Remove tilt" in response.content

    # .. description
    assert b"description2" in response.content

    # .. physical size
    assert "112 µm x 27 µm" in response.content.decode('utf-8')




@pytest.mark.django_db
def test_delete_topography(client, two_topos, django_user_model):

    username = 'testuser'
    password = 'abcd$1234'
    topo_id = 1

    # topography 1 is still in database
    topo = Topography.objects.get(pk=topo_id)
    surface = topo.surface

    topo_datafile_path = topo.datafile.path

    assert client.login(username=username, password=password)

    response = client.get(reverse('manager:topography-delete', kwargs=dict(pk=topo_id)))

    # user should be asked if he/she is sure
    assert b'Are you sure' in response.content

    response = client.post(reverse('manager:topography-delete', kwargs=dict(pk=topo_id)))

    # user should be redirected to surface details
    assert reverse('manager:surface-detail', kwargs=dict(pk=surface.id)) == response.url

    # topography topo_id is no more in database
    assert not Topography.objects.filter(pk=topo_id).exists()

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
    assert reverse('manager:surface-detail', kwargs=dict(pk=surface.id)) == response.url

    # topography topo_id is no more in database
    assert not Topography.objects.filter(pk=topo_id).exists()

    # topography file should **not** have been deleted, because still used by topo2
    assert os.path.exists(topo_datafile_path)

@pytest.mark.django_db
def test_create_surface(client, django_user_model):

    description = "My description. hasdhahdlahdla"
    name = "Surface 1 kjfhakfhökadsökdf"

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
                            'user': user.id,
                            'description': description,
                           }, follow=True)

    assert ('context' not in response) or ('form' not in response.context), "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 200

    assert description.encode() in response.content
    assert name.encode() in response.content


@pytest.mark.django_db
def test_edit_surface(client, django_user_model):

    surface_id = 1
    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    surface = Surface.objects.create(id=surface_id, name="Surface 1", user=user)
    surface.save()

    new_name = "This is a better surface name"
    new_description = "This is new description"

    response = client.post(reverse('manager:surface-update', kwargs=dict(pk=surface_id)),
                           data={
                            'name': new_name,
                            'user': user.id,
                            'description': new_description,
                           })

    assert ('context' not in response) or ('form' not in response.context), "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 302
    assert reverse('manager:surface-detail', kwargs=dict(pk=surface_id)) == response.url

    surface = Surface.objects.get(pk=surface_id)

    assert new_name == surface.name
    assert new_description == surface.description

@pytest.mark.django_db
def test_delete_surface(client, django_user_model):

    surface_id = 1
    username = 'testuser'
    password = 'abcd$1234'

    user = django_user_model.objects.create_user(username=username, password=password)

    assert client.login(username=username, password=password)

    surface = Surface.objects.create(id=surface_id, name="Surface 1", user=user)
    surface.save()

    assert Surface.objects.all().count() == 1

    response = client.get(reverse('manager:surface-delete', kwargs=dict(pk=surface_id)))

    # user should be asked if he/she is sure
    assert b'Are you sure' in response.content

    response = client.post(reverse('manager:surface-delete', kwargs=dict(pk=surface_id)))

    assert ('context' not in response) or ('form' not in response.context), "Still on form: {}".format(response.context['form'].errors)

    assert response.status_code == 302
    assert reverse('manager:surface-list') == response.url

    assert Surface.objects.all().count() == 0



