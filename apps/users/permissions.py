"""
Catálogo central de permisos de negocio para staff del gimnasio.
Cada código se almacena en StaffRole (plantilla) y StaffProfile (cuenta).
"""

PERMISSION_GROUPS = {
    "dashboard": {
        "label": "Inicio",
        "permissions": [
            ("dashboard.view", "Ver inicio"),
        ],
    },
    "clients": {
        "label": "Afiliados",
        "permissions": [
            ("clients.view_list", "Ver lista de afiliados"),
            ("clients.view_profile", "Ver perfil del afiliado"),
            ("clients.edit", "Editar datos personales"),
            ("clients.view_phone", "Ver teléfono del afiliado"),
            ("clients.enroll", "Enrolar nuevos afiliados"),
            ("clients.delete", "Eliminar afiliados"),
        ],
    },
    "billing_ops": {
        "label": "Caja",
        "permissions": [
            ("billing.charge", "Registrar cobro"),
            ("billing.change_cut_date", "Cambiar fecha de corte"),
            ("billing.view_audit", "Ver auditoría en perfil"),
            ("billing.delete_queued_membership", "Eliminar membresía encolada"),
        ],
    },
    "billing_invoices": {
        "label": "Facturas",
        "permissions": [
            ("billing.view_invoices", "Ver historial de facturas"),
            ("billing.view_invoice_detail", "Ver detalle / ticket"),
            ("billing.print_invoice", "Imprimir factura"),
            ("billing.delete_invoice", "Eliminar facturas"),
        ],
    },
    "plans": {
        "label": "Planes",
        "permissions": [
            ("plans.view", "Ver planes"),
            ("plans.create", "Crear planes"),
            ("plans.edit", "Editar planes"),
            ("plans.delete", "Eliminar planes"),
        ],
    },
    "products": {
        "label": "Productos y servicios",
        "permissions": [
            ("products.view", "Ver catálogo y vender en caja"),
            ("products.manage", "Gestionar catálogo de productos"),
        ],
    },
    "access": {
        "label": "Accesos",
        "permissions": [
            ("access.view_logs", "Ver historial de accesos"),
        ],
    },
    "settings": {
        "label": "Configuración del negocio",
        "permissions": [
            ("settings.exchange_rate", "Cambiar tasa VES/$"),
            ("settings.billing", "Configuración de multa"),
        ],
    },
    "administration": {
        "label": "Administración del sistema",
        "permissions": [
            ("users.view", "Ver usuarios"),
            ("users.create", "Crear usuarios"),
            ("users.edit", "Editar / activar-desactivar usuarios"),
            ("roles.manage", "Gestionar plantillas de permisos"),
        ],
    },
}

ALL_PERMISSION_CODES = []
for _group in PERMISSION_GROUPS.values():
    for code, _label in _group["permissions"]:
        ALL_PERMISSION_CODES.append(code)

CASHIER_PERMISSION_CODES = [
    "dashboard.view",
    "clients.view_list",
    "clients.view_profile",
    "clients.edit",
    "clients.enroll",
    "billing.charge",
    "billing.change_cut_date",
    "billing.view_audit",
    "billing.delete_queued_membership",
    "billing.view_invoices",
    "billing.view_invoice_detail",
    "billing.print_invoice",
    "plans.view",
    "products.view",
    "access.view_logs",
]

ADMINISTRATOR_PERMISSION_CODES = list(ALL_PERMISSION_CODES)

ADMIN_CAPACITY_PERMISSIONS = frozenset(
    {
        "roles.manage",
        "users.view",
    }
)


def validate_permissions(codes):
    if not codes:
        return []
    allowed = set(ALL_PERMISSION_CODES)
    seen = set()
    result = []
    for code in codes:
        if code in allowed and code not in seen:
            seen.add(code)
            result.append(code)
    return result


def get_user_permissions(user):
    if not user or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(ALL_PERMISSION_CODES)
    profile = getattr(user, "staff_profile", None)
    if profile is None:
        return set()
    return set(validate_permissions(profile.permissions or []))


def has_permission(user, code):
    if code not in ALL_PERMISSION_CODES:
        return False
    return code in get_user_permissions(user)
