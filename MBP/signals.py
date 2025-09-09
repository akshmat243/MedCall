from django.db.models.signals import pre_save, post_save, post_delete
from django.dispatch import receiver
from .models import AuditLog
from .utils import log_audit_from_user
from .utils import serialize_instance


@receiver(post_save)
def log_create_or_update(sender, instance, created, **kwargs):
    if sender == AuditLog:
        return

    user = getattr(instance, '_request_user', None)
    if not user:
        print("No _request_user found. Skipping.")
        return

    model_name = sender.__name__
    object_id = instance.pk
    old_data = getattr(instance, '_old_data', None)
    new_data = serialize_instance(instance)

    if created:
        log_audit_from_user(
            user=user,
            action='create',
            model_name=model_name,
            object_id=object_id,
            details=f"Created {model_name}",
            new_data=new_data
        )
    else:
        log_audit_from_user(
            user=user,
            action='update',
            model_name=model_name,
            object_id=object_id,
            details=f"Updated {model_name}",
            old_data=old_data,
            new_data=new_data
        )


@receiver(post_delete)
def log_deletion(sender, instance, **kwargs):
    if sender == AuditLog:
        return

    user = getattr(instance, '_request_user', None)
    if not user:
        return

    model_name = sender.__name__
    object_id = instance.pk
    old_data = serialize_instance(instance)

    log_audit_from_user(
        user=user,
        action='delete',
        model_name=model_name,
        object_id=object_id,
        details=f"Signal: Deleted {model_name}: {instance}",
        old_data=old_data
    )
