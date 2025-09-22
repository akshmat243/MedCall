from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.utils.timezone import now
from django.contrib.auth import get_user_model

from .models import Emergency, Room, Staff, Notification
from .utils import send_notification, recalc_staff_performance

User = get_user_model()


# -------------------------
# 🔹 Emergency Notifications
# -------------------------
@receiver(post_save, sender=Emergency)
def handle_emergency_notifications(sender, instance, created, **kwargs):
    """
    Emergency lifecycle:
    - New emergency → notify available staff (bulk)
    - Assigned → notify assigned staff
    - Resolved → notify assigned staff + admins
    - Escalated → notify escalation target
    """
    if created:
        # Notify all available staff
        staff_qs = Staff.objects.filter(is_available=True)

        notifications = [
            Notification(
                user=staff.user,
                role=staff.role,
                emergency=instance,
                type="new_call",
                message=f"New emergency in Room {instance.room.room_number} "
                        f"({instance.priority}) - {instance.description or 'No details'}",
                created_at=now(),
            )
            for staff in staff_qs
        ]
        Notification.objects.bulk_create(notifications, ignore_conflicts=True)

    else:
        # Assigned
        if instance.assigned_staff:
            Notification.objects.create(
                user=instance.assigned_staff.user,
                role=instance.assigned_staff.role,
                emergency=instance,
                type="assignment",
                message=f"You have been assigned to emergency in Room {instance.room.room_number}",
            )

        # Resolved
        if instance.status == "resolved":
            if instance.assigned_staff:
                Notification.objects.create(
                    user=instance.assigned_staff.user,
                    role=instance.assigned_staff.role,
                    emergency=instance,
                    type="info",
                    message=f"Emergency in Room {instance.room.room_number} resolved.",
                )

            admin_qs = User.objects.filter(role__name__iexact="admin")
            notifications = [
                Notification(
                    user=admin,
                    role=getattr(admin, "role", None),
                    emergency=instance,
                    type="update",
                    message=f"Emergency in Room {instance.room.room_number} resolved at {now().strftime('%H:%M')}.",
                    created_at=now(),
                )
                for admin in admin_qs
            ]
            Notification.objects.bulk_create(notifications, ignore_conflicts=True)

        # Escalated
        if instance.status == "escalated" and instance.escalated_to:
            Notification.objects.create(
                user=instance.escalated_to,
                role=getattr(instance.escalated_to, "role", None),
                emergency=instance,
                type="escalation",
                message=f"Emergency in Room {instance.room.room_number} escalated.",
            )


# -------------------------
# 🔹 Room Notifications
# -------------------------
@receiver(post_save, sender=Room)
def handle_room_notifications(sender, instance, created, **kwargs):
    """Notify staff when room occupancy changes"""
    if not created:
        staff_qs = Staff.objects.filter(is_available=True)

        if instance.is_occupied:
            msg = f"Room {instance.room.room_number} is now occupied (Patient: {instance.patient.full_name})."
        else:
            msg = f"Room {instance.room.room_number} is now free."

        notifications = [
            Notification(
                user=staff.user,
                role=staff.role,
                emergency=None,
                type="room_update",
                message=msg,
                created_at=now(),
            )
            for staff in staff_qs
        ]
        Notification.objects.bulk_create(notifications, ignore_conflicts=True)


# -------------------------
# 🔹 Staff Performance Updates
# -------------------------
@receiver(post_save, sender=Emergency)
def update_staff_performance_on_emergency_save(sender, instance, created, **kwargs):
    """Recalc staff performance whenever an emergency is created/updated"""
    if instance.assigned_staff:
        recalc_staff_performance(instance.assigned_staff, store=True)


@receiver(post_delete, sender=Emergency)
def update_staff_performance_on_emergency_delete(sender, instance, **kwargs):
    """Recalc staff performance when an emergency is deleted"""
    if instance.assigned_staff:
        recalc_staff_performance(instance.assigned_staff, store=True)


@receiver(post_save, sender=Staff)
def update_staff_performance_on_staff_save(sender, instance, created, **kwargs):
    """Always recalc when a Staff object is created/updated"""
    recalc_staff_performance(instance, store=True)
