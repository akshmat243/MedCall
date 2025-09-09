from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.timezone import now
from django.contrib.auth import get_user_model

from models import Emergency, Room
from .models import Notification

User = get_user_model()


@receiver(post_save, sender=Emergency)
def send_emergency_notifications(sender, instance, created, **kwargs):
    """Send notifications when emergencies are created or resolved"""
    if created:
        # Notify all staff users when a new emergency is created
        staff_users = User.objects.filter(role__name="Staff")
        for staff in staff_users:
            Notification.objects.create(
                user=staff,
                role=staff.role,
                emergency=instance,
                type="emergency",
                message=f"New emergency in Room {instance.room.room_number}: {instance.description}"
            )
    else:
        # If status is resolved, notify the assigned user + admins
        if instance.status == "resolved":
            if instance.assigned_user:
                Notification.objects.create(
                    user=instance.assigned_user,
                    role=instance.assigned_user.role,
                    emergency=instance,
                    type="info",
                    message=f"Emergency in Room {instance.room.room_number} has been resolved."
                )

            admin_users = User.objects.filter(role__name="Admin")
            for admin in admin_users:
                Notification.objects.create(
                    user=admin,
                    role=admin.role,
                    emergency=instance,
                    type="info",
                    message=f"Emergency in Room {instance.room.room_number} was resolved at {now()}."
                )


@receiver(post_save, sender=Room)
def send_room_notifications(sender, instance, created, **kwargs):
    """Send notifications when room occupancy changes"""
    if not created:  # Only on update
        if instance.is_occupied:
            # Notify staff that a room got occupied
            staff_users = User.objects.filter(role__name="Staff")
            for staff in staff_users:
                Notification.objects.create(
                    user=staff,
                    role=staff.role,
                    type="info",
                    message=f"🛏️ Room {instance.room_number} is now occupied."
                )
        else:
            # Notify staff that a room got free
            staff_users = User.objects.filter(role__name="Staff")
            for staff in staff_users:
                Notification.objects.create(
                    user=staff,
                    role=staff.role,
                    type="info",
                    message=f"Room {instance.room_number} is now available."
                )
