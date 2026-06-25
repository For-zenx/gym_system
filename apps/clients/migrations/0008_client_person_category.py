from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0007_client_terms_accepted_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="client",
            name="person_category",
            field=models.CharField(
                choices=[
                    ("MEMBER", "Afiliado"),
                    ("EMPLOYEE", "Empleado"),
                    ("TRAINER", "Entrenador"),
                ],
                db_index=True,
                default="MEMBER",
                max_length=10,
                verbose_name="Categoría",
            ),
        ),
        migrations.AlterField(
            model_name="client",
            name="codigo_afiliado",
            field=models.CharField(max_length=20, unique=True, verbose_name="Código"),
        ),
    ]
