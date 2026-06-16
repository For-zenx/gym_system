from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, ListView, UpdateView

from apps.users.mixins import PermissionRequiredMixin

from .models import Locker
from .services import expire_overdue_rentals, get_current_rental_for_locker, release_locker


class LockerListView(PermissionRequiredMixin, ListView):
    required_permission = "lockers.view"
    model = Locker
    template_name = "lockers/locker_list.html"
    context_object_name = "lockers"

    def get_queryset(self):
        expire_overdue_rentals()
        return Locker.objects.all().order_by("number", "id")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        for locker in context["lockers"]:
            locker.current_rental = get_current_rental_for_locker(locker)
        return context


class LockerCreateView(PermissionRequiredMixin, CreateView):
    required_permission = "lockers.manage"
    model = Locker
    template_name = "lockers/locker_form.html"
    fields = ["number", "status", "notes"]
    success_url = reverse_lazy("lockers:locker_list")

    def form_valid(self, form):
        messages.success(self.request, "Casillero registrado correctamente.")
        return super().form_valid(form)


class LockerUpdateView(PermissionRequiredMixin, UpdateView):
    required_permission = "lockers.manage"
    model = Locker
    template_name = "lockers/locker_form.html"
    fields = ["number", "status", "notes"]
    success_url = reverse_lazy("lockers:locker_list")

    def form_valid(self, form):
        if get_current_rental_for_locker(self.object) and form.cleaned_data["status"] != Locker.Status.OCCUPIED:
            form.add_error("status", "Libere el casillero antes de cambiar su estado.")
            return self.form_invalid(form)
        messages.success(self.request, "Casillero actualizado correctamente.")
        return super().form_valid(form)


class LockerReleaseView(PermissionRequiredMixin, View):
    required_permission = "lockers.view"

    def post(self, request, pk):
        locker = get_object_or_404(Locker, pk=pk)
        try:
            release_locker(locker, user=request.user)
            messages.success(request, "Casillero liberado correctamente.")
        except ValidationError as e:
            messages.error(request, str(e))
        return redirect("lockers:locker_list")
