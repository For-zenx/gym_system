from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import Client


def _invalidate_client_embedding_cache():
    from apps.access.ai_engine import invalidate_embedding_cache

    # Invalida ahora (rollback seguro) y otra vez al commit para evitar una
    # recarga concurrente con datos previos a la transacción.
    invalidate_embedding_cache()
    transaction.on_commit(invalidate_embedding_cache)


@receiver(post_save, sender=Client)
@receiver(post_delete, sender=Client)
def invalidate_client_embedding_gallery(sender, instance, **kwargs):
    _invalidate_client_embedding_cache()
