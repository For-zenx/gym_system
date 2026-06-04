from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.urls import reverse
from django.http import JsonResponse
import base64
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from apps.clients.models import Client
from apps.clients.validation import validate_client_data, client_form_context, apply_client_fields
from apps.access.models import AccessLog
from apps.access import ai_engine
from apps.users.decorators import permission_required

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

def _enrollment_wants_json(request):
    return request.headers.get('X-Enrollment-Submit') == '1'

def _enrollment_error_response(request, message, post_data=None, status=400):
    if _enrollment_wants_json(request):
        return JsonResponse({'status': 'error', 'message': message}, status=status)
    messages.error(request, message)
    return render(request, 'enrollment.html', client_form_context(post_data=post_data or request.POST))

@login_required
@permission_required("dashboard.view")
def dashboard(request):
    latest_logs = AccessLog.objects.select_related('client').order_by('-timestamp')[:4]
    return render(request, 'dashboard.html', {'logs': latest_logs})

@login_required
@permission_required("clients.enroll")
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
            first_error = next(iter(errors.values()))
            if _enrollment_wants_json(request):
                return JsonResponse({'status': 'error', 'message': first_error}, status=400)
            for message in errors.values():
                messages.error(request, message)
            context = client_form_context(post_data=request.POST)
            return render(request, 'enrollment.html', context)

        cedula = cleaned['cedula']
        nombre = cleaned['nombre']
        foto_frente_b64 = request.POST.get("foto_frente_base64")

        if not foto_frente_b64:
            return _enrollment_error_response(
                request,
                "Debe capturar la foto del afiliado en la tablet de enrolamiento.",
                post_data=request.POST,
            )

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

            client.save()

            try:
                ai_engine.update_client_embeddings(client)
            except Exception as e:
                return _enrollment_error_response(
                    request,
                    f"No se pudo procesar la foto facial: {str(e)}",
                    post_data=request.POST,
                )

            checkout_url = reverse(
                'billing:charge_checkout',
                kwargs={'codigo_afiliado': client.codigo_afiliado},
            )
            redirect_target = '{}?origin=enrollment'.format(checkout_url)
            if _enrollment_wants_json(request):
                return JsonResponse({'status': 'success', 'redirect_url': redirect_target})
            messages.success(request, f"Afiliado {nombre} {msg_action} exitosamente y procesado por IA.")
            return redirect(redirect_target)
        except Exception as e:
            return _enrollment_error_response(request, f"Error al guardar: {str(e)}", post_data=request.POST)

    return render(request, 'enrollment.html', client_form_context())

@login_required
@permission_required("clients.enroll")
def enrollment_billing(request, codigo_afiliado):
    get_object_or_404(Client, codigo_afiliado=codigo_afiliado)
    checkout_url = reverse(
        'billing:charge_checkout',
        kwargs={'codigo_afiliado': codigo_afiliado},
    )
    return redirect('{}?origin=enrollment'.format(checkout_url))
