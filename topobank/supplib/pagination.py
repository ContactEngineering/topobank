from rest_framework.pagination import LimitOffsetPagination


class TopobankPaginator(LimitOffsetPagination):
    default_limit = 25
    max_limit = 100
    limit_query_param = 'limit'
    offset_query_param = 'offset'
