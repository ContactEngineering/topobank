from rest_framework.pagination import PageNumberPagination


class TopobankPaginator(PageNumberPagination):
    page_size = 25
    page_query_param = 'page'
    page_size_query_param = 'count'
    max_page_size = 100
