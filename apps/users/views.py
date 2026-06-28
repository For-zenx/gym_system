import json

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View
from django.views.generic import ListView, TemplateView

from .forms_helpers import build_granted_permission_groups, build_permission_groups, permissions_from_post
from .mixins import PermissionRequiredMixin
from .models import StaffRole
from .permissions import has_permission
from apps.billing.models import BillingSettings, ReportEmailSettings
from apps.billing.services import update_late_fee_amount_usd, update_fixed_grace_days, update_report_recipient_email
from .services import (
    create_staff_role,
    create_staff_user,
    delete_staff_role,
    get_or_create_staff_profile,
    update_staff_profile_self,
    update_staff_role,
    update_staff_user,
)

User = get_user_model()


class AnyPermissionRequiredMixin(LoginRequiredMixin):
    required_any_permissions = ()
    permission_denied_message = "No tienes permiso para acceder a la configuración."

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if any(has_permission(request.user, code) for code in self.required_any_permissions):
            return super().dispatch(request, *args, **kwargs)
        raise PermissionDenied(self.permission_denied_message)


def _roles_presets_context():
    roles = StaffRole.objects.all().order_by("name")
    presets = {str(role.pk): role.permissions or [] for role in roles}
    return roles, presets


class StaffProfileView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        profile = getattr(user, "staff_profile", None)
        if profile is None and not user.is_superuser:
            profile = get_or_create_staff_profile(user)

        can_edit = has_permission(user, "users.edit")
        form_display_name = ""
        if profile:
            form_display_name = profile.display_name
        elif user.is_superuser:
            form_display_name = user.get_full_name() or user.username

        return render(
            request,
            "users/staff_profile.html",
            {
                "staff_profile": profile,
                "permission_groups": build_granted_permission_groups(user),
                "can_edit_profile": can_edit and profile is not None,
                "form_display_name": form_display_name,
            },
        )

    def post(self, request):
        if not has_permission(request.user, "users.edit"):
            raise PermissionDenied("No tienes permiso para editar tu perfil.")

        profile = getattr(request.user, "staff_profile", None)
        if profile is None:
            messages.error(request, "Tu cuenta no tiene perfil operativo.")
            return redirect("staff_profile")

        try:
            update_staff_profile_self(
                request.user,
                display_name=request.POST.get("display_name"),
            )
            messages.success(request, "Perfil actualizado correctamente.")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)

        return redirect("staff_profile")


class ConfigHomeView(AnyPermissionRequiredMixin, TemplateView):
    required_any_permissions = ("users.view", "roles.manage", "settings.billing", "settings.grace", "settings.reports")
    template_name = "users/config_home.html"


class BillingSettingsView(PermissionRequiredMixin, View):
    required_permission = "settings.billing"

    def get(self, request):
        settings_obj = BillingSettings.get_settings()
        return render(
            request,
            "users/billing_settings.html",
            {
                "multa_monto_usd": settings_obj.multa_monto_usd,
                "updated_at": settings_obj.updated_at,
            },
        )

    def post(self, request):
        try:
            update_late_fee_amount_usd(request.POST.get("multa_monto_usd"))
            messages.success(request, "Monto de multa actualizado correctamente.")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        return redirect("users:billing_settings")


class GraceSettingsView(PermissionRequiredMixin, View):
    required_permission = "settings.grace"

    def get(self, request):
        settings_obj = BillingSettings.get_settings()
        return render(
            request,
            "users/grace_settings.html",
            {
                "fixed_grace_days": settings_obj.fixed_grace_days,
                "updated_at": settings_obj.updated_at,
            },
        )

    def post(self, request):
        try:
            update_fixed_grace_days(request.POST.get("fixed_grace_days"))
            messages.success(request, "Días de gracia actualizados correctamente.")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        return redirect("users:grace_settings")


class ReportEmailSettingsView(PermissionRequiredMixin, View):
    required_permission = "settings.reports"

    def get(self, request):
        settings_obj = ReportEmailSettings.get_settings()
        return render(
            request,
            "users/report_settings.html",
            {
                "recipient_email": settings_obj.recipient_email,
                "updated_at": settings_obj.updated_at,
                "daily_send_limit": settings_obj.daily_send_limit,
            },
        )

    def post(self, request):
        try:
            update_report_recipient_email(request.POST.get("recipient_email"))
            messages.success(request, "Correo de reportes actualizado correctamente.")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        return redirect("users:report_settings")


class RoleListView(PermissionRequiredMixin, ListView):
    required_permission = "roles.manage"
    model = StaffRole
    template_name = "users/role_list.html"
    context_object_name = "roles"


class RoleCreateView(PermissionRequiredMixin, View):
    required_permission = "roles.manage"

    def get(self, request):
        roles, presets = _roles_presets_context()
        return render(
            request,
            "users/role_form.html",
            {
                "form_title": "Nueva plantilla",
                "permission_groups": build_permission_groups(),
                "roles": roles,
                "roles_presets_json": json.dumps(presets),
                "is_edit": False,
            },
        )

    def post(self, request):
        try:
            create_staff_role(
                request.POST.get("name"),
                request.POST.get("description"),
                permissions_from_post(request.POST),
            )
            messages.success(request, "Plantilla creada correctamente.")
            return redirect("users:role_list")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            roles, presets = _roles_presets_context()
            return render(
                request,
                "users/role_form.html",
                {
                    "form_title": "Nueva plantilla",
                    "permission_groups": build_permission_groups(permissions_from_post(request.POST)),
                    "roles": roles,
                    "roles_presets_json": json.dumps(presets),
                    "is_edit": False,
                    "form_name": request.POST.get("name", ""),
                    "form_description": request.POST.get("description", ""),
                },
            )


class RoleUpdateView(PermissionRequiredMixin, View):
    required_permission = "roles.manage"

    def get(self, request, pk):
        role = get_object_or_404(StaffRole, pk=pk)
        roles, presets = _roles_presets_context()
        return render(
            request,
            "users/role_form.html",
            {
                "form_title": "Editar plantilla",
                "role": role,
                "permission_groups": build_permission_groups(role.permissions or []),
                "roles": roles,
                "roles_presets_json": json.dumps(presets),
                "is_edit": True,
                "form_name": role.name,
                "form_description": role.description,
            },
        )

    def post(self, request, pk):
        role = get_object_or_404(StaffRole, pk=pk)
        try:
            update_staff_role(
                role,
                name=request.POST.get("name"),
                description=request.POST.get("description"),
                permissions=permissions_from_post(request.POST),
            )
            messages.success(request, "Plantilla actualizada correctamente.")
            return redirect("users:role_list")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            roles, presets = _roles_presets_context()
            return render(
                request,
                "users/role_form.html",
                {
                    "form_title": "Editar plantilla",
                    "role": role,
                    "permission_groups": build_permission_groups(permissions_from_post(request.POST)),
                    "roles": roles,
                    "roles_presets_json": json.dumps(presets),
                    "is_edit": True,
                    "form_name": request.POST.get("name", ""),
                    "form_description": request.POST.get("description", ""),
                },
            )


class RoleDeleteView(PermissionRequiredMixin, View):
    required_permission = "roles.manage"

    def post(self, request, pk):
        role = get_object_or_404(StaffRole, pk=pk)
        try:
            delete_staff_role(role)
            messages.success(request, "Plantilla eliminada correctamente.")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        return redirect("users:role_list")


class StaffUserListView(PermissionRequiredMixin, ListView):
    required_permission = "users.view"
    template_name = "users/staff_user_list.html"
    context_object_name = "staff_users"
    paginate_by = 20

    def get_queryset(self):
        return (
            User.objects.filter(is_superuser=False)
            .select_related("staff_profile", "staff_profile__created_from_role")
            .order_by("username")
        )


class StaffUserCreateView(PermissionRequiredMixin, View):
    required_permission = "users.create"

    def get(self, request):
        roles, presets = _roles_presets_context()
        selected = []
        template_id = request.GET.get("plantilla")
        if template_id:
            role = roles.filter(pk=template_id).first()
            if role:
                selected = role.permissions or []
        return render(
            request,
            "users/staff_user_form.html",
            {
                "form_title": "Nuevo usuario",
                "permission_groups": build_permission_groups(selected),
                "roles": roles,
                "roles_presets_json": json.dumps(presets),
                "selected_template_id": template_id or "",
                "is_edit": False,
            },
        )

    def post(self, request):
        roles, presets = _roles_presets_context()
        template_role = None
        template_id = request.POST.get("template_role")
        if template_id:
            template_role = roles.filter(pk=template_id).first()

        password = request.POST.get("password", "")
        password_confirm = request.POST.get("password_confirm", "")
        if password != password_confirm:
            messages.error(request, "Las contraseñas no coinciden.")
            return self._render_form_error(request, roles, presets, permissions_from_post(request.POST))

        try:
            create_staff_user(
                username=request.POST.get("username"),
                password=password,
                display_name=request.POST.get("display_name"),
                permissions=permissions_from_post(request.POST),
                template_role=template_role,
                is_active=request.POST.get("is_active") == "on",
            )
            messages.success(request, "Usuario creado correctamente.")
            return redirect("users:staff_user_list")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return self._render_form_error(
                request,
                roles,
                presets,
                permissions_from_post(request.POST),
            )

    def _render_form_error(self, request, roles, presets, selected_permissions):
        return render(
            request,
            "users/staff_user_form.html",
            {
                "form_title": "Nuevo usuario",
                "permission_groups": build_permission_groups(selected_permissions),
                "roles": roles,
                "roles_presets_json": json.dumps(presets),
                "selected_template_id": request.POST.get("template_role", ""),
                "is_edit": False,
                "form_username": request.POST.get("username", ""),
                "form_display_name": request.POST.get("display_name", ""),
                "form_is_active": request.POST.get("is_active") == "on",
            },
        )


class StaffUserUpdateView(PermissionRequiredMixin, View):
    required_permission = "users.edit"

    def get(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_superuser=False)
        profile = getattr(user, "staff_profile", None)
        if profile is None:
            messages.error(request, "Este usuario no tiene perfil operativo.")
            return redirect("users:staff_user_list")

        roles, presets = _roles_presets_context()
        return render(
            request,
            "users/staff_user_form.html",
            {
                "form_title": "Editar usuario",
                "staff_user": user,
                "staff_profile": profile,
                "permission_groups": build_permission_groups(profile.permissions or []),
                "roles": roles,
                "roles_presets_json": json.dumps(presets),
                "selected_template_id": str(profile.created_from_role_id or ""),
                "is_edit": True,
                "form_display_name": profile.display_name,
                "form_is_active": user.is_active,
            },
        )

    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk, is_superuser=False)
        roles, presets = _roles_presets_context()
        template_role = None
        template_id = request.POST.get("template_role")
        if template_id:
            template_role = roles.filter(pk=template_id).first()

        reset_from_template = request.POST.get("reset_from_template") == "1"
        if reset_from_template and not template_role:
            messages.error(request, "Selecciona una plantilla para restablecer los permisos.")
            return self._render_form_error(
                request,
                user,
                roles,
                presets,
                permissions_from_post(request.POST),
            )

        permissions = None if reset_from_template and template_role else permissions_from_post(request.POST)

        password = request.POST.get("password", "").strip()
        password_confirm = request.POST.get("password_confirm", "").strip()
        if password or password_confirm:
            if password != password_confirm:
                messages.error(request, "Las contraseñas no coinciden.")
                return self._render_form_error(request, user, roles, presets, permissions_from_post(request.POST))

        try:
            update_staff_user(
                user,
                display_name=request.POST.get("display_name"),
                password=password or None,
                permissions=permissions,
                template_role=template_role if reset_from_template and template_role else None,
                is_active=request.POST.get("is_active") == "on",
                acting_user=request.user,
            )
            messages.success(request, "Usuario actualizado correctamente.")
            return redirect("users:staff_user_list")
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
            return self._render_form_error(
                request,
                user,
                roles,
                presets,
                permissions_from_post(request.POST),
            )

    def _render_form_error(self, request, user, roles, presets, selected_permissions):
        profile = getattr(user, "staff_profile", None)
        return render(
            request,
            "users/staff_user_form.html",
            {
                "form_title": "Editar usuario",
                "staff_user": user,
                "staff_profile": profile,
                "permission_groups": build_permission_groups(selected_permissions),
                "roles": roles,
                "roles_presets_json": json.dumps(presets),
                "selected_template_id": request.POST.get("template_role", ""),
                "is_edit": True,
                "form_display_name": request.POST.get("display_name", ""),
                "form_is_active": request.POST.get("is_active") == "on",
            },
        )
