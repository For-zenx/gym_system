"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/4.2/howto/deployment/wsgi/
"""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# En produccion la licencia es obligatoria; en desarrollo local no.
from config.licencia import verify_license_if_required
verify_license_if_required()

application = get_wsgi_application()
