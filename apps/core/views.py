from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import base64
from django.core.files.base import ContentFile
from apps.clients.models import Client

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
    return render(request, 'dashboard.html')

@login_required
def enrollment(request):
    if request.method == "POST":
        cedula = request.POST.get("cedula")
        nombre = request.POST.get("nombre")
        telefono = request.POST.get("telefono")
        # Recuperar fotos Base64
        foto_frente_b64 = request.POST.get("foto_frente_base64")
        foto_perfil_izq_b64 = request.POST.get("foto_perfil_izq_base64")
        foto_perfil_der_b64 = request.POST.get("foto_perfil_der_base64")
        
        # Generar código automáticamente
        codigo = get_next_codigo_afiliado()
        
        try:
            # Creamos el afiliado con los datos
            client = Client(
                cedula=cedula,
                nombre=nombre,
                telefono=telefono,
                codigo_afiliado=codigo
            )
            
            # Helper function para guardar fotos base64
            def save_b64_image(b64_str, filename):
                if b64_str:
                    format, imgstr = b64_str.split(';base64,')
                    ext = format.split('/')[-1]
                    return ContentFile(base64.b64decode(imgstr), name=f"{filename}.{ext}")
                return None
            
            frente_file = save_b64_image(foto_frente_b64, f"{codigo}_frente")
            if frente_file: client.foto_frente = frente_file
            
            perfil_izq_file = save_b64_image(foto_perfil_izq_b64, f"{codigo}_perfil_izq")
            if perfil_izq_file: client.foto_perfil_izq = perfil_izq_file
            
            perfil_der_file = save_b64_image(foto_perfil_der_b64, f"{codigo}_perfil_der")
            if perfil_der_file: client.foto_perfil_der = perfil_der_file
            
            client.save()
            messages.success(request, f"Afiliado {nombre} guardado exitosamente con sus fotos.")
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f"Error al guardar: {str(e)}")
            
    return render(request, 'enrollment.html')
