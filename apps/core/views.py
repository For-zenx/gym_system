from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
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
        
        # Generar código automáticamente
        codigo = get_next_codigo_afiliado()
        
        try:
            # Creamos el afiliado con los datos de texto (las fotos quedan vacías temporalmente)
            Client.objects.create(
                cedula=cedula,
                nombre=nombre,
                telefono=telefono,
                codigo_afiliado=codigo
            )
            messages.success(request, f"Afiliado {nombre} guardado exitosamente.")
            return redirect('dashboard')
        except Exception as e:
            messages.error(request, f"Error al guardar: {str(e)}")
            
    return render(request, 'enrollment.html')
