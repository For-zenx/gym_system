from .models import AccessLog

def check_access_integrity(client):
    # 1. Verificar si tiene membresía
    if not hasattr(client, 'membership'):
        AccessLog.objects.create(
            client=client,
            resultado=False,
            motivo="Sin membresía registrada"
        )
        return False, "Sin membresía"
    # 2. Verificar vigencia
    membership = client.membership
    if membership.es_valida:
        AccessLog.objects.create(
            client=client,
            resultado=True,
            motivo="Acceso concedido"
        )
        return True, "OK"
    else:
        AccessLog.objects.create(
            client=client,
            resultado=False,
            motivo=f"Membresía vencida el {membership.fecha_fin.strftime('%d/%m/%Y')}"
        )
        return False, "Vencido"
