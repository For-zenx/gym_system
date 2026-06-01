from .permissions import has_permission

NAV_ROUTE_PRIORITY = (
    ("dashboard.view", "dashboard"),
    ("clients.view_list", "clients:client_list"),
    ("billing.view_invoices", "billing:invoice_list"),
    ("access.view_logs", "access:access_log_list"),
    ("clients.enroll", "enrollment"),
    ("plans.view", "billing:plan_list"),
)


def get_first_accessible_route(user):
    for permission_code, url_name in NAV_ROUTE_PRIORITY:
        if has_permission(user, permission_code):
            return url_name
    return None
