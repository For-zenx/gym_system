import os
from django.conf import settings
from django.core.files.base import ContentFile

def save_enrollment_photos(client, files_dict):
    """
    Guarda las 3 fotos de enrolamiento en media/clients/{id}/.
    Sobreescribe las existentes si el afiliado se está re-enrolando.
    files_dict: {'frente': file, 'izquierda': file, 'derecha': file}
    """
    client_folder = os.path.join('clients', str(client.id))
    full_path = os.path.join(settings.MEDIA_ROOT, client_folder)

    # Asegurar que la carpeta del cliente exista
    if not os.path.exists(full_path):
        os.makedirs(full_path)

    for side, uploaded_file in files_dict.items():
        if side not in ['frente', 'izquierda', 'derecha']:
            continue
        
        filename = f"{side}.jpg"
        file_path = os.path.join(full_path, filename)

        # Borrar archivo anterior si existe (re-enrolamiento)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Guardar el nuevo archivo
        with open(file_path, 'wb+') as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        
        # Guardar la referencia de la foto principal (frente) en el modelo
        if side == 'frente':
            client.foto = os.path.join(client_folder, filename)
            client.save()

    return True
