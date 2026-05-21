from .models import AccessLog

def check_access_integrity(client):
    from django.utils import timezone
    active_memberships = client.active_memberships
    
    if not active_memberships.exists():
        if client.memberships.exists():
            latest = client.memberships.order_by('-fecha_fin').first()
            motivo = f"Membresía vencida el {latest.fecha_fin.strftime('%d/%m/%Y')}"
        else:
            motivo = "Sin membresía registrada"
            
        AccessLog.objects.create(
            client=client,
            resultado=False,
            motivo=motivo
        )
        return False, motivo

    current_time = timezone.localtime().time()
    
    for membership in active_memberships:
        if membership.is_valid_now(current_time):
            AccessLog.objects.create(
                client=client,
                resultado=True,
                motivo="Acceso concedido"
            )
            return True, "Acceso concedido"
            
    AccessLog.objects.create(
        client=client,
        resultado=False,
        motivo="Fuera de horario permitido"
    )
    return False, "Fuera de horario"
