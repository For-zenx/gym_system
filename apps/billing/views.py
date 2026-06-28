from urllib.parse import urlencode
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views import View
from apps.users.mixins import PermissionRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DetailView
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from apps.clients.models import Client, PersonCategory
from apps.clients.services import get_person_profile_url_name
from django.db.models import Q
from .models import Plan, Membership, ExchangeRate, Invoice, SaleItem
from .services import (
    register_checkout,
    change_client_cut_date,
    delete_invoice,
    parse_late_fee_from_post,
    parse_payment_cut_from_post,
    parse_payment_cut_day_from_post,
    parse_payment_method_from_post,
    parse_product_lines_from_post,
    preview_membership_period,
    resolve_cut_date_motivo,
)
from .printer import (
    build_invoice_preview_lines,
    compute_invoice_total,
    print_invoice,
    _format_currency_ves,
)
from .services import (
    apply_invoice_amount_edits,
    build_amount_overrides_from_post,
    post_amount_edits_differ_from_stored,
)
from apps.users.permissions import has_permission


def _charge_form_context(client, planes):
    import json

    from .services import (
        get_client_billing_context,
        get_chargeable_plans,
        CUT_DATE_CHANGE_REASONS,
    )

    ctx = get_client_billing_context(client)
    chargeable = get_chargeable_plans(client, planes)
    default_cut_day = client.fecha_corte_dia or timezone.localdate().day
    plan_previews = {}
    for plan in chargeable:
        preview = preview_membership_period(
            client,
            plan,
            cut_day_override=default_cut_day if plan.is_fixed else None,
        )
        plan_previews[str(plan.id)] = {
            "inicio": preview["fecha_inicio"].strftime("%d/%m/%Y"),
            "fin": preview["fecha_fin"].strftime("%d/%m/%Y"),
            "fecha_inicio_iso": preview["fecha_inicio"].isoformat(),
            "fecha_fin_iso": preview["fecha_fin"].isoformat(),
            "billing_type": plan.billing_type,
            "assigns_cut_date": preview.get("assigns_cut_date", False),
            "duracion": plan.duracion_display,
        }
    return {
        "billing_context": ctx,
        "planes": chargeable,
        "payment_cut_day_default": default_cut_day,
        "cut_date_change_reasons": CUT_DATE_CHANGE_REASONS,
        "billing_context_json": json.dumps(
            {
                "fixed_status": ctx["fixed_status"],
                "unpaid_period_count": ctx["unpaid_period_count"],
                "days_since_last_unpaid_cut": ctx["days_since_last_unpaid_cut"],
                "suggested_late_fee_usd": str(ctx["suggested_late_fee_usd"]),
                "default_apply_late_fee": ctx["default_apply_late_fee"],
                "warnings_on_flexible_purchase": ctx["warnings_on_flexible_purchase"],
                "fecha_corte_dia": ctx["fecha_corte_dia"],
                "default_cut_day": default_cut_day,
            }
        ),
        "plan_previews_json": json.dumps(plan_previews),
    }


def _get_safe_next_url(request, value):
    if url_has_allowed_host_and_scheme(value, allowed_hosts={request.get_host()}):
        return value
    return ''


def _normalize_checkout_origin(value):
    if value in ("profile", "enrollment", "list"):
        return value
    return "profile"


def _checkout_return_path(client, origin, next_url=""):
    path = reverse("billing:charge_checkout", kwargs={"codigo_afiliado": client.codigo_afiliado})
    query = urlencode({"origin": origin})
    if next_url:
        query = "{}&{}".format(query, urlencode({"next": next_url}))
    return "{}?{}".format(path, query)


def _checkout_back_context(client, origin, next_url=""):
    if next_url:
        return {"back_url": next_url, "back_label": "Volver"}
    if origin == "enrollment":
        return {
            "back_url": reverse("enrollment"),
            "back_label": "Volver al enrolamiento",
        }
    if origin == "list":
        list_url = (
            reverse("clients:client_list")
            if client.is_member
            else reverse("staff_persons:staff_list")
        )
        return {
            "back_url": list_url,
            "back_label": "Volver a la lista",
        }
    profile_url = reverse(
        get_person_profile_url_name(client),
        kwargs={"codigo_afiliado": client.codigo_afiliado},
    )
    return {
        "back_url": profile_url,
        "back_label": "Volver al perfil",
    }


def _process_checkout_charge(request, client, origin):
    plan_id = (request.POST.get("plan_id") or "").strip()
    plan = None
    if plan_id:
        if not client.can_purchase_membership:
            messages.error(request, "El personal del gym no puede cobrar planes ni membresías.")
            return None
        plan = get_object_or_404(Plan, id=plan_id, is_active=True)

    product_lines = parse_product_lines_from_post(request.POST)
    if product_lines:
        from apps.users.permissions import has_permission

        if not has_permission(request.user, "products.view"):
            messages.error(request, "No tienes permiso para cobrar productos.")
            return None
        if not client.can_purchase_membership:
            from .models import SaleItem

            for line in product_lines:
                item = get_object_or_404(SaleItem, pk=line["item_id"])
                if item.item_type != SaleItem.ItemType.PRODUCT:
                    messages.error(
                        request,
                        "Solo se pueden cobrar productos al personal del gym.",
                    )
                    return None
                if line.get("locker_id"):
                    messages.error(
                        request,
                        "El personal del gym no puede alquilar casilleros en caja.",
                    )
                    return None

    if not plan and not product_lines:
        messages.error(request, "Seleccione un plan y/o al menos un producto para cobrar.")
        return None

    if origin == "enrollment" and not plan:
        messages.error(request, "El enrolamiento requiere seleccionar un plan de membresía.")
        return None

    apply_late_fee, late_fee_usd = parse_late_fee_from_post(request.POST)
    payment_cut_day, payment_cut_motivo = parse_payment_cut_from_post(request.POST)

    try:
        payment_method, payment_splits = parse_payment_method_from_post(request.POST)
        result = register_checkout(
            client,
            plan=plan,
            product_lines=product_lines,
            apply_late_fee=apply_late_fee,
            late_fee_usd=late_fee_usd,
            acting_user=request.user,
            payment_cut_day=payment_cut_day,
            payment_cut_motivo=payment_cut_motivo,
            payment_method=payment_method,
            payment_splits=payment_splits,
        )
        for warning in result.warnings:
            if warning == "flexible_on_suspended_subscription":
                messages.warning(
                    request,
                    "Pase flexible vendido con suscripción fija suspendida. El afiliado tiene acceso por el pase.",
                )
        success_url = reverse("billing:payment_success", kwargs={"pk": result.invoice.pk})
        return redirect("{}?{}".format(success_url, urlencode({"origin": origin})))
    except ValidationError as e:
        messages.error(request, str(e))
    except Exception as e:
        messages.error(request, f"Error al registrar el cobro: {str(e)}")
    return None


class ExchangeRateUpdateView(PermissionRequiredMixin, View):
    required_permission = "settings.exchange_rate"
    def post(self, request):
        try:
            tasa_str = request.POST.get('tasa_ves')
            if not tasa_str:
                raise ValueError("La tasa no puede estar vacía.")
            
            tasa = float(tasa_str.replace(',', '.'))
            if tasa <= 0:
                raise ValueError("La tasa debe ser mayor a 0.")
                
            ExchangeRate.objects.create(tasa_ves=tasa)
            messages.success(request, f"Tasa VES/$ actualizada a {tasa:.2f}")
        except ValueError as e:
            messages.error(request, f"Valor de tasa inválido: {str(e)}")
        except Exception as e:
            messages.error(request, f"Error al actualizar la tasa: {str(e)}")
            
        next_url = request.POST.get('next') or request.META.get('HTTP_REFERER', '/')
        return redirect(next_url)

class ChargeCheckoutView(PermissionRequiredMixin, View):
    required_permission = "billing.charge"

    def get(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if client.is_guest:
            messages.error(request, "Los invitados no pueden usar el cobro en caja.")
            return redirect(
                reverse("guests:profile", kwargs={"codigo_afiliado": codigo_afiliado})
            )
        origin = _normalize_checkout_origin(request.GET.get("origin", "profile"))
        next_url = _get_safe_next_url(request, request.GET.get("next", ""))
        planes = Plan.objects.filter(is_active=True) if client.can_purchase_membership else Plan.objects.none()
        products_only = not client.can_purchase_membership

        context = {
            "client": client,
            "latest_rate": ExchangeRate.get_latest(),
            "origin": origin,
            "next_url": next_url,
            "is_enrollment": origin == "enrollment",
            "products_only_checkout": products_only,
            "checkout_return_url": _checkout_return_path(client, origin, next_url),
            "page_heading": "Cobro inicial" if origin == "enrollment" else "Registrar cobro",
            "submit_label": "Cobrar e imprimir" if origin == "enrollment" else "Confirmar cobro",
            "review_label": "Revisar cobro e imprimir" if origin == "enrollment" else "Revisar cobro",
            "confirm_submit_label": "Confirmar y cobrar e imprimir" if origin == "enrollment" else "Confirmar y cobrar",
        }
        context.update(_checkout_back_context(client, origin, next_url))
        context.update(_charge_form_context(client, planes))

        from apps.clients.validation import client_form_context
        from apps.billing.services import get_profile_subscription_summary
        from apps.users.permissions import has_permission

        can_view_phone = has_permission(request.user, "clients.view_phone")
        context.update(client_form_context(client=client, can_view_phone=can_view_phone))
        if client.can_purchase_membership:
            context["subscription_summary"] = get_profile_subscription_summary(client)

        sale_items = SaleItem.objects.filter(is_active=True)
        if products_only:
            sale_items = sale_items.filter(item_type=SaleItem.ItemType.PRODUCT)
        context["sale_items"] = sale_items
        can_sell_products = has_permission(request.user, "products.view")
        context["can_checkout"] = bool(context.get("planes")) or (
            sale_items.exists() and can_sell_products
        )
        context["payment_method_choices"] = [
            choice for choice in Invoice.PaymentMethod if choice != Invoice.PaymentMethod.MIXED
        ]
        import json

        context["sale_items_json"] = json.dumps(
            [
                {
                    "id": item.pk,
                    "name": item.name,
                    "price_usd": str(item.price_usd),
                    "item_type": item.item_type,
                    "requires_locker_assignment": item.requires_locker_assignment,
                }
                for item in sale_items
            ]
        )
        from apps.lockers.services import get_lockers_for_checkout

        context["available_lockers_json"] = json.dumps(
            [
                {
                    "id": locker.pk,
                    "number": locker.number,
                }
                for locker in get_lockers_for_checkout(client)
            ]
        )
        return render(request, "billing/charge_checkout.html", context)

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if client.is_guest:
            messages.error(request, "Los invitados no pueden usar el cobro en caja.")
            return redirect(
                reverse("guests:profile", kwargs={"codigo_afiliado": codigo_afiliado})
            )
        origin = _normalize_checkout_origin(
            request.POST.get("origin", request.GET.get("origin", "profile"))
        )
        next_url = _get_safe_next_url(request, request.POST.get("next", ""))

        response = _process_checkout_charge(request, client, origin)
        if response is not None:
            return response

        return redirect(_checkout_return_path(client, origin, next_url))


class RenewPlanView(PermissionRequiredMixin, View):
    """DEPRECATED: reemplazado por billing:charge_checkout — conservado para POST legacy."""

    required_permission = "billing.charge"

    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        origin = _normalize_checkout_origin(request.POST.get("origin", "profile"))
        response = _process_checkout_charge(request, client, origin)
        if response is not None:
            return response
        return redirect(
            _checkout_return_path(
                client,
                origin,
                _get_safe_next_url(request, request.POST.get("next", "")),
            )
        )


class PaymentPeriodPreviewView(PermissionRequiredMixin, View):
    required_permission = "billing.charge"
    def get(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if not client.can_purchase_membership:
            return JsonResponse({"error": "Solo afiliados pueden previsualizar membresías."}, status=400)
        plan_id = request.GET.get("plan_id")
        if not plan_id:
            return JsonResponse({"error": "plan_id requerido"}, status=400)

        plan = get_object_or_404(Plan, id=plan_id, is_active=True)
        try:
            cut_day = parse_payment_cut_day_from_post(request.GET)
        except ValidationError as e:
            return JsonResponse({"error": str(e)}, status=400)

        if plan.is_flexible:
            preview = preview_membership_period(client, plan)
        else:
            if cut_day is None:
                cut_day = client.fecha_corte_dia or timezone.localdate().day
            preview = preview_membership_period(client, plan, cut_day_override=cut_day)

        payload = {
            "inicio": preview["fecha_inicio"].strftime("%d/%m/%Y"),
            "fin": preview["fecha_fin"].strftime("%d/%m/%Y"),
            "billing_type": plan.billing_type,
        }
        if plan.is_fixed:
            payload["cut_day"] = cut_day
            payload["stored_cut_day"] = client.fecha_corte_dia
        return JsonResponse(payload)


class PaymentSuccessView(PermissionRequiredMixin, View):
    required_permission = "billing.charge"

    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        messages.success(
            request,
            "Cobro registrado. Revise la factura y ajústela si es necesario antes de imprimir.",
        )
        detail_url = reverse("billing:invoice_detail", kwargs={"pk": invoice.pk})
        origin = request.GET.get("origin", "")
        if origin:
            detail_url = "{}?{}".format(detail_url, urlencode({"origin": origin}))
        return redirect(detail_url)


class ChangeCutDateView(PermissionRequiredMixin, View):
    required_permission = "billing.change_cut_date"
    def post(self, request, codigo_afiliado):
        client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
        if not client.can_purchase_membership:
            messages.error(request, "Solo los afiliados tienen fecha de corte.")
            return redirect(
                reverse(
                    get_person_profile_url_name(client),
                    kwargs={"codigo_afiliado": codigo_afiliado},
                )
            )

        try:
            new_day = int(request.POST.get("cut_day", ""))
            motivo = resolve_cut_date_motivo(request.POST)
            change_client_cut_date(client, new_day, motivo, user=request.user)
            messages.success(request, f"Fecha de corte actualizada al día {new_day}.")
        except (ValueError, TypeError):
            messages.error(request, "Debe indicar un día de corte válido (1-31).")
        except ValidationError as e:
            messages.error(request, str(e))

        return redirect("clients:profile", codigo_afiliado=codigo_afiliado)

class PlanListView(PermissionRequiredMixin, ListView):
    required_permission = "plans.view"
    model = Plan
    template_name = 'billing/plan_list.html'
    context_object_name = 'planes'
    
    def get_queryset(self):
        return Plan.objects.filter(is_active=True).order_by('-id')

class PlanCreateView(PermissionRequiredMixin, CreateView):
    required_permission = "plans.create"
    model = Plan
    template_name = 'billing/plan_form.html'
    fields = ['nombre', 'billing_type', 'dias_duracion', 'precio_usd', 'hora_inicio', 'hora_fin']
    success_url = reverse_lazy('billing:plan_list')

    def form_valid(self, form):
        messages.success(self.request, "Plan creado exitosamente.")
        return super().form_valid(form)

class PlanUpdateView(PermissionRequiredMixin, UpdateView):
    required_permission = "plans.edit"
    model = Plan
    template_name = 'billing/plan_form.html'
    fields = ['nombre', 'billing_type', 'dias_duracion', 'precio_usd', 'hora_inicio', 'hora_fin']
    success_url = reverse_lazy('billing:plan_list')

    def form_valid(self, form):
        old_plan = self.get_object()
        old_plan.is_active = False
        old_plan.save()

        billing_type = form.cleaned_data['billing_type']
        dias_duracion = form.cleaned_data.get('dias_duracion')
        if billing_type == Plan.BillingType.FIXED:
            dias_duracion = None

        Plan.objects.create(
            nombre=form.cleaned_data['nombre'],
            billing_type=billing_type,
            dias_duracion=dias_duracion,
            precio_usd=form.cleaned_data['precio_usd'],
            hora_inicio=form.cleaned_data['hora_inicio'],
            hora_fin=form.cleaned_data['hora_fin'],
            is_active=True,
        )

        messages.success(self.request, "Plan actualizado exitosamente (Se conservó el historial de la versión anterior).")
        return redirect('billing:plan_list')

class PlanDeleteView(PermissionRequiredMixin, View):
    required_permission = "plans.delete"
    def post(self, request, pk):
        plan = get_object_or_404(Plan, pk=pk)
        plan.is_active = False
        plan.save()
        messages.success(request, "Plan eliminado exitosamente.")
        return redirect('billing:plan_list')


class SaleItemListView(PermissionRequiredMixin, ListView):
    required_permission = "products.view"
    model = SaleItem
    template_name = "billing/product_list.html"
    context_object_name = "sale_items"

    def get_queryset(self):
        return SaleItem.objects.filter(is_active=True).order_by("name", "id")


class SaleItemCreateView(PermissionRequiredMixin, CreateView):
    required_permission = "products.manage"
    model = SaleItem
    template_name = "billing/product_form.html"
    fields = ["name", "description", "item_type", "price_usd"]
    success_url = reverse_lazy("billing:product_list")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_system_locker_item"] = False
        return context

    def form_valid(self, form):
        form.instance.requires_locker_assignment = False
        form.instance.default_rental_days = 30
        messages.success(self.request, "Producto registrado correctamente.")
        return super().form_valid(form)


class SaleItemUpdateView(PermissionRequiredMixin, UpdateView):
    required_permission = "products.manage"
    model = SaleItem
    template_name = "billing/product_form.html"
    fields = ["name", "description", "item_type", "price_usd"]
    success_url = reverse_lazy("billing:product_list")

    def _apply_form_fields(self):
        if self.object.is_system_managed:
            self.fields = ["name", "description", "price_usd", "default_rental_days"]
        else:
            self.fields = ["name", "description", "item_type", "price_usd"]

    def get(self, request, *args, **kwargs):
        self.object = self.get_object()
        self._apply_form_fields()
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        self._apply_form_fields()
        return super().post(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_system_locker_item"] = bool(
            self.object and self.object.is_system_managed
        )
        return context

    def form_valid(self, form):
        if self.object.is_system_managed:
            form.instance.requires_locker_assignment = True
            form.instance.item_type = SaleItem.ItemType.SERVICE
            form.instance.system_code = self.object.system_code
        else:
            form.instance.requires_locker_assignment = False
            form.instance.default_rental_days = 30
        messages.success(self.request, "Producto actualizado correctamente.")
        return super().form_valid(form)


class SaleItemDeleteView(PermissionRequiredMixin, View):
    required_permission = "products.manage"

    def post(self, request, pk):
        item = get_object_or_404(SaleItem, pk=pk)
        if item.is_system_managed:
            messages.error(request, "El servicio de casillero del sistema no se puede desactivar.")
            return redirect("billing:product_list")
        item.is_active = False
        item.save(update_fields=["is_active"])
        messages.success(request, "Producto desactivado correctamente.")
        return redirect("billing:product_list")


class MembershipDeleteView(PermissionRequiredMixin, View):
    required_permission = "billing.delete_queued_membership"
    def post(self, request, pk):
        membership = get_object_or_404(Membership, pk=pk)
        client_code = membership.client.codigo_afiliado
        
        # We only allow deleting if it hasn't started yet (queued)
        from datetime import date
        if membership.fecha_inicio > date.today():
            membership.delete()
            messages.success(request, "Membresía encolada cancelada exitosamente.")
        else:
            messages.error(request, "No se puede eliminar una membresía activa o pasada.")
            
        return redirect('clients:profile', codigo_afiliado=client_code)

class InvoiceListView(PermissionRequiredMixin, ListView):
    required_permission = "billing.view_invoices"
    model = Invoice
    template_name = 'billing/invoice_list.html'
    context_object_name = 'invoices'
    paginate_by = 20

    def get_queryset(self):
        queryset = (
            Invoice.objects.select_related("client", "membership__plan")
            .prefetch_related("lines")
            .order_by("-fecha_emision", "-id")
        )
        q = self.request.GET.get('q', '').strip()
        if q:
            queryset = queryset.filter(
                Q(nro_control__icontains=q) |
                Q(client__nombre__icontains=q) |
                Q(client__cedula__icontains=q) |
                Q(client__codigo_afiliado__icontains=q) |
                Q(client_nombre_snapshot__icontains=q) |
                Q(client_cedula_snapshot__icontains=q) |
                Q(client_codigo_snapshot__icontains=q)
            )
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


class InvoiceDetailView(PermissionRequiredMixin, DetailView):
    required_permission = "billing.view_invoice_detail"
    model = Invoice
    template_name = 'billing/invoice_detail.html'
    context_object_name = 'invoice'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = self.object
        context["latest_rate"] = ExchangeRate.get_latest()
        context["next_url"] = _get_safe_next_url(self.request, self.request.GET.get("next", ""))
        context["ticket_lines"] = build_invoice_preview_lines(invoice)
        context["invoice_lines"] = invoice.lines.select_related("sale_item", "membership").all()
        context["uses_legacy_invoice"] = not invoice.has_detail_lines()
        has_edit_perm = has_permission(self.request.user, "billing.edit_invoice")
        context["has_edit_invoice_permission"] = has_edit_perm
        context["can_edit_invoice"] = not invoice.esta_impresa and has_edit_perm
        context["preview_ticket_url"] = reverse(
            "billing:invoice_ticket_preview",
            kwargs={"pk": invoice.pk},
        )
        return context


class InvoiceTicketPreviewView(PermissionRequiredMixin, View):
    required_permission = "billing.view_invoice_detail"

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        overrides = {}
        has_edit_perm = has_permission(request.user, "billing.edit_invoice")
        if (
            not invoice.esta_impresa
            and has_edit_perm
        ):
            overrides = build_amount_overrides_from_post(request.POST, invoice)
        elif (
            not invoice.esta_impresa
            and post_amount_edits_differ_from_stored(request.POST, invoice)
        ):
            return JsonResponse(
                {"error": "No tiene permiso para editar los montos de la factura."},
                status=403,
            )

        ticket_lines = build_invoice_preview_lines(invoice, amount_overrides=overrides)
        total = compute_invoice_total(invoice, overrides)
        return JsonResponse(
            {
                "ticket_lines": ticket_lines,
                "monto_total": str(total),
                "monto_total_fmt": _format_currency_ves(total),
            }
        )


class PrintInvoiceActionView(PermissionRequiredMixin, View):
    required_permission = "billing.print_invoice"

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        detail_url = reverse("billing:invoice_detail", kwargs={"pk": pk})
        next_url = _get_safe_next_url(request, request.POST.get("next", ""))
        if next_url:
            detail_url = "{}?{}".format(detail_url, urlencode({"next": next_url}))

        if invoice.esta_impresa:
            messages.error(request, "Esta factura ya ha sido impresa y no se puede volver a imprimir.")
            return redirect(detail_url)

        try:
            has_edit_perm = has_permission(request.user, "billing.edit_invoice")
            if not invoice.esta_impresa and post_amount_edits_differ_from_stored(
                request.POST, invoice
            ):
                if not has_edit_perm:
                    messages.error(
                        request,
                        "No tiene permiso para editar los montos de la factura.",
                    )
                    return redirect(detail_url)

            if not invoice.esta_impresa and has_edit_perm:
                edits = build_amount_overrides_from_post(request.POST, invoice)
                if invoice.has_detail_lines():
                    line_edits = {int(k): v for k, v in edits.items()}
                else:
                    line_edits = edits
                if line_edits:
                    apply_invoice_amount_edits(invoice, line_edits)
                    invoice.refresh_from_db()

            print_invoice(invoice)
            messages.success(request, "Factura {} enviada a la impresora con éxito.".format(invoice.nro_control))
        except ValidationError as exc:
            for msg in exc.messages:
                messages.error(request, msg)
        except Exception as e:
            messages.error(request, "Error al imprimir la factura: {}".format(str(e)))

        return redirect(detail_url)


class InvoiceDeleteView(PermissionRequiredMixin, View):
    required_permission = "billing.delete_invoice"

    def post(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        detail_url = reverse("billing:invoice_detail", kwargs={"pk": pk})
        next_url = _get_safe_next_url(request, request.POST.get("next", ""))
        if next_url:
            detail_url = f"{detail_url}?{urlencode({'next': next_url})}"

        if request.POST.get("confirm_delete") != "1":
            messages.error(request, "Debes confirmar la eliminación de la factura.")
            return redirect(detail_url)

        nro_control = delete_invoice(invoice)
        messages.success(request, f"Factura {nro_control} eliminada del sistema.")
        if next_url:
            return redirect(next_url)
        return redirect("billing:invoice_list")


class ReportView(PermissionRequiredMixin, View):
    required_permission = "reports.view"

    def get(self, request):
        from .reporting import (
            REPORT_PERIOD_CHOICES,
            build_report_context,
            can_send_report_today,
            daily_send_count,
            is_smtp_configured,
            normalize_period_days,
        )
        from .models import ReportEmailSettings

        period_days = normalize_period_days(request.GET.get("period", 7))
        report = build_report_context(period_days)
        cfg = ReportEmailSettings.get_settings()
        can_send, send_block_reason = can_send_report_today()

        return render(
            request,
            "billing/report.html",
            {
                "report": report,
                "period_choices": REPORT_PERIOD_CHOICES,
                "period_days": period_days,
                "recipient_email": cfg.recipient_email,
                "daily_send_limit": cfg.daily_send_limit,
                "daily_send_count": daily_send_count(),
                "can_send": can_send,
                "send_block_reason": send_block_reason,
                "smtp_configured": is_smtp_configured(),
            },
        )


class ReportSendView(PermissionRequiredMixin, View):
    required_permission = "reports.send"

    def post(self, request):
        from .reporting import normalize_period_days, send_report_email

        period_days = normalize_period_days(request.POST.get("period_days", 7))
        result = send_report_email(period_days=period_days, user=request.user)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(result)

        if result["success"]:
            messages.success(request, "Reporte enviado correctamente.")
        else:
            failed = next((item["text"] for item in result["items"] if not item["ok"]), None)
            messages.error(request, failed or "No se pudo enviar el reporte.")
        return redirect(f"{reverse('billing:report')}?period={period_days}")
