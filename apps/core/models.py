from django.db import models
from django.core.exceptions import ValidationError


class PrinterConfig(models.Model):
    class PrinterType(models.TextChoices):
        DT230_FISCAL = "DT230_FISCAL", "Tally Dascom DT-230 (Fiscal)"

    printer_type = models.CharField(
        "Tipo de impresora",
        max_length=32,
        choices=PrinterType.choices,
        default=PrinterType.DT230_FISCAL,
    )
    port = models.CharField("Puerto COM", max_length=20, blank=True, default="")
    baudrate = models.PositiveIntegerField("Baudrate", default=9600)
    is_active = models.BooleanField("Activa", default=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Configuración de Impresora"
        verbose_name_plural = "Configuración de Impresora"

    def clean(self):
        if self.is_active and PrinterConfig.objects.filter(is_active=True).exclude(pk=self.pk).exists():
            raise ValidationError("Solo puede haber una configuración de impresora activa.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls):
        config = cls.objects.first()
        if config:
            return config
        return cls(
            printer_type=cls.PrinterType.DT230_FISCAL,
            port="",
            baudrate=9600,
            is_active=True,
        )

    @classmethod
    def get_active(cls):
        config = cls.objects.filter(is_active=True).first()
        if config and config.port.strip():
            return config
        return None

    def __str__(self):
        if self.port:
            return "{0} en {1} ({2} bps)".format(
                self.get_printer_type_display(),
                self.port,
                self.baudrate,
            )
        return "{0} (sin puerto COM)".format(self.get_printer_type_display())
