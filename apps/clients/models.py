from django.db import models

class Client(models.Model):
    # --- Datos Maestros ---
    cedula = models.CharField("Cédula", max_length=20, unique=True)
    nombre = models.CharField("Nombre Completo", max_length=255)
    telefono = models.CharField("Teléfono", max_length=20, blank=True, null=True)
    # Identificador legacy crítico para facturación fiscal
    codigo_afiliado = models.CharField("Cód. Afiliado", max_length=20, unique=True) # Ej: M-02309-00
    fecha_ingreso = models.DateField(auto_now_add=True)

    # --- Multimedia y Biometría ---
    foto = models.ImageField(upload_to='clients/photos/', blank=True, null=True)
    # Almacenaremos los embeddings (arrays de la IA) como JSON para comparación rápida
    face_id_embeddings = models.JSONField(blank=True, null=True) 

    class Meta:
        verbose_name = "Afiliado"
        verbose_name_plural = "Afiliados"

    def __str__(self):
        return f"{self.nombre} ({self.codigo_afiliado})"
