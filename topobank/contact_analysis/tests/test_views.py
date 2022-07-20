from django.shortcuts import reverse

from topobank.utils import assert_in_content
from topobank.manager.utils import subjects_to_json
from topobank.analysis.views import switch_card_view
from topobank.analysis.registry import AnalysisRegistry

from ..views import ContactMechanicsCardView


def test_resolve_card_view(client, example_contact_analysis):
    subjects_ids_json = subjects_to_json([example_contact_analysis.subject])

    user = example_contact_analysis.related_surface.creator

    reg = AnalysisRegistry()
    view_class = reg.get_card_view_class(
        reg.get_analysis_result_type_for_function_name(example_contact_analysis.function.name))
    assert view_class == ContactMechanicsCardView

    client.force_login(user)

    response = client.post(reverse('analysis:card'),
                           data=dict(
                               function_id=example_contact_analysis.function.id,
                               card_id="card-1",
                               template_flavor='detail',
                               subjects_ids_json=subjects_ids_json
                           ), HTTP_X_REQUESTED_WITH='XMLHttpRequest')  # we need an AJAX request

    assert_in_content(response, 'Load vs displacement')






