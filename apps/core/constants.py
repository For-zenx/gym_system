"""Constantes de hardware compartidas."""

COM_PORT_CHOICES = [
    ("", "— Seleccione un puerto —"),
] + [(f"COM{index}", f"COM{index}") for index in range(1, 21)]
