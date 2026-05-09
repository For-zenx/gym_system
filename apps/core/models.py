from django.db import models
from django.core.exceptions import ValidationError

class PrinterConfig(models.Model):
    port = models.CharField("Puerto COM", max_length=20)
    baudrate = models.PositiveIntegerField("Baudrate", default=38400)
    is_active = models.BooleanField("Activa", default=True)

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
    def get_active(cls):
        return cls.objects.filter(is_active=True).first()

    def __str__(self):
        return f"Impresora en {self.port} ({self.baudrate} bps)"
