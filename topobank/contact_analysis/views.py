import itertools
import json

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import reverse

from topobank.analysis.registry import register_card_view_class
from topobank.analysis.views import SimpleCardView
from topobank.analysis.utils import filter_and_order_analyses, palette_for_topographies
from topobank.manager.models import Topography
from topobank.analysis.models import AnalysisFunction


@register_card_view_class('contact mechanics')
class ContactMechanicsCardView(SimpleCardView):
    """View for displaying a card with results from Contact Mechanics analyses.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        alerts = []  # list of collected alerts
        analyses_success = context['analyses_success']

        if len(analyses_success) > 0:

            data_sources_dict = []

            analyses_success = filter_and_order_analyses(analyses_success)

            #
            # Prepare colors to be used for different analyses
            #
            color_cycle = itertools.cycle(palette_for_topographies(len(analyses_success)))

            #
            # Context information for the figure
            #
            context.update(dict(
                output_backend=settings.BOKEH_OUTPUT_BACKEND))

            #
            # Generate two plots in two tabs based on same data sources
            #
            for a_index, analysis in enumerate(analyses_success):
                curr_color = next(color_cycle)

                subject_name = analysis.subject.name

                #
                # Context information for this data source
                #
                data_sources_dict += [dict(
                    source_name=f'analysis-{analysis.id}',
                    subject_name=subject_name,
                    subject_name_index=a_index,
                    url=reverse('analysis:data', args=(analysis.pk, 'result.json')),
                    showSymbols=True,  # otherwise symbols do not appear in legend
                    color=curr_color,
                    width=1.,
                )]

            context['data_sources'] = json.dumps(data_sources_dict)

        #
        # Calculate initial values for the parameter form on the page
        # We only handle topographies here so far, so we only take into account
        # parameters for topography analyses
        #
        topography_ct = ContentType.objects.get_for_model(Topography)
        try:
            unique_kwargs = context['unique_kwargs'][topography_ct]
        except KeyError:
            unique_kwargs = None
        if unique_kwargs:
            initial_calc_kwargs = unique_kwargs
        else:
            # default initial arguments for form if we don't have unique common arguments
            contact_mechanics_func = AnalysisFunction.objects.get(name="Contact mechanics")
            initial_calc_kwargs = contact_mechanics_func.get_default_kwargs(topography_ct)
            initial_calc_kwargs['substrate_str'] = 'nonperiodic'  # because most topographies are non-periodic

        context['initial_calc_kwargs'] = initial_calc_kwargs

        context['extra_warnings'] = alerts
        context['extra_warnings'].append(
            dict(alert_class='alert-warning',
                 message="""
                 Translucent data points did not converge within iteration limit and may carry large errors.
                 <i>A</i> is the true contact area and <i>A0</i> the apparent contact area,
                 i.e. the size of the provided measurement.""")
        )

        context['limits_calc_kwargs'] = settings.CONTACT_MECHANICS_KWARGS_LIMITS

        return context

