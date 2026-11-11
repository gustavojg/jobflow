from rest_framework.pagination import CursorPagination


class JobCursorPagination(CursorPagination):
    """Keyset pagination: O(1) per page regardless of table size, unlike OFFSET."""

    ordering = ("-created_at", "-id")
    page_size = 50
    max_page_size = 200
    page_size_query_param = "page_size"
