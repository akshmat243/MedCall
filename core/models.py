import uuid
from django.db import models
from django.conf import settings
from MBP.models import Role

User = settings.AUTH_USER_MODEL  # works if you’re using a custom user model

class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room_number = models.CharField(max_length=20, unique=True)
    floor = models.CharField(max_length=20, blank=True, null=True)
    ward = models.CharField(max_length=50, blank=True, null=True)  # e.g., ICU, General Ward
    bed_count = models.PositiveIntegerField(default=1)
    is_occupied = models.BooleanField(default=False)

    def __str__(self):
        return f"Room {self.room_number} - {self.ward or 'General'}"


class Staff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="staff_profile"
    )

    department = models.CharField(max_length=100, blank=True, null=True)
    contact_number = models.CharField(max_length=15, blank=True, null=True)
    is_available = models.BooleanField(default=True)
    shift_start = models.TimeField(blank=True, null=True)
    shift_end = models.TimeField(blank=True, null=True)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.user.full_name})"
    

class Emergency(models.Model):
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("acknowledged", "Acknowledged"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("escalated", "Escalated"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey("Room", on_delete=models.CASCADE, related_name="emergencies")
    description = models.TextField(blank=True, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # Assigned to a specific User (staff user)
    assigned_user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_emergencies"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"Emergency in {self.room.room_number} ({self.priority})"

class Notification(models.Model):
    TYPE_CHOICES = [
        ("new_call", "New Emergency Call"),
        ("update", "Status Update"),
        ("reminder", "Reminder"),
        ("escalation", "Escalation"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Can target specific user
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )

    # Can target role group
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, null=True, blank=True, related_name="role_notifications"
    )

    emergency = models.ForeignKey("Emergency", on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="new_call")
    message = models.CharField(max_length=255)

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        if self.user:
            return f"Notification for {self.user.full_name} - {self.type}"
        elif self.role:
            return f"Notification for {self.role.name} - {self.type}"
        return f"Notification {self.type}"
