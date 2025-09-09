from .models import Room, Staff, Emergency, Notification
from .serializers import (
    RoomSerializer,
    StaffSerializer,
    EmergencySerializer,
    NotificationSerializer,
)
from MBP.views import ProtectedModelViewSet
from rest_framework.decorators import action
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField, Q
from rest_framework.response import Response
from datetime import timedelta
from django.utils.timezone import now
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()



class RoomViewSet(ProtectedModelViewSet):
    queryset = Room.objects.all().order_by("room_number")
    serializer_class = RoomSerializer
    model_name = "Room"
    lookup_field = "id"
    
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """General room statistics"""
        total = self.queryset.count()
        occupied = self.queryset.filter(is_occupied=True).count()
        available = self.queryset.filter(is_occupied=False).count()

        return Response({
            "total_rooms": total,
            "occupied_rooms": occupied,
            "available_rooms": available,
        })

    @action(detail=False, methods=["get"])
    def ward_stats(self, request):
        """Breakdown of rooms by ward"""
        data = self.queryset.values("ward").annotate(
            total=Count("id"),
            occupied=Count("id", filter=Q(is_occupied=True)),
            available=Count("id", filter=Q(is_occupied=False)),
        )
        return Response(list(data))

    @action(detail=True, methods=["get"])
    def emergency_stats(self, request, id=None):
        """Emergency statistics for a single room"""
        room = self.get_object()
        qs = Emergency.objects.filter(room=room)

        total_emergencies = qs.count()
        resolved = qs.filter(status="resolved").count()
        unresolved = total_emergencies - resolved

        return Response({
            "room": room.room_number,
            "total_emergencies": total_emergencies,
            "resolved": resolved,
            "unresolved": unresolved,
        })

    @action(detail=False, methods=["get"])
    def leaderboard(self, request):
        """
        Top rooms with most emergencies.
        Supports ?range=24h / 7d / 30d (default = all time)
        """
        time_range = request.query_params.get("range")
        qs = Emergency.objects.all()

        if time_range == "24h":
            qs = qs.filter(created_at__gte=now() - timedelta(hours=24))
        elif time_range == "7d":
            qs = qs.filter(created_at__gte=now() - timedelta(days=7))
        elif time_range == "30d":
            qs = qs.filter(created_at__gte=now() - timedelta(days=30))

        leaderboard = (
            qs.values("room__id", "room__room_number", "room__ward")
            .annotate(total_emergencies=Count("id"))
            .order_by("-total_emergencies")[:10]
        )
        return Response(list(leaderboard))


class StaffViewSet(ProtectedModelViewSet):
    queryset = Staff.objects.select_related("user").all().order_by("user__full_name")
    serializer_class = StaffSerializer
    model_name = "Staff"
    lookup_field = "id"
    
    @action(detail=False, methods=["get"])
    def active(self, request):
        """List active staff (available for duty)"""
        active_qs = self.queryset.filter(is_available=True)
        serializer = self.get_serializer(active_qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """General staff statistics"""
        total = self.queryset.count()
        active = self.queryset.filter(is_available=True).count()
        inactive = self.queryset.filter(is_available=False).count()

        return Response({
            "total_staff": total,
            "active_staff": active,
            "inactive_staff": inactive,
        })

    @action(detail=True, methods=["get"])
    def performance(self, request, id=None):
        """Get performance report for a single staff member"""
        staff = self.get_object()

        qs = Emergency.objects.filter(assigned_user=staff.user)

        total_assigned = qs.count()
        resolved = qs.filter(status="resolved").count()

        avg_response = qs.annotate(
            response_time=ExpressionWrapper(
                F("acknowledged_at") - F("created_at"),
                output_field=DurationField()
            )
        ).aggregate(avg=Avg("response_time"))["avg"]

        avg_resolution = qs.annotate(
            resolution_time=ExpressionWrapper(
                F("resolved_at") - F("created_at"),
                output_field=DurationField()
            )
        ).aggregate(avg=Avg("resolution_time"))["avg"]

        return Response({
            "staff": staff.user.get_full_name(),
            "total_assigned": total_assigned,
            "resolved": resolved,
            "avg_response_time": avg_response,
            "avg_resolution_time": avg_resolution,
        })


class EmergencyViewSet(ProtectedModelViewSet):
    queryset = Emergency.objects.select_related("room", "assigned_user").all().order_by("-created_at")
    serializer_class = EmergencySerializer
    model_name = "Emergency"
    lookup_field = "id"
    
    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Overall statistics for emergencies"""
        qs = self.queryset

        total = qs.count()
        resolved = qs.filter(status="resolved").count()
        unresolved = qs.exclude(status="resolved").count()

        avg_response = qs.annotate(
            response_time=ExpressionWrapper(
                F("acknowledged_at") - F("created_at"),
                output_field=DurationField()
            )
        ).aggregate(avg_response=Avg("response_time"))["avg_response"]

        avg_resolution = qs.annotate(
            resolution_time=ExpressionWrapper(
                F("resolved_at") - F("created_at"),
                output_field=DurationField()
            )
        ).aggregate(avg_resolution=Avg("resolution_time"))["avg_resolution"]

        return Response({
            "total_emergencies": total,
            "resolved": resolved,
            "unresolved": unresolved,
            "avg_response_time": avg_response,
            "avg_resolution_time": avg_resolution,
        })

    @action(detail=False, methods=["get"])
    def by_priority(self, request):
        """Breakdown of emergencies by priority"""
        qs = self.queryset.values("priority").annotate(
            total=Count("id"),
            resolved=Count("id", filter=F("status") == "resolved"),
        )
        return Response(list(qs))

    @action(detail=False, methods=["get"])
    def active(self, request):
        """List currently active (unresolved) emergencies"""
        active_qs = self.queryset.exclude(status="resolved")
        serializer = self.get_serializer(active_qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def staff_performance(self, request):
        """Performance report for each staff member"""
        qs = self.queryset.exclude(assigned_user__isnull=True)

        performance = qs.values(
            staff_id=F("assigned_user__id"),
            staff_name=F("assigned_user__full_name"),
            staff_role=F("assigned_user__staff__role"),
        ).annotate(
            total_assigned=Count("id"),
            resolved=Count("id", filter=F("status") == "resolved"),
            avg_response=Avg(
                ExpressionWrapper(F("acknowledged_at") - F("created_at"), output_field=DurationField())
            ),
            avg_resolution=Avg(
                ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
            ),
        )

        return Response(list(performance))


class NotificationViewSet(ProtectedModelViewSet):
    queryset = Notification.objects.select_related("user", "role", "emergency").all().order_by("-created_at")
    serializer_class = NotificationSerializer
    model_name = "Notification"
    lookup_field = "id"
    
    @action(detail=False, methods=["get"])
    def unread(self, request):
        """Fetch unread notifications for current user"""
        qs = self.queryset.filter(user=request.user, is_read=False)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def read(self, request):
        """Fetch read notifications for current user"""
        qs = self.queryset.filter(user=request.user, is_read=True)
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)

    # -------------------
    # 🔹 Updating
    # -------------------
    @action(detail=True, methods=["post"])
    def mark_read(self, request, id=None):
        """Mark a notification as read"""
        notification = self.get_object()
        notification.is_read = True
        notification.read_at = now()
        notification.save()
        serializer = self.get_serializer(notification)
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Notification count stats for user"""
        total = self.queryset.filter(user=request.user).count()
        unread = self.queryset.filter(user=request.user, is_read=False).count()
        read = total - unread
        return Response({
            "total_notifications": total,
            "unread": unread,
            "read": read,
        })

    # -------------------
    # 🔹 Manual sending
    # -------------------
    @action(detail=False, methods=["post"])
    def send(self, request):
        """
        Manually send a notification to a user.
        Expected payload:
        {
            "user_id": "<uuid>",
            "type": "info | warning | emergency",
            "message": "Custom message",
            "emergency_id": "<uuid>" (optional)
        }
        """
        user_id = request.data.get("user_id")
        message = request.data.get("message")
        notif_type = request.data.get("type", "info")
        emergency_id = request.data.get("emergency_id")

        if not user_id or not message:
            return Response({"error": "user_id and message are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response({"error": "User not found."},
                            status=status.HTTP_404_NOT_FOUND)

        notification = Notification.objects.create(
            user=user,
            role=getattr(user, "role", None),
            emergency_id=emergency_id,
            type=notif_type,
            message=message
        )
        serializer = self.get_serializer(notification)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
