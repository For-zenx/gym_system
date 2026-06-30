from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.http import urlencode
from django.views import View
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.billing.models import ExchangeRate, Invoice
from apps.billing.services import parse_payment_method_from_post
from apps.clients.models import Client, PersonCategory
from apps.users.mixins import PermissionRequiredMixin

from .forms import ClassSessionForm
from .models import ClassRegistration, ClassSession
from .services import (
    add_registration,
    cancel_registration,
    cancel_session,
    create_session,
    get_session_roster,
    register_class_checkout,
    set_attendance_reported,
    update_session,
)


def _validation_error_message(exc):
    if hasattr(exc, "messages"):
        return " ".join(str(message) for message in exc.messages)
    return str(exc)


class ClassSessionListView(PermissionRequiredMixin, ListView):
    required_permission = "classes.view"
    model = ClassSession
    template_name = "classes/class_list.html"
    context_object_name = "sessions"
    paginate_by = 30


class ClassSessionCreateView(PermissionRequiredMixin, CreateView):
    required_permission = "classes.manage"
    model = ClassSession
    form_class = ClassSessionForm
    template_name = "classes/class_form.html"
    success_url = reverse_lazy("classes:session_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Nueva sesión de clase"
        return context

    def form_valid(self, form):
        try:
            session = create_session(form.cleaned_data, user=self.request.user)
            messages.success(self.request, "Sesión registrada correctamente.")
            return redirect("classes:session_detail", pk=session.pk)
        except ValidationError as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)


class ClassSessionUpdateView(PermissionRequiredMixin, UpdateView):
    required_permission = "classes.manage"
    model = ClassSession
    form_class = ClassSessionForm
    template_name = "classes/class_form.html"

    def get_success_url(self):
        return reverse("classes:session_detail", kwargs={"pk": self.object.pk})

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Editar sesión"
        return context

    def form_valid(self, form):
        try:
            update_session(self.object, form.cleaned_data)
            messages.success(self.request, "Sesión actualizada correctamente.")
            return redirect(self.get_success_url())
        except ValidationError as exc:
            messages.error(self.request, str(exc))
            return self.form_invalid(form)


class ClassSessionDetailView(PermissionRequiredMixin, DetailView):
    required_permission = "classes.view"
    model = ClassSession
    template_name = "classes/class_detail.html"
    context_object_name = "session"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        session = self.object
        context["roster"] = get_session_roster(session)
        context["latest_rate"] = ExchangeRate.get_latest()
        context["can_register"] = session.is_paid and session.status != ClassSession.Status.CANCELLED
        if context["can_register"] and session.capacity is not None:
            context["can_register"] = not session.is_full
        from apps.users.permissions import has_permission

        if has_permission(self.request.user, "classes.register"):
            context["member_search_url"] = reverse("classes:member_search")
        return context


class ClassMemberSearchView(PermissionRequiredMixin, View):
    required_permission = "classes.register"

    def get(self, request):
        query = request.GET.get("q", "").strip()
        if len(query) < 2:
            return JsonResponse({"results": []})

        clients = (
            Client.objects.filter(person_category=PersonCategory.MEMBER)
            .filter(
                Q(cedula__icontains=query)
                | Q(codigo_afiliado__icontains=query)
                | Q(nombre__icontains=query)
            )
            .order_by("nombre")[:8]
        )
        results = [
            {
                "id": client.pk,
                "nombre": client.nombre,
                "cedula": client.cedula,
                "codigo_afiliado": client.codigo_afiliado,
            }
            for client in clients
        ]
        return JsonResponse({"results": results})


class ClassSessionCancelView(PermissionRequiredMixin, View):
    required_permission = "classes.manage"

    def post(self, request, pk):
        session = get_object_or_404(ClassSession, pk=pk)
        try:
            cancel_session(session)
            messages.success(request, "Sesión cancelada.")
        except ValidationError as exc:
            messages.error(request, _validation_error_message(exc))
        return redirect("classes:session_detail", pk=pk)


class ClassAttendanceView(PermissionRequiredMixin, View):
    required_permission = "classes.manage"

    def post(self, request, pk):
        session = get_object_or_404(ClassSession, pk=pk)
        try:
            count_raw = (request.POST.get("attendance_reported") or "").strip()
            count = int(count_raw) if count_raw else None
            mark_completed = request.POST.get("mark_completed") == "on"
            set_attendance_reported(session, count, mark_completed=mark_completed)
            messages.success(request, "Asistencia registrada.")
        except (ValueError, TypeError):
            messages.error(request, "Indique un número válido de asistentes.")
        except ValidationError as exc:
            messages.error(request, _validation_error_message(exc))
        return redirect("classes:session_detail", pk=pk)


class ClassRegistrationAddView(PermissionRequiredMixin, View):
    required_permission = "classes.register"

    def post(self, request, pk):
        session = get_object_or_404(ClassSession, pk=pk)
        client_id = (request.POST.get("client_id") or "").strip()
        client = None

        if client_id:
            client = Client.objects.filter(
                pk=client_id,
                person_category=PersonCategory.MEMBER,
            ).first()
        else:
            codigo = (request.POST.get("codigo_afiliado") or "").strip().upper()
            if codigo:
                client = Client.objects.filter(
                    codigo_afiliado=codigo,
                    person_category=PersonCategory.MEMBER,
                ).first()

        if not client:
            messages.error(request, "Seleccione un afiliado válido.")
            return redirect("classes:session_detail", pk=pk)

        try:
            add_registration(session, client, user=request.user)
            messages.success(request, "{} agregado.".format(client.nombre))
        except ValidationError as exc:
            messages.error(request, _validation_error_message(exc))
        return redirect("classes:session_detail", pk=pk)


class ClassRegistrationCancelView(PermissionRequiredMixin, View):
    required_permission = "classes.register"

    def post(self, request, pk):
        registration = get_object_or_404(ClassRegistration, pk=pk)
        session_pk = registration.session_id
        try:
            cancel_registration(registration, user=request.user)
            messages.success(request, "Inscripción cancelada.")
        except ValidationError as exc:
            messages.error(request, _validation_error_message(exc))
        return redirect("classes:session_detail", pk=session_pk)


class ClassCheckoutView(PermissionRequiredMixin, View):
    required_permission = "billing.charge"

    def get(self, request, registration_id):
        registration = get_object_or_404(
            ClassRegistration.objects.select_related("session", "client"),
            pk=registration_id,
        )
        session = registration.session
        client = registration.client

        if registration.status != ClassRegistration.Status.PENDING_PAYMENT:
            messages.error(request, "Esta inscripción ya no está pendiente de cobro.")
            return redirect("classes:session_detail", pk=session.pk)

        latest_rate = ExchangeRate.get_latest()
        amount_ves = Decimal("0.00")
        if latest_rate:
            amount_ves = (session.price_usd * latest_rate.tasa_ves).quantize(Decimal("0.01"))

        context = {
            "registration": registration,
            "session": session,
            "client": client,
            "latest_rate": latest_rate,
            "amount_ves": amount_ves,
            "back_url": reverse("classes:session_detail", kwargs={"pk": session.pk}),
            "payment_method_choices": [
                choice for choice in Invoice.PaymentMethod if choice != Invoice.PaymentMethod.MIXED
            ],
        }
        return render(request, "classes/class_checkout.html", context)

    def post(self, request, registration_id):
        registration = get_object_or_404(
            ClassRegistration.objects.select_related("session", "client"),
            pk=registration_id,
        )
        session = registration.session

        latest_rate = ExchangeRate.get_latest()
        if not latest_rate:
            messages.error(request, "No hay tasa de cambio registrada.")
            return redirect("classes:class_checkout", registration_id=registration_id)

        amount_ves = (session.price_usd * latest_rate.tasa_ves).quantize(Decimal("0.01"))

        try:
            payment_method, payment_splits = parse_payment_method_from_post(
                request.POST,
                expected_total=amount_ves,
            )
            invoice = register_class_checkout(
                registration,
                acting_user=request.user,
                payment_method=payment_method,
                payment_splits=payment_splits,
            )
            success_url = reverse("billing:payment_success", kwargs={"pk": invoice.pk})
            query = urlencode({"origin": "class", "session_id": session.pk})
            return redirect("{}?{}".format(success_url, query))
        except ValidationError as exc:
            messages.error(request, _validation_error_message(exc))
        except Exception as exc:
            messages.error(request, "Error al registrar el cobro: {}".format(exc))

        return redirect("classes:class_checkout", registration_id=registration_id)
