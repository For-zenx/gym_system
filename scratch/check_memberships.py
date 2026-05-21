import os
import sys
import django

# Add the project directory to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from apps.clients.models import Client
from apps.billing.models import Membership

print("--- CLIENT MEMBERSHIPS DUMP ---")
for c in Client.objects.all():
    print(f"Client: {c.nombre} ({c.codigo_afiliado})")
    mems = c.memberships.all().order_by('fecha_inicio')
    if not mems.exists():
        print("  No memberships.")
    for m in mems:
        print(f"  - ID {m.id}: {m.plan.nombre} | {m.fecha_inicio} to {m.fecha_fin}")
print("--------------------------------")
