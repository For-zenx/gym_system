import json

from django.db import models


class SQLiteJSONField(models.TextField):
    """
    JSON persistido como TEXT. Necesario en Django 4.2 + SQLite (E180 con JSONField).
    En Python se comporta como list/dict; en BD es texto JSON.
    """

    description = "JSON almacenado como texto (compatible con SQLite)"

    def from_db_value(self, value, expression, connection):
        return self.to_python(value)

    def to_python(self, value):
        if value is None or value == "":
            return None
        if isinstance(value, (list, dict)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value

    def get_prep_value(self, value):
        if value is None:
            return None
        if isinstance(value, str):
            return value
        return json.dumps(value)
