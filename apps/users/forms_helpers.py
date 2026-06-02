from .permissions import PERMISSION_GROUPS, get_user_permissions, validate_permissions


def permissions_from_post(post):
    return validate_permissions(post.getlist("permissions"))


def build_permission_groups(selected_codes=None):
    selected = set(selected_codes or [])
    groups = []
    for group_key, group_data in PERMISSION_GROUPS.items():
        groups.append(
            {
                "key": group_key,
                "label": group_data["label"],
                "permissions": [
                    {
                        "code": code,
                        "label": label,
                        "checked": code in selected,
                    }
                    for code, label in group_data["permissions"]
                ],
            }
        )
    return groups


def build_granted_permission_groups(user):
    granted = get_user_permissions(user)
    groups = []
    for group_key, group_data in PERMISSION_GROUPS.items():
        permissions = [
            {"code": code, "label": label}
            for code, label in group_data["permissions"]
            if code in granted
        ]
        if permissions:
            groups.append(
                {
                    "key": group_key,
                    "label": group_data["label"],
                    "permissions": permissions,
                }
            )
    return groups
