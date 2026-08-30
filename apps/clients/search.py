import re

from django.db.models import Q

from .models import PERSON_CODE_PREFIX, Client, PersonCategory

SEARCH_MODE_AUTO = "auto"
SEARCH_MODE_CODE = "code"

VALID_CODE_PREFIXES = frozenset(PERSON_CODE_PREFIX.values())


def _digits_only(value):
    return re.sub(r"\D", "", value or "")


def apply_person_search(queryset, query, mode=SEARCH_MODE_AUTO, code_prefix=None):
    """Filter a Client queryset for person search modals."""
    query = (query or "").strip()
    if not query:
        return queryset.none()

    if mode == SEARCH_MODE_CODE:
        prefix = (code_prefix or "").strip().upper()
        if prefix not in VALID_CODE_PREFIXES:
            return queryset.none()

        digits = _digits_only(query)
        if not digits:
            return queryset.none()

        return queryset.filter(
            codigo_afiliado__startswith="{}-".format(prefix),
            codigo_afiliado__icontains=digits,
        )

    return queryset.filter(
        Q(cedula__icontains=query)
        | Q(codigo_afiliado__icontains=query)
        | Q(nombre__icontains=query)
    )


def person_search_min_length(mode=SEARCH_MODE_AUTO):
    return 1 if mode == SEARCH_MODE_CODE else 2


def search_clients_for_modal(query, mode=SEARCH_MODE_AUTO, code_prefix=None, exclude_guests=False):
    queryset = Client.objects.all()
    if exclude_guests:
        queryset = queryset.exclude(person_category=PersonCategory.GUEST)
        if mode == SEARCH_MODE_CODE and (code_prefix or "").strip().upper() == "G":
            return []

    queryset = apply_person_search(queryset, query, mode=mode, code_prefix=code_prefix)
    return list(queryset.order_by("nombre")[:8])
