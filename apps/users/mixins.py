from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied

from .permissions import has_permission


class PermissionRequiredMixin(LoginRequiredMixin):
    required_permission = None
    permission_denied_message = "No tienes permiso para realizar esta acción."

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if self.required_permission and not has_permission(request.user, self.required_permission):
            raise PermissionDenied(self.permission_denied_message)
        return super().dispatch(request, *args, **kwargs)
