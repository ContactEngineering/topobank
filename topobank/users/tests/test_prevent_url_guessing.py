
from django.urls import reverse

def test_prevent_username_guessing(client, django_user_model):

    django_user_model.objects.create_user(username='testuser1', password="abcd$1234")
    django_user_model.objects.create_user(username='testuser2', password="abcd$5678")

    assert client.login(username='testuser1', password='abcd$1234')

    response = client.get(reverse('users:detail', kwargs={'username': 'testuser1'}))  # same user
    assert response.status_code == 200

    response = client.get(reverse('users:detail', kwargs={'username': 'testuser2'})) # other user!!
    assert response.status_code == 403 # Forbidden





