from .permissions import PERMISSION_GROUPS, validate_permissions


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
