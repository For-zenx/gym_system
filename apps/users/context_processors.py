from .permissions import get_user_permissions


def staff_permissions(request):
    if not request.user.is_authenticated:
        return {
            "user_permissions": set(),
            "staff_profile": None,
        }
    profile = getattr(request.user, "staff_profile", None)
    return {
        "user_permissions": get_user_permissions(request.user),
        "staff_profile": profile,
    }
