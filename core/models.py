import uuid
from django.db import models
from django.conf import settings
from django.utils.text import slugify
from MBP.models import Role

User = settings.AUTH_USER_MODEL


class Patient(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    full_name = models.CharField(max_length=200)
    age = models.PositiveIntegerField(blank=True, null=True)
    gender = models.CharField(max_length=10, blank=True, null=True)
    contact_number = models.CharField(max_length=20, blank=True, null=True)
    medical_record_number = models.CharField(max_length=64, blank=True, null=True, unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.full_name}-{uuid.uuid4().hex[:6]}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.full_name} ({self.medical_record_number})"


class Room(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    room_number = models.CharField(max_length=20, unique=True)
    floor = models.CharField(max_length=20, blank=True, null=True)
    ward = models.CharField(max_length=50, blank=True, null=True)  # e.g., ICU, General Ward
    bed_count = models.PositiveIntegerField(default=1)
    is_occupied = models.BooleanField(default=False)
    patient = models.ForeignKey("Patient", on_delete=models.SET_NULL, null=True, blank=True, related_name="rooms")
    last_call_priority = models.CharField(max_length=10, blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"room-{self.room_number}-{uuid.uuid4().hex[:6]}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Room {self.room_number} - {self.ward or 'General'}"


class Staff(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="staff_profile")
    department = models.CharField(max_length=100, blank=True, null=True)
    contact_number = models.CharField(max_length=15, blank=True, null=True)
    is_available = models.BooleanField(default=True)
    shift_start = models.TimeField(blank=True, null=True)
    shift_end = models.TimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.user.username}-{uuid.uuid4().hex[:6]}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.get_full_name()} ({self.department})"


class Emergency(models.Model):
    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("notified", "Notified"),
        ("assigned", "Assigned"),
        ("accepted", "Accepted"),
        ("in_progress", "In Progress"),
        ("resolved", "Resolved"),
        ("cancelled", "Cancelled"),
        ("escalated", "Escalated"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name="emergencies")
    patient = models.ForeignKey(Patient, on_delete=models.SET_NULL, null=True, blank=True, related_name="emergencies")
    description = models.TextField(blank=True, null=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_calls")
    assigned_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_emergencies")
    accepted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="accepted_emergencies")

    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(blank=True, null=True)
    accepted_at = models.DateTimeField(blank=True, null=True)
    reached_at = models.DateTimeField(blank=True, null=True)
    resolved_at = models.DateTimeField(blank=True, null=True)
    escalated_to = models.ForeignKey(Role, on_delete=models.SET_NULL, null=True, blank=True, related_name="escalated_emergencies")

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"emergency-{self.room.room_number}-{uuid.uuid4().hex[:6]}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Emergency {self.priority} - {self.room.room_number}"


class Notification(models.Model):
    TYPE_CHOICES = [
        ("new_call", "New Emergency Call"),
        ("update", "Status Update"),
        ("reminder", "Reminder"),
        ("escalation", "Escalation"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    slug = models.SlugField(max_length=255, unique=True, blank=True)

    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True, related_name="notifications")
    role = models.ForeignKey(Role, on_delete=models.CASCADE, null=True, blank=True, related_name="role_notifications")
    emergency = models.ForeignKey(Emergency, on_delete=models.CASCADE, related_name="notifications")

    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="new_call")
    message = models.CharField(max_length=255)

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"notification-{uuid.uuid4().hex[:6]}")
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Notification {self.type} → {self.user or self.role}"

class StaffPerformance(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    staff = models.OneToOneField(User, on_delete=models.CASCADE, related_name="performance")
    
    slug = models.SlugField(max_length=255, unique=True, blank=True)  # added slug
    
    total_assigned = models.PositiveIntegerField(default=0)
    resolved = models.PositiveIntegerField(default=0)
    resolution_rate = models.FloatField(default=0.0)  # %
    avg_response_time = models.DurationField(default=0)
    avg_resolution_time = models.DurationField(default=0)
    
    satisfaction_percent = models.FloatField(default=0.0)  # optional
    rating = models.FloatField(default=0.0)  # optional
    
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_updated"]

    def save(self, *args, **kwargs):
        # auto-generate slug from staff name if not set
        if not self.slug and self.staff:
            base_slug = slugify(self.staff.get_full_name())
            slug = base_slug
            n = 1
            # ensure unique
            while StaffPerformance.objects.filter(slug=slug).exclude(id=self.id).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Performance: {self.staff.get_full_name()}"