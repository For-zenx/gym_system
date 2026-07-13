from django.core.exceptions import ValidationError

from apps.core.constants import COM_PORT_CHOICES
from apps.core.models import PrinterConfig

_VALID_PORTS = {value for value, _label in COM_PORT_CHOICES if value}


def update_printer_settings(*, printer_type, port):
    printer_type = (printer_type or "").strip()
    port = (port or "").strip()

    valid_types = {choice.value for choice in PrinterConfig.PrinterType}
    if printer_type not in valid_types:
        raise ValidationError("Seleccione un tipo de impresora válido.")

    if port and port not in _VALID_PORTS:
        raise ValidationError("Seleccione un puerto COM válido.")

    config = PrinterConfig.objects.first()
    if config is None:
        config = PrinterConfig()

    config.printer_type = printer_type
    config.port = port
    config.baudrate = 9600
    config.is_active = True
    config.save()

    PrinterConfig.objects.exclude(pk=config.pk).update(is_active=False)
    return config
