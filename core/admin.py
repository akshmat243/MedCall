# admin.py
from django.contrib import admin
from .models import Room, Staff, Emergency, Notification


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ("room_number", "floor", "ward", "bed_count", "is_occupied")
    search_fields = ("room_number", "ward", "floor")
    list_filter = ("ward", "is_occupied")
    ordering = ("room_number",)


@admin.register(Staff)
class StaffAdmin(admin.ModelAdmin):
    list_display = ("user", "department", "contact_number", "is_available", "shift_start", "shift_end")
    search_fields = ("user__full_name","department")
    list_filter = ("is_available", "department")
    ordering = ("user__full_name",)


@admin.register(Emergency)
class EmergencyAdmin(admin.ModelAdmin):
    list_display = ("room", "priority", "status", "assigned_user", "created_at", "resolved_at")
    search_fields = ("room__room_number", "description", "assigned_user__full_name")
    list_filter = ("priority", "status", "created_at")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("type", "message", "user", "role", "emergency", "is_read", "created_at")
    search_fields = ("message", "user__full_name", "role__name", "emergency__room__room_number")
    list_filter = ("type", "is_read", "created_at")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
