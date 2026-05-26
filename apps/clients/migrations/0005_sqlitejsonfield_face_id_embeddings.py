# Generated manually for SQLite + Django 4.2 compatibility

import apps.clients.fields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0004_client_fecha_nacimiento_sexo"),
    ]

    operations = [
        migrations.AlterField(
            model_name="client",
            name="face_id_embeddings",
            field=apps.clients.fields.SQLiteJSONField(blank=True, null=True),
        ),
    ]
