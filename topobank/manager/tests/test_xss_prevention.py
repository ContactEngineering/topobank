from topobank.publication.forms import SurfacePublishForm

MALICIOUS_TEXT = "<script>alert('hi')</script>"
BLEACHED_MALICIOUS_TEXT = "&lt;script&gt;alert('hi')&lt;/script&gt;"


def test_author_is_safe():
    form_data = {
        'authors_json': [{'first_name': 'Draco', 'last_name': MALICIOUS_TEXT, 'orcid_id': '', 'affiliations': []}],
        'license': 'cc0-1.0',
        'agreed': True,
        'copyright_hold': True,
    }
    form = SurfacePublishForm(data=form_data)
    assert form.is_valid()

    cleaned = form.clean()
    assert cleaned['authors_json'] == [{'first_name': 'Draco',
                                        'last_name': BLEACHED_MALICIOUS_TEXT,
                                        'orcid_id': '', 'affiliations': []}]
