import factory

class OrcidSocialAccountFactory(factory.django.DjangoModelFactory):

    class Meta:
        model = "socialaccount.SocialAccount"

    user_id = 0 # overwrite on construction
    provider = 'orcid'
    uid = factory.Sequence(lambda n: "{:04d}-{:04d}-{:04d}-{:04d}".format(n,n,n,n))
    extra_data = {}

    @factory.post_generation
    def set_extra_data(self, create, value, **kwargs):
        self.extra_data = {
          'orcid-identifier': {
              'uri': 'https://orcid.org/{}'.format(self.uid),
              'path': self.uid,
              'host': 'orcid.org'
            }
        }


class UserFactory(factory.django.DjangoModelFactory):
    username = factory.Sequence(lambda n: f"user-{n}")
    email = factory.Sequence(lambda n: f"user-{n}@example.com")
    password = factory.PostGenerationMethodCall("set_password", "password")
    name = factory.Sequence(lambda n: f"name-{n}")

    class Meta:
        model = "users.User"
        django_get_or_create = ("username",)

    @factory.post_generation
    def create_orcid_account(self, create, value, **kwargs):
        OrcidSocialAccountFactory(user_id=self.id)
