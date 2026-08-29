"""Session idle timeout for staff browser logins (TASK-133)."""

import time

from django.conf import settings
from django.contrib.auth import logout


LAST_ACTIVITY_KEY = "_pl_last_activity"


class SessionIdleTimeoutMiddleware:
    """
    Force re-login after SESSION_IDLE_TIMEOUT_SECONDS without requests.
    Works with SESSION_EXPIRE_AT_BROWSER_CLOSE (server-side idle, not cookie Max-Age).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        idle_seconds = int(getattr(settings, "SESSION_IDLE_TIMEOUT_SECONDS", 0) or 0)
        if idle_seconds > 0 and getattr(request, "user", None) is not None:
            if request.user.is_authenticated:
                now = int(time.time())
                last_raw = request.session.get(LAST_ACTIVITY_KEY)
                try:
                    last = int(last_raw) if last_raw is not None else None
                except (TypeError, ValueError):
                    last = None
                if last is not None and (now - last) > idle_seconds:
                    logout(request)
                else:
                    request.session[LAST_ACTIVITY_KEY] = now

        return self.get_response(request)
