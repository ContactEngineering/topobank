from trackstats.models import Metric, Period

from .utils import increase_statistics_by_date


def count_request_middleware(get_response):
    """We want to count every request of the web site.
    """

    def middleware(request):
        # count this request for statistics
        metric = Metric.objects.TOTAL_REQUEST_COUNT
        increase_statistics_by_date(metric, period=Period.DAY)

        response = get_response(request)

        return response

    return middleware
