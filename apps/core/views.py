from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import base64
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from apps.clients.models import Client
from apps.clients.validation import validate_client_data, client_form_context, apply_client_fields
from apps.access.models import AccessLog
from apps.access import ai_engine
from apps.billing.models import Plan, ExchangeRate
from apps.billing.services import register_membership_renewal

def get_next_codigo_afiliado():
    last_client = Client.objects.order_by('id').last()
    if not last_client or not last_client.codigo_afiliado:
        return 'M-00001-00'
    
    parts = last_client.codigo_afiliado.split('-')
    if len(parts) >= 2 and parts[0] == 'M':
        try:
            num = int(parts[1])
            return f"M-{num + 1:05d}-00"
        except ValueError:
            pass
    return 'M-00001-00'

@login_required
def dashboard(request):
    latest_logs = AccessLog.objects.select_related('client').order_by('-timestamp')[:4]
    return render(request, 'dashboard.html', {'logs': latest_logs})

@login_required
def enrollment(request):
    if request.method == "POST":
        errors, cleaned = validate_client_data(
            request.POST.get('nombre'),
            request.POST.get('cedula_prefix'),
            request.POST.get('cedula_numero'),
            request.POST.get('telefono'),
            request.POST.get('fecha_nacimiento'),
            request.POST.get('sexo'),
        )

        if errors:
            for message in errors.values():
                messages.error(request, message)
            context = client_form_context(post_data=request.POST)
            return render(request, 'enrollment.html', context)

        cedula = cleaned['cedula']
        nombre = cleaned['nombre']
        foto_frente_b64 = request.POST.get("foto_frente_base64")
        foto_perfil_izq_b64 = request.POST.get("foto_perfil_izq_base64")
        foto_perfil_der_b64 = request.POST.get("foto_perfil_der_base64")

        try:
            client = Client.objects.filter(cedula=cedula).first()

            if client:
                apply_client_fields(client, cleaned)
                msg_action = "actualizado"
            else:
                codigo = get_next_codigo_afiliado()
                client = Client(
                    cedula=cedula,
                    nombre=nombre,
                    telefono=cleaned['telefono'] or None,
                    fecha_nacimiento=cleaned['fecha_nacimiento'],
                    sexo=cleaned['sexo'],
                    codigo_afiliado=codigo,
                )
                msg_action = "guardado"

            codigo_final = client.codigo_afiliado

            def save_b64_image(b64_str, filename):
                if b64_str:
                    format, imgstr = b64_str.split(';base64,')
                    ext = format.split('/')[-1]
                    full_filename = f"{filename}.{ext}"
                    storage_path = f"clients/enrollment/{full_filename}"
                    if default_storage.exists(storage_path):
                        default_storage.delete(storage_path)
                    return ContentFile(base64.b64decode(imgstr), name=full_filename)
                return None

            frente_file = save_b64_image(foto_frente_b64, f"{codigo_final}_frente")
            if frente_file:
                client.foto_frente = frente_file

            perfil_izq_file = save_b64_image(foto_perfil_izq_b64, f"{codigo_final}_perfil_izq")
            if perfil_izq_file:
                client.foto_perfil_izq = perfil_izq_file

            perfil_der_file = save_b64_image(foto_perfil_der_b64, f"{codigo_final}_perfil_der")
            if perfil_der_file:
                client.foto_perfil_der = perfil_der_file

            client.save()

            try:
                ai_engine.update_client_embeddings(client)
                messages.success(request, f"Afiliado {nombre} {msg_action} exitosamente y procesado por IA.")
            except Exception as e:
                messages.warning(request, f"Afiliado {nombre} {msg_action}, pero falló el procesamiento de IA: {str(e)}")

            return redirect('enrollment_billing', codigo_afiliado=client.codigo_afiliado)
        except Exception as e:
            messages.error(request, f"Error al guardar: {str(e)}")
            context = client_form_context(post_data=request.POST)
            return render(request, 'enrollment.html', context)

    return render(request, 'enrollment.html', client_form_context())

@login_required
def enrollment_billing(request, codigo_afiliado):
    client = get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
    
    if request.method == "POST":
        plan_id = request.POST.get('plan_id')
        if not plan_id:
            messages.error(request, "Debe seleccionar un plan válido.")
            return redirect('enrollment_billing', codigo_afiliado=codigo_afiliado)
            
        plan = get_object_or_404(Plan, id=plan_id)
        
        try:
            membership, invoice = register_membership_renewal(client, plan)
            return render(request, 'enrollment/success_step.html', {
                'client': client,
                'invoice': invoice,
                'membership': membership
            })
        except Exception as e:
            messages.error(request, f"Error al generar factura: {str(e)}")
            return redirect('enrollment_billing', codigo_afiliado=codigo_afiliado)
            
    context = {
        'client': client,
        'planes': Plan.objects.filter(is_active=True),
        'latest_rate': ExchangeRate.get_latest(),
    }
    context.update(client_form_context(client=client))
    return render(request, 'enrollment/billing_step.html', context)
