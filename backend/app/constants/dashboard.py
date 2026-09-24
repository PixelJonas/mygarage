"""Dashboard constants: the orders the vehicle list can open in.

The single source of truth for backend-side validation of
``users.dashboard_sort``. Mirrors ``DASHBOARD_SORT_OPTIONS`` in the
frontend's ``src/constants/dashboardSort.ts``; keep the two in sync when adding
or removing an order.
"""

SUPPORTED_DASHBOARD_SORTS: tuple[str, ...] = ("name", "year-new", "year-old", "maintenance")

DEFAULT_DASHBOARD_SORT: str = "name"
