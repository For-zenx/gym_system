from .permissions import get_user_permissions


def staff_permissions(request):
    if not request.user.is_authenticated:
        return {
            "user_permissions": set(),
            "staff_profile": None,
            "staff_display_name": "",
        }
    profile = getattr(request.user, "staff_profile", None)
    display_name = request.user.username
    if profile and profile.display_name:
        display_name = profile.display_name
    elif request.user.get_full_name():
        display_name = request.user.get_full_name()
    return {
        "user_permissions": get_user_permissions(request.user),
        "staff_profile": profile,
        "staff_display_name": display_name,
    }
