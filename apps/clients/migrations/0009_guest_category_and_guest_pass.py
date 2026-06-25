import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("clients", "0008_client_person_category"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="cedula",
            field=models.CharField(
                blank=True,
                max_length=20,
                null=True,
                unique=True,
                verbose_name="Cédula",
            ),
        ),
        migrations.AlterField(
            model_name="client",
            name="person_category",
            field=models.CharField(
                choices=[
                    ("MEMBER", "Afiliado"),
                    ("EMPLOYEE", "Empleado"),
                    ("TRAINER", "Entrenador"),
                    ("GUEST", "Invitado"),
                ],
                db_index=True,
                default="MEMBER",
                max_length=10,
                verbose_name="Categoría",
            ),
        ),
        migrations.CreateModel(
            name="GuestPass",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("valid_from", models.DateField(verbose_name="Válido desde")),
                ("valid_until", models.DateField(verbose_name="Válido hasta")),
                ("notes", models.CharField(blank=True, max_length=500, verbose_name="Notas")),
                (
                    "revoked_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="Revocado el"),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creado el")),
                (
                    "guest",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="guest_passes",
                        to="clients.client",
                        verbose_name="Invitado",
                    ),
                ),
                (
                    "registered_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="registered_guest_passes",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Registrado por",
                    ),
                ),
                (
                    "sponsor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sponsored_guest_passes",
                        to="clients.client",
                        verbose_name="Afiliado responsable",
                    ),
                ),
            ],
            options={
                "verbose_name": "Pase de invitado",
                "verbose_name_plural": "Pases de invitado",
                "ordering": ["-created_at"],
            },
        ),
    ]
