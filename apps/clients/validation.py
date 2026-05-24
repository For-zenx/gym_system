import re
from datetime import date, datetime

CEDULA_PREFIXES = ('V-', 'J-')
CEDULA_PATTERN = re.compile(r'^[VJ]-\d{6,10}$')
NAME_PATTERN = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s'\-]+$")
PHONE_DIGITS_PATTERN = re.compile(r'^[\d\s+\-]+$')
VALID_SEX_VALUES = ('', 'M', 'F')


def split_cedula(stored):
    if not stored:
        return 'V-', ''
    stored = stored.strip().upper()
    for prefix in CEDULA_PREFIXES:
        if stored.startswith(prefix):
            return prefix, stored[len(prefix):]
    if len(stored) >= 2 and stored[0] in ('V', 'J') and stored[1] in '-':
        prefix = stored[0] + '-'
        return prefix, stored[2:]
    digits = re.sub(r'\D', '', stored)
    return 'V-', digits


def build_cedula(prefix, number):
    prefix = (prefix or 'V-').strip().upper()
    if prefix in ('V', 'J'):
        prefix = prefix + '-'
    if prefix not in CEDULA_PREFIXES:
        prefix = 'V-'
    digits = re.sub(r'\D', '', number or '')
    return f"{prefix}{digits}"


def validate_client_data(nombre, cedula_prefix, cedula_numero, telefono, fecha_nacimiento_raw, sexo):
    errors = {}
    cleaned = {}

    nombre = (nombre or '').strip()
    if len(nombre) < 3:
        errors['nombre'] = 'El nombre debe tener al menos 3 caracteres.'
    elif not NAME_PATTERN.match(nombre):
        errors['nombre'] = 'El nombre debe contener letras válidas (no use solo números ni símbolos).'
    elif not re.search(r'[A-Za-zÁÉÍÓÚáéíóúÑñÜü]', nombre):
        errors['nombre'] = 'El nombre debe incluir al menos una letra.'
    else:
        cleaned['nombre'] = nombre

    cedula = build_cedula(cedula_prefix, cedula_numero)
    if not CEDULA_PATTERN.match(cedula):
        errors['cedula'] = 'La cédula/RIF debe tener formato V-12345678 o J-401234567 (6 a 10 dígitos).'
    else:
        cleaned['cedula'] = cedula

    telefono = (telefono or '').strip()
    if telefono:
        if not PHONE_DIGITS_PATTERN.match(telefono):
            errors['telefono'] = 'El teléfono no parece válido. Use solo números, espacios, guiones o +.'
        elif len(re.sub(r'\D', '', telefono)) < 7:
            errors['telefono'] = 'El teléfono debe tener al menos 7 dígitos.'
        else:
            cleaned['telefono'] = telefono
    else:
        cleaned['telefono'] = ''

    sexo = (sexo or '').strip().upper()
    if sexo not in VALID_SEX_VALUES:
        errors['sexo'] = 'Seleccione un sexo válido.'
    else:
        cleaned['sexo'] = sexo

    fecha_nacimiento = None
    if (fecha_nacimiento_raw or '').strip():
        try:
            parsed = datetime.strptime(fecha_nacimiento_raw.strip(), '%Y-%m-%d').date()
        except ValueError:
            errors['fecha_nacimiento'] = 'La fecha de nacimiento no es válida.'
        else:
            today = date.today()
            if parsed > today:
                errors['fecha_nacimiento'] = 'La fecha de nacimiento no puede ser futura.'
            else:
                age = today.year - parsed.year - (
                    (today.month, today.day) < (parsed.month, parsed.day)
                )
                if age < 5:
                    errors['fecha_nacimiento'] = 'La edad mínima permitida es 5 años.'
                elif age > 120:
                    errors['fecha_nacimiento'] = 'La fecha de nacimiento no parece válida.'
                else:
                    fecha_nacimiento = parsed
    cleaned['fecha_nacimiento'] = fecha_nacimiento

    return errors, cleaned


def client_form_context(client=None, post_data=None):
    if post_data is not None:
        prefix = post_data.get('cedula_prefix', 'V-')
        numero = post_data.get('cedula_numero', '')
        return {
            'form_nombre': post_data.get('nombre', ''),
            'form_cedula_prefix': prefix,
            'form_cedula_numero': numero,
            'form_telefono': post_data.get('telefono', ''),
            'form_fecha_nacimiento': post_data.get('fecha_nacimiento', ''),
            'form_sexo': post_data.get('sexo', ''),
        }
    if client:
        prefix, numero = split_cedula(client.cedula)
        return {
            'form_nombre': client.nombre,
            'form_cedula_prefix': prefix,
            'form_cedula_numero': numero,
            'form_telefono': client.telefono or '',
            'form_fecha_nacimiento': client.fecha_nacimiento.isoformat() if client.fecha_nacimiento else '',
            'form_sexo': client.sexo or '',
        }
    return {
        'form_nombre': '',
        'form_cedula_prefix': 'V-',
        'form_cedula_numero': '',
        'form_telefono': '',
        'form_fecha_nacimiento': '',
        'form_sexo': '',
    }


def apply_client_fields(client, cleaned):
    client.nombre = cleaned['nombre']
    client.cedula = cleaned['cedula']
    client.telefono = cleaned['telefono'] or None
    client.fecha_nacimiento = cleaned['fecha_nacimiento']
    client.sexo = cleaned['sexo']
