from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Room, Patient, Emergency, Notification, Staff, StaffPerformance
from accounts.serializers import UserSerializer
from django.db.models import F, Avg, ExpressionWrapper, DurationField
from datetime import timedelta
from .utils import format_duration

User = get_user_model()


class PatientSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    class Meta:
        model = Patient
        fields = [
            "id",
            "slug",
            "full_name",
            "age",
            "gender",
            "contact_number",
            "medical_record_number",
        ]


class RoomSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    patient = PatientSerializer(read_only=True)
    patient_id = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(),
        source="patient",
        write_only=True,
        required=False,
    )
    patient_slug = serializers.SlugRelatedField(
        queryset=Patient.objects.all(),
        slug_field="slug",
        source="patient",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Room
        fields = [
            "id",
            "slug",
            "room_number",
            "floor",
            "ward",
            "bed_count",
            "is_occupied",
            "patient",
            "patient_id",
            "patient_slug",
            "last_call_priority",
        ]

class RoomStatsSerializer(serializers.Serializer):
    total_rooms = serializers.IntegerField()
    occupied_rooms = serializers.IntegerField()
    available_rooms = serializers.IntegerField()


class RoomWardStatsSerializer(serializers.Serializer):
    ward = serializers.CharField()
    total = serializers.IntegerField()
    occupied = serializers.IntegerField()
    available = serializers.IntegerField()


# class UserSerializer(serializers.ModelSerializer):
#     slug = serializers.SlugField(read_only=True)

#     class Meta:
#         model = User
#         fields = ["id", "slug", "username", "first_name", "last_name", "email"]


class EmergencySerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    room = RoomSerializer(read_only=True)
    room_id = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        source="room",
        write_only=True,
    )
    room_slug = serializers.SlugRelatedField(
        queryset=Room.objects.all(),
        slug_field="slug",
        source="room",
        write_only=True,
        required=False,
    )

    patient = PatientSerializer(read_only=True)
    patient_id = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(),
        source="patient",
        write_only=True,
        required=False,
        allow_null=True,
    )
    patient_slug = serializers.SlugRelatedField(
        queryset=Patient.objects.all(),
        slug_field="slug",
        source="patient",
        write_only=True,
        required=False,
        allow_null=True,
    )

    assigned_user = UserSerializer(read_only=True)
    assigned_user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="assigned_user",
        write_only=True,
        required=False,
        allow_null=True,
    )
    assigned_user_slug = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field="slug",
        source="assigned_user",
        write_only=True,
        required=False,
        allow_null=True,
    )

    accepted_by = UserSerializer(read_only=True)
    # accepted_by is set by accept endpoint

    class Meta:
        model = Emergency
        fields = [
            "id",
            "slug",
            "room",
            "room_id",
            "room_slug",
            "patient",
            "patient_id",
            "patient_slug",
            "description",
            "priority",
            "status",
            "assigned_user",
            "assigned_user_id",
            "assigned_user_slug",
            "accepted_by",
            "created_by",
            "created_at",
            "acknowledged_at",
            "accepted_at",
            "reached_at",
            "resolved_at",
        ]
        read_only_fields = (
            "created_by",
            "created_at",
            "acknowledged_at",
            "accepted_at",
            "reached_at",
            "resolved_at",
        )

    def create(self, validated_data):
        request = self.context.get("request")
        if request and hasattr(request, "user"):
            validated_data["created_by"] = request.user
        return super().create(validated_data)


class NotificationSerializer(serializers.ModelSerializer):
    slug = serializers.SlugField(read_only=True)

    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        source="user",
        write_only=True,
        required=False,
        allow_null=True,
    )
    user_slug = serializers.SlugRelatedField(
        queryset=User.objects.all(),
        slug_field="slug",
        source="user",
        write_only=True,
        required=False,
        allow_null=True,
    )

    emergency = EmergencySerializer(read_only=True)
    emergency_id = serializers.PrimaryKeyRelatedField(
        queryset=Emergency.objects.all(),
        source="emergency",
        write_only=True,
        required=False,
        allow_null=True,
    )
    emergency_slug = serializers.SlugRelatedField(
        queryset=Emergency.objects.all(),
        slug_field="slug",
        source="emergency",
        write_only=True,
        required=False,
        allow_null=True,
    )

    class Meta:
        model = Notification
        fields = [
            "id",
            "slug",
            "user",
            "user_id",
            "user_slug",
            "role",
            "emergency",
            "emergency_id",
            "emergency_slug",
            "type",
            "message",
            "is_read",
            "created_at",
            "read_at",
        ]
        

def format_duration(value):
    if not value or value == timedelta(0):
        return "0s"
    total_seconds = int(value.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


class StaffPerformanceModelSerializer(serializers.ModelSerializer):
    staff = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = StaffPerformance
        fields = [
            "id",
            "slug",
            "staff",
            "total_assigned",
            "resolved",
            "resolution_rate",
            "avg_response_time",
            "avg_resolution_time",
            "satisfaction_percent",
            "rating",
            "last_updated",
        ]
        read_only_fields = fields

    def get_staff(self, obj):
        user = obj.staff.user
        return {
            "id": getattr(user, "id", None),
            "full_name": user.get_full_name() if hasattr(user, "get_full_name") else str(user),
            "username": getattr(user, "username", None),
            "email": getattr(user, "email", None),
        }


class StaffPerformanceDynamicSerializer(serializers.Serializer):
    staff = serializers.CharField(read_only=True)
    total_assigned = serializers.IntegerField(read_only=True)
    resolved = serializers.IntegerField(read_only=True)
    resolution_rate = serializers.FloatField(read_only=True)
    avg_response_time = serializers.CharField(read_only=True)
    avg_resolution_time = serializers.CharField(read_only=True)
    satisfaction_percent = serializers.FloatField(read_only=True)
    rating = serializers.FloatField(read_only=True)
    last_updated = serializers.DateTimeField(read_only=True, required=False)

    def to_representation(self, staff_obj):
        perf = getattr(staff_obj, "performance", None)
        if perf:
            return StaffPerformanceModelSerializer(perf).data

        user = staff_obj.user
        qs = Emergency.objects.filter(assigned_user=user)

        total_assigned = qs.count()
        resolved = qs.filter(status="resolved").count()
        resolution_rate = (resolved / total_assigned * 100) if total_assigned else 0.0

        avg_response = (
            qs.exclude(acknowledged_at__isnull=True)
            .annotate(response_time=ExpressionWrapper(F("acknowledged_at") - F("created_at"), output_field=DurationField()))
            .aggregate(avg=Avg("response_time"))["avg"]
            or timedelta(0)
        )

        avg_resolution = (
            qs.exclude(resolved_at__isnull=True)
            .annotate(resolution_time=ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField()))
            .aggregate(avg=Avg("resolution_time"))["avg"]
            or timedelta(0)
        )

        return {
            "staff": staff_obj.user.get_full_name(),
            "total_assigned": total_assigned,
            "resolved": resolved,
            "resolution_rate": round(resolution_rate, 2),
            "avg_response_time": format_duration(avg_response),
            "avg_resolution_time": format_duration(avg_resolution),
            "satisfaction_percent": 0.0,  # can be updated later
            "rating": 0.0,                # can be updated later
            "last_updated": None,
        }


class StaffSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.PrimaryKeyRelatedField(queryset=Staff.objects.all(), source="user", write_only=True)
    performance = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Staff
        fields = [
            "id",
            "slug",
            "user",
            "user_id",
            "department",
            "contact_number",
            "is_available",
            "shift_start",
            "shift_end",
            "performance",
        ]

    def get_performance(self, obj):
        return StaffPerformanceDynamicSerializer().to_representation(obj)