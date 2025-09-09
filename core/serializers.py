from rest_framework import serializers
from .models import Room, Staff, Emergency, Notification
from accounts.serializers import UserSerializer


class RoomSerializer(serializers.ModelSerializer):
    class Meta:
        model = Room
        fields = ["id", "room_number", "floor", "ward", "bed_count", "is_occupied"]


class StaffSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = Staff
        fields = [
            "id",
            "user",
            "department",
            "contact_number",
            "is_available",
            "shift_start",
            "shift_end",
        ]


class EmergencySerializer(serializers.ModelSerializer):
    room = RoomSerializer(read_only=True)
    assigned_user = UserSerializer(read_only=True)

    class Meta:
        model = Emergency
        fields = [
            "id",
            "room",
            "description",
            "priority",
            "status",
            "assigned_user",
            "created_at",
            "acknowledged_at",
            "resolved_at",
        ]


class NotificationSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    emergency = EmergencySerializer(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id",
            "user",
            "role",
            "emergency",
            "type",
            "message",
            "is_read",
            "created_at",
            "read_at",
        ]
