from django.contrib import admin
from .models import Patient, Room, Staff, Emergency, Notification, StaffPerformance

@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("full_name", "age", "gender", "medical_record_number")
    search_fields = ("full_name", "medical_record_number")
    prepopulated_fields = {"slug": ("full_name",)}

@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("room_number", "ward", "floor", "bed_count", "is_occupied", "last_call_priority")
    search_fields = ("room_number", "ward")
    list_filter = ("ward", "is_occupied")
    prepopulated_fields = {"slug": ("room_number",)}

@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "is_available", "shift_start", "shift_end")
    search_fields = ("user__full_name", "user__email", "department")
    list_filter = ("is_available",)
    prepopulated_fields = {"slug": ("user",)}

@admin.register(Emergency)
class EmergencyAdmin(admin.ModelAdmin):
    list_display = ("room", "patient", "priority", "status", "created_at", "assigned_user", "accepted_by")
    search_fields = ("room__room_number", "patient__full_name", "description")
    list_filter = ("priority", "status", "created_at")
    prepopulated_fields = {"slug": ("room",)}

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("type", "emergency", "user", "role", "is_read", "created_at")
    search_fields = ("message", "user__full_name", "role__name")
    list_filter = ("type", "is_read", "created_at")
    prepopulated_fields = {"slug": ("type",)}

@admin.register(StaffPerformance)
class StaffPerformanceAdmin(admin.ModelAdmin):
    list_display = (
        "staff",
        "slug",
        "total_assigned",
        "resolved",
        "resolution_rate",
        "avg_response_time",
        "avg_resolution_time",
        "satisfaction_percent",
        "rating",
        "last_updated",
    )
    list_filter = ("last_updated",)
    search_fields = ("staff__full_name", "staff__email", "slug")
    readonly_fields = ("slug", "last_updated")  # auto fields not editable
    ordering = ("-last_updated",)
    
    fieldsets = (
        ("Staff Info", {
            "fields": ("staff", "slug"),
        }),
        ("Performance Stats", {
            "fields": (
                "total_assigned",
                "resolved",
                "resolution_rate",
                "avg_response_time",
                "avg_resolution_time",
                "satisfaction_percent",
                "rating",
            ),
        }),
        ("Timestamps", {
            "fields": ("last_updated",),
        }),
    )