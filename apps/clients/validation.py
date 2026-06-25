import re
from datetime import date, datetime

CEDULA_PREFIXES = ('V-', 'J-')
CEDULA_PATTERN = re.compile(r'^[VJ]-\d{6,10}$')
NAME_PATTERN = re.compile(r"^[A-Za-zÁÉÍÓÚáéíóúÑñÜü\s'\-]+$")
PHONE_DIGITS_PATTERN = re.compile(r'^[\d\s+\-]+$')
VALID_SEX_VALUES = ('', 'M', 'F')
PHONE_MASKED_DISPLAY = "**********"
PHONE_UNAUTHORIZED_DISPLAY = "No autorizado"


def display_client_phone(telefono, can_view_phone):
    if can_view_phone:
        return telefono or "N/A"
    if telefono:
        return PHONE_MASKED_DISPLAY
    return PHONE_UNAUTHORIZED_DISPLAY


def display_client_phone_feed(telefono, can_view_phone):
    if can_view_phone:
        return telefono or "No registrado"
    if telefono:
        return PHONE_MASKED_DISPLAY
    return "No registrado"


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


GUEST_MINOR_MAX_AGE = 17


def _calculate_age(birth_date, today=None):
    if today is None:
        today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


def validate_guest_data(
    nombre,
    cedula_prefix,
    cedula_numero,
    telefono,
    fecha_nacimiento_raw,
    sexo,
    minor_without_cedula=False,
):
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
                age = _calculate_age(parsed, today)
                if age < 0:
                    errors['fecha_nacimiento'] = 'La fecha de nacimiento no parece válida.'
                elif age > 120:
                    errors['fecha_nacimiento'] = 'La fecha de nacimiento no parece válida.'
                else:
                    fecha_nacimiento = parsed
    cleaned['fecha_nacimiento'] = fecha_nacimiento

    minor_flag = str(minor_without_cedula).lower() in ('1', 'true', 'on', 'yes')
    cleaned['minor_without_cedula'] = minor_flag

    if minor_flag:
        if fecha_nacimiento is None:
            errors['fecha_nacimiento'] = 'Indique la fecha de nacimiento del menor.'
        elif _calculate_age(fecha_nacimiento) > GUEST_MINOR_MAX_AGE:
            errors['fecha_nacimiento'] = (
                'La opción «menor sin cédula» solo aplica a menores de 18 años.'
            )
        cleaned['cedula'] = None
    else:
        cedula = build_cedula(cedula_prefix, cedula_numero)
        if not CEDULA_PATTERN.match(cedula):
            errors['cedula'] = 'La cédula/RIF debe tener formato V-12345678 o J-401234567 (6 a 10 dígitos).'
        else:
            cleaned['cedula'] = cedula

    return errors, cleaned


def validate_guest_enrollment_data(nombre):
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

    cleaned['cedula'] = None
    cleaned['telefono'] = None
    cleaned['fecha_nacimiento'] = None
    cleaned['sexo'] = ''

    return errors, cleaned


def validate_guest_pass_dates(valid_from_raw, valid_until_raw):
    errors = {}
    cleaned = {}
    today = date.today()

    if not (valid_from_raw or '').strip():
        cleaned['valid_from'] = today
    else:
        try:
            cleaned['valid_from'] = datetime.strptime(valid_from_raw.strip(), '%Y-%m-%d').date()
        except ValueError:
            errors['valid_until'] = 'La fecha de inicio del pase no es válida.'

    if not (valid_until_raw or '').strip():
        errors['valid_until'] = 'Indique la fecha de vencimiento del pase.'
    else:
        try:
            valid_until = datetime.strptime(valid_until_raw.strip(), '%Y-%m-%d').date()
        except ValueError:
            errors['valid_until'] = 'La fecha de vencimiento del pase no es válida.'
        else:
            valid_from = cleaned.get('valid_from', today)
            if valid_until < valid_from:
                errors['valid_until'] = 'La fecha de vencimiento no puede ser anterior al inicio del pase.'
            else:
                cleaned['valid_until'] = valid_until

    return errors, cleaned


def client_form_context(client=None, post_data=None, can_view_phone=True):
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
            'can_view_client_phone': can_view_phone,
        }
    if client:
        prefix, numero = split_cedula(client.cedula)
        return {
            'form_nombre': client.nombre,
            'form_cedula_prefix': prefix,
            'form_cedula_numero': numero,
            'form_telefono': (client.telefono or '') if can_view_phone else '',
            'form_fecha_nacimiento': client.fecha_nacimiento.isoformat() if client.fecha_nacimiento else '',
            'form_sexo': client.sexo or '',
            'can_view_client_phone': can_view_phone,
        }
    return {
        'form_nombre': '',
        'form_cedula_prefix': 'V-',
        'form_cedula_numero': '',
        'form_telefono': '',
        'form_fecha_nacimiento': '',
        'form_sexo': '',
        'can_view_client_phone': can_view_phone,
    }


def apply_client_fields(client, cleaned, preserve_phone_if_blank=False):
    client.nombre = cleaned['nombre']
    client.cedula = cleaned['cedula']
    if preserve_phone_if_blank and not cleaned['telefono']:
        pass
    else:
        client.telefono = cleaned['telefono'] or None
    client.fecha_nacimiento = cleaned['fecha_nacimiento']
    client.sexo = cleaned['sexo']
