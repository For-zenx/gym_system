from functools import wraps

from django.core.exceptions import PermissionDenied

from .permissions import has_permission


def permission_required(permission_code, message=None):
    denied_message = message or "No tienes permiso para realizar esta acción."

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not has_permission(request.user, permission_code):
                raise PermissionDenied(denied_message)
            return view_func(request, *args, **kwargs)

        return _wrapped_view

    return decorator
