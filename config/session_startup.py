"""Flush staff browser sessions once when the ASGI/WSGI process starts (TASK-133)."""

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


def flush_sessions_on_startup_if_enabled():
    if not getattr(settings, "SESSION_FLUSH_ON_STARTUP", False):
        return
    try:
        from django.contrib.sessions.models import Session

        deleted_count, _ = Session.objects.all().delete()
        logger.info("SESSION_FLUSH_ON_STARTUP: cleared %s session row(s)", deleted_count)
    except Exception:
        logger.exception("SESSION_FLUSH_ON_STARTUP: failed to clear sessions")
