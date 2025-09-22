from .models import Room, Staff, Emergency, Notification, Patient
from .serializers import (
    RoomSerializer,
    StaffSerializer,
    EmergencySerializer,
    NotificationSerializer,
    PatientSerializer,
    StaffPerformanceModelSerializer,
    RoomStatsSerializer,
    RoomWardStatsSerializer,
    
)
import csv
from django.http import HttpResponse
from openpyxl import Workbook
from django.utils.dateparse import parse_date
from MBP.views import ProtectedModelViewSet
from rest_framework.decorators import action
from django.db.models import Count, Avg, F, ExpressionWrapper, DurationField, Q, Prefetch
from rest_framework.response import Response
from datetime import timedelta
from django.utils.timezone import now
from rest_framework import status
from django.db.models.functions import TruncDay
from .utils import recalc_staff_performance
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.contrib.auth import get_user_model

User = get_user_model()

class PatientViewSet(ProtectedModelViewSet):
    """
    Patient API.
    lookup_field = 'slug' (requires Patient.slug present)

    Prefetches related rooms/emergencies for efficiency.
    Endpoints:
        GET    /api/patients/{slug}/rooms/
        GET    /api/patients/{slug}/emergencies/?status=&priority=&from=&to=
        GET    /api/patients/{slug}/active_calls/
        GET    /api/patients/{slug}/latest_call/
        POST   /api/patients/{slug}/call/
        GET    /api/patients/{slug}/summary/
    """

    queryset = Patient.objects.prefetch_related(
        Prefetch("rooms", queryset=Room.objects.select_related("patient")),
        Prefetch("emergencies", queryset=Emergency.objects.select_related("room", "assigned_user")),
    ).all().order_by("full_name")

    serializer_class = PatientSerializer
    model_name = "Patient"
    lookup_field = "slug"

    # ------------------------
    # Rooms
    # ------------------------
    @action(detail=True, methods=["get"])
    def rooms(self, request, slug=None):
        """List rooms associated with the patient."""
        patient = self.get_object()
        rooms_qs = patient.rooms.all()
        serializer = RoomSerializer(rooms_qs, many=True, context={"request": request})
        return Response(serializer.data)

    # ------------------------
    # Emergencies
    # ------------------------
    @action(detail=True, methods=["get"])
    def emergencies(self, request, slug=None):
        """
        List emergencies for this patient.

        Query params:
          - status (comma separated)
          - priority (comma separated)
          - from / to (ISO dates, filters created_at__date)
        """
        patient = self.get_object()
        qs = patient.emergencies.select_related("room", "assigned_user").all()

        # filter by status
        status_q = request.query_params.get("status")
        if status_q:
            statuses = [s.strip() for s in status_q.split(",") if s.strip()]
            qs = qs.filter(status__in=statuses)

        # filter by priority
        priority_q = request.query_params.get("priority")
        if priority_q:
            priorities = [p.strip() for p in priority_q.split(",") if p.strip()]
            qs = qs.filter(priority__in=priorities)

        # optional date filters
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")
        if date_from:
            qs = qs.filter(created_at__date__gte=date_from)
        if date_to:
            qs = qs.filter(created_at__date__lte=date_to)

        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = EmergencySerializer(page, many=True, context={"request": request})
            return self.get_paginated_response(serializer.data)

        serializer = EmergencySerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    # ------------------------
    # Active Calls
    # ------------------------
    @action(detail=True, methods=["get"])
    def active_calls(self, request, slug=None):
        """Return active (non-resolved/cancelled) emergencies for this patient."""
        patient = self.get_object()
        active_qs = patient.emergencies.exclude(status__in=["resolved", "cancelled"]).select_related(
            "room", "assigned_user"
        )
        serializer = EmergencySerializer(active_qs, many=True, context={"request": request})
        return Response(serializer.data)

    # ------------------------
    # Latest Call
    # ------------------------
    @action(detail=True, methods=["get"])
    def latest_call(self, request, slug=None):
        """Return the most recent emergency for the patient (active or resolved)."""
        patient = self.get_object()
        latest = patient.emergencies.select_related("room", "assigned_user").order_by("-created_at").first()
        if not latest:
            return Response(None, status=status.HTTP_204_NO_CONTENT)
        serializer = EmergencySerializer(latest, context={"request": request})
        return Response(serializer.data)

    # ------------------------
    # Trigger Call
    # ------------------------
    @action(detail=True, methods=["post"])
    def call(self, request, slug=None):
        """
        Patient triggers a call.

        Payload:
        {
            "room_id": "<uuid>"           # optional (if multiple rooms exist)
            "room_slug": "room-101",      # optional
            "description": "Need assistance",
            "priority": "low|medium|high|critical"  # default "medium"
        }

        Returns: created Emergency object
        """
        patient = self.get_object()
        room = None
        room_id = request.data.get("room_id")
        room_slug = request.data.get("room_slug")
        description = request.data.get("description", "")
        priority = request.data.get("priority", "medium")

        # resolve room
        if room_id:
            try:
                room = Room.objects.get(id=room_id, patient=patient)
            except Room.DoesNotExist:
                return Response({"error": "Room not found for this patient."}, status=status.HTTP_404_NOT_FOUND)
        elif room_slug:
            try:
                room = Room.objects.get(slug=room_slug, patient=patient)
            except Room.DoesNotExist:
                return Response({"error": "Room not found for this patient."}, status=status.HTTP_404_NOT_FOUND)
        else:
            room = patient.rooms.first()
            if not room:
                return Response(
                    {"error": "Patient has no room assigned; please provide room_id."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # create emergency
        emergency = Emergency.objects.create(
            room=room,
            patient=patient,
            description=description,
            priority=priority,
            status="pending",
            created_by=None,  # TODO: set if patient users exist
        )

        # update room quick access field
        room.last_call_priority = priority
        room.save(update_fields=["last_call_priority"])

        # ------------------------
        # INJECT PERFORMANCE UPDATE
        # ------------------------
        if emergency.assigned_user:
            try:
                staff = Staff.objects.get(user=emergency.assigned_user)
                recalc_staff_performance(staff, store=True)
            except Staff.DoesNotExist:
                pass  # safe fail: assigned_user might not map to staff

        # send notification
        try:
            send_notification(
                message=f"New patient call in Room {room.room_number}: {description or 'No details'}",
                emergency=emergency,
                role=None,
                type="new_call",
            )
        except Exception:
            pass  # don’t fail API if notifications are off

        serializer = EmergencySerializer(emergency, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # ------------------------
    # Summary
    # ------------------------
    @action(detail=True, methods=["get"])
    def summary(self, request, slug=None):
        """
        Quick summary for dashboards:
          - rooms count
          - active calls count
          - last call info
        """
        patient = self.get_object()
        rooms_count = patient.rooms.count()
        active_calls = patient.emergencies.exclude(status__in=["resolved", "cancelled"]).count()
        last_call = patient.emergencies.order_by("-created_at").first()

        return Response(
            {
                "patient": PatientSerializer(patient, context={"request": request}).data,
                "rooms_count": rooms_count,
                "active_calls": active_calls,
                "last_call_priority": getattr(last_call, "priority", None),
                "last_call_at": getattr(last_call, "created_at", None),
            }
        )


class RoomViewSet(ProtectedModelViewSet):
    queryset = Room.objects.all().order_by("room_number")
    serializer_class = RoomSerializer
    model_name = "Room"
    lookup_field = "slug"

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """General room statistics"""
        total = self.queryset.count()
        occupied = self.queryset.filter(is_occupied=True).count()
        available = self.queryset.filter(is_occupied=False).count()

        serializer = RoomStatsSerializer({
            "total_rooms": total,
            "occupied_rooms": occupied,
            "available_rooms": available,
        })
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def ward_stats(self, request):
        """Breakdown of rooms by ward"""
        data = self.queryset.values("ward").annotate(
            total=Count("id"),
            occupied=Count("id", filter=Q(is_occupied=True)),
            available=Count("id", filter=Q(is_occupied=False)),
        )
        serializer = RoomWardStatsSerializer(data, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def emergency_stats(self, request, slug=None):
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
            qs.values("room__slug", "room__room_number", "room__ward")
            .annotate(total_emergencies=Count("id"))
            .order_by("-total_emergencies")[:10]
        )
        return Response(list(leaderboard))

    @action(detail=False, methods=["get"])
    def active_emergencies(self, request):
        """
        Show all active emergencies per room for dashboard.
        Active = not resolved/cancelled.
        """
        active_status = [
            "pending", "notified", "assigned", "accepted", "in_progress", "escalated"
        ]

        qs = Emergency.objects.filter(
            status__in=active_status
        ).select_related("room", "patient")

        serializer = EmergencySerializer(qs, many=True, context={"request": request})
        return Response(serializer.data)


class StaffViewSet(ProtectedModelViewSet):
    queryset = (
        Staff.objects
        .select_related("user", "performance")
        .prefetch_related("user__assigned_emergencies")
        .all()
        .order_by("user__full_name")
    )
    serializer_class = StaffSerializer
    model_name = "Staff"
    lookup_field = "slug"   # use slug for consistency

    @action(detail=False, methods=["get"])
    def available(self, request):
        """List available staff (on duty)"""
        qs = self.queryset.filter(is_available=True)
        serializer = self.get_serializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """General staff statistics"""
        total = self.queryset.count()
        available = self.queryset.filter(is_available=True).count()
        unavailable = total - available

        return Response({
            "total_staff": total,
            "available_staff": available,
            "unavailable_staff": unavailable,
        })

    @action(detail=True, methods=["get"])
    def performance(self, request, slug=None):
        """Return latest performance (auto-updated + stored) for a staff member"""
        staff = self.get_object()
        perf = recalc_staff_performance(staff, store=True)  # always update & save
        serializer = StaffPerformanceModelSerializer(perf, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def performance_summary(self, request):
        """Return stored & updated performance for all staff"""
        perfs = [recalc_staff_performance(staff, store=True) for staff in self.queryset]
        serializer = StaffPerformanceModelSerializer(perfs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def leaderboard(self, request):
        """
        Top staff by performance.
        Supports ?metric=calls|satisfaction|rating (default=calls).
        """
        metric = request.query_params.get("metric", "calls")
        perfs = [recalc_staff_performance(staff, store=True) for staff in self.queryset]

        if metric == "satisfaction":
            perfs.sort(key=lambda p: p.satisfaction_percent, reverse=True)
        elif metric == "rating":
            perfs.sort(key=lambda p: p.avg_rating, reverse=True)
        else:
            perfs.sort(key=lambda p: p.total_calls, reverse=True)

        top10 = perfs[:10]
        serializer = StaffPerformanceModelSerializer(top10, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=True, methods=["get"])
    def performance_trend(self, request, slug=None):
        """
        Return performance trend for staff (last 30 recalculations stored in StaffPerformance).
        """
        staff = self.get_object()
        trends = StaffPerformance.objects.filter(staff=staff).order_by("-updated_at")[:30]

        data = [{
            "date": t.updated_at.date(),
            "calls": t.total_calls,
            "satisfaction": t.satisfaction_percent,
            "rating": t.avg_rating,
        } for t in trends]

        return Response(data)


class EmergencyViewSet(ProtectedModelViewSet):
    queryset = Emergency.objects.select_related("patient", "assigned_staff").all().order_by("-created_at")
    serializer_class = EmergencySerializer
    model_name = "Emergency"
    lookup_field = "slug"

    @action(detail=True, methods=["post"])
    def resolve(self, request, slug=None):
        """Mark emergency as resolved and update staff performance"""
        emergency = self.get_object()
        emergency.status = "resolved"
        emergency.save()

        if emergency.assigned_staff:
            recalc_staff_performance(emergency.assigned_staff, store=True)

        return Response({"status": "resolved", "id": str(emergency.id)})

    @action(detail=False, methods=["get"])
    def active(self, request):
        """List all active emergencies"""
        qs = self.queryset.filter(status="active")
        serializer = self.get_serializer(qs, many=True, context={"request": request})
        return Response(serializer.data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """General emergency stats"""
        total = self.queryset.count()
        active = self.queryset.filter(status="active").count()
        resolved = self.queryset.filter(status="resolved").count()

        return Response({
            "total_emergencies": total,
            "active_emergencies": active,
            "resolved_emergencies": resolved,
        })




# class EmergencyViewSet(ProtectedModelViewSet):
#     queryset = Emergency.objects.select_related("room", "patient", "assigned_user", "accepted_by").all()
#     serializer_class = EmergencySerializer
#     model_name = "Emergency"
#     lookup_field = "slug"
    
#     @action(detail=False, methods=["get"])
#     def stats(self, request):
#         """Overall statistics for emergencies"""
#         qs = self.queryset

#         total = qs.count()
#         resolved = qs.filter(status="resolved").count()
#         unresolved = qs.exclude(status="resolved").count()

#         avg_response = qs.annotate(
#             response_time=ExpressionWrapper(
#                 F("acknowledged_at") - F("created_at"),
#                 output_field=DurationField()
#             )
#         ).aggregate(avg_response=Avg("response_time"))["avg_response"]

#         avg_resolution = qs.annotate(
#             resolution_time=ExpressionWrapper(
#                 F("resolved_at") - F("created_at"),
#                 output_field=DurationField()
#             )
#         ).aggregate(avg_resolution=Avg("resolution_time"))["avg_resolution"]

#         return Response({
#             "total_emergencies": total,
#             "resolved": resolved,
#             "unresolved": unresolved,
#             "avg_response_time": avg_response,
#             "avg_resolution_time": avg_resolution,
#         })

#     @action(detail=False, methods=["get"])
#     def by_priority(self, request):
#         """Breakdown of emergencies by priority"""
#         qs = self.queryset.values("priority").annotate(
#             total=Count("id"),
#             resolved=Count("id", filter=F("status") == "resolved"),
#         )
#         return Response(list(qs))

#     @action(detail=False, methods=["get"])
#     def active(self, request):
#         """List currently active (unresolved) emergencies"""
#         active_qs = self.queryset.exclude(status="resolved")
#         serializer = self.get_serializer(active_qs, many=True)
#         return Response(serializer.data)

#     @action(detail=False, methods=["get"])
#     def staff_performance(self, request):
#         """Performance report for each staff member"""
#         qs = self.queryset.exclude(assigned_user__isnull=True)

#         performance = qs.values(
#             staff_id=F("assigned_user__id"),
#             staff_name=F("assigned_user__full_name"),
#             staff_role=F("assigned_user__staff__role"),
#         ).annotate(
#             total_assigned=Count("id"),
#             resolved=Count("id", filter=F("status") == "resolved"),
#             avg_response=Avg(
#                 ExpressionWrapper(F("acknowledged_at") - F("created_at"), output_field=DurationField())
#             ),
#             avg_resolution=Avg(
#                 ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())
#             ),
#         )

#         return Response(list(performance))
    
#     @action(detail=False, methods=["get"])
#     def bulk_report(self, request):
#         """
#         Download emergency report as CSV or Excel.
#         Filters:
#           - ?from=YYYY-MM-DD&to=YYYY-MM-DD   (date range)
#           - ?status=resolved                 (status filter)
#           - ?priority=high                   (priority filter)
#           - ?format=excel                    (default=csv)
#         """
#         qs = self.queryset.select_related("room", "patient", "assigned_user", "accepted_by")

#         # ---- Apply filters ----
#         from_date = request.query_params.get("from")
#         to_date = request.query_params.get("to")
#         status = request.query_params.get("status")
#         priority = request.query_params.get("priority")

#         if from_date:
#             from_date = parse_date(from_date)
#             if from_date:
#                 qs = qs.filter(created_at__date__gte=from_date)

#         if to_date:
#             to_date = parse_date(to_date)
#             if to_date:
#                 qs = qs.filter(created_at__date__lte=to_date)

#         if status:
#             qs = qs.filter(status=status)

#         if priority:
#             qs = qs.filter(priority=priority)

#         export_format = request.query_params.get("format", "csv").lower()

#         headers = [
#             "ID", "Room", "Patient", "Priority", "Status",
#             "Created At", "Resolved At", "Assigned To", "Accepted By"
#         ]

#         # ---------------- CSV Export ----------------
#         if export_format == "csv":
#             response = HttpResponse(content_type="text/csv")
#             response['Content-Disposition'] = 'attachment; filename="emergency_report.csv"'
#             writer = csv.writer(response)
#             writer.writerow(headers)

#             for e in qs:
#                 writer.writerow([
#                     e.id,
#                     e.room.room_number if e.room else "",
#                     e.patient.full_name if e.patient else "",
#                     e.priority,
#                     e.status,
#                     e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "",
#                     e.resolved_at.strftime("%Y-%m-%d %H:%M") if e.resolved_at else "",
#                     e.assigned_user.get_full_name() if e.assigned_user else "",
#                     e.accepted_by.get_full_name() if e.accepted_by else "",
#                 ])
#             return response

#         # ---------------- Excel Export ----------------
#         elif export_format == "excel":
#             wb = Workbook()
#             ws = wb.active
#             ws.title = "Emergency Report"

#             # Header row
#             ws.append(headers)

#             # Data rows
#             for e in qs:
#                 ws.append([
#                     str(e.id),
#                     e.room.room_number if e.room else "",
#                     e.patient.full_name if e.patient else "",
#                     e.priority,
#                     e.status,
#                     e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "",
#                     e.resolved_at.strftime("%Y-%m-%d %H:%M") if e.resolved_at else "",
#                     e.assigned_user.get_full_name() if e.assigned_user else "",
#                     e.accepted_by.get_full_name() if e.accepted_by else "",
#                 ])

#             response = HttpResponse(content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
#             response['Content-Disposition'] = 'attachment; filename="emergency_report.xlsx"'
#             wb.save(response)
#             return response

#         return Response({"error": "Invalid format. Use 'csv' or 'excel'."}, status=400)
    
#     def perform_create(self, serializer):
#         em = serializer.save()
#         # update room last_call_priority
#         em.room.last_call_priority = em.priority
#         em.room.save(update_fields=['last_call_priority'])
#         # optionally: create notification via signal (signals file will handle)
        
#     @action(detail=False, methods=["post"])
#     def patient_call(self, request):
#         """
#         Patient calls for emergency from their room.
#         Expected payload:
#         {
#             "room_id": "<room_uuid>",
#             "description": "Patient needs assistance",
#             "priority": "low|medium|high|critical"
#         }
#         """
#         room_id = request.data.get("room_id")
#         description = request.data.get("description", "")
#         priority = request.data.get("priority", "medium")

#         if not room_id:
#             return Response({"error": "room_id is required"}, status=status.HTTP_400_BAD_REQUEST)

#         try:
#             room = Room.objects.get(id=room_id)
#         except Room.DoesNotExist:
#             return Response({"error": "Room not found"}, status=status.HTTP_404_NOT_FOUND)

#         # Assign patient if available
#         patient = room.patient

#         emergency = Emergency.objects.create(
#             room=room,
#             patient=patient,
#             description=description,
#             priority=priority,
#             status="pending",
#             created_by=patient.user if hasattr(patient, "user") else None  # optional if patient has user
#         )

#         # Update room last_call_priority
#         room.last_call_priority = priority
#         room.save(update_fields=["last_call_priority"])

#         # Send notification to staff/admin (handled by signals)
#         from .utils import send_notification
#         send_notification(
#             message=f"New emergency call in Room {room.room_number}: {description}",
#             emergency=emergency,
#             role=None,  # all staff roles will get notification
#             type="new_call"
#         )

#         serializer = self.get_serializer(emergency)
#         return Response(serializer.data, status=status.HTTP_201_CREATED)

#     @action(detail=True, methods=['post'])
#     def assign(self, request, id=None):
#         """Admin assigns staff: { "assigned_user_id": "<uuid>" }"""
#         emergency = self.get_object()
#         user_id = request.data.get('assigned_user_id')
#         if not user_id:
#             return Response({"error": "assigned_user_id required"}, status=status.HTTP_400_BAD_REQUEST)
#         try:

#             user = User.objects.get(id=user_id)
#         except User.DoesNotExist:
#             return Response({"error": "user not found"}, status=status.HTTP_404_NOT_FOUND)
#         emergency.assigned_user = user
#         emergency.status = "assigned"
#         emergency.save(update_fields=["assigned_user", "status"])
#         # create notification to user (or role) - use helper
#         from .utils import send_notification
#         send_notification(message=f"You have been assigned emergency {emergency.id}", emergency=emergency, user=user, type="update")
#         return Response(self.get_serializer(emergency).data)

#     @action(detail=True, methods=['post'])
#     def accept(self, request, id=None):
#         """Staff accepts the assigned call - sets accepted_by, accepted_at"""
#         emergency = self.get_object()
#         user = request.user
#         if emergency.assigned_user and emergency.assigned_user != user:
#             return Response({"error": "This emergency is assigned to someone else"}, status=status.HTTP_403_FORBIDDEN)
#         emergency.accepted_by = user
#         emergency.accepted_at = now()
#         emergency.status = "accepted"
#         emergency.save(update_fields=["accepted_by", "accepted_at", "status"])
#         from .utils import send_notification
#         send_notification(message=f"{user.get_full_name()} accepted emergency {emergency.id}", emergency=emergency, type="update", role=None)
#         return Response(self.get_serializer(emergency).data)

#     @action(detail=True, methods=['post'])
#     def reach(self, request, id=None):
#         emergency = self.get_object()
#         emergency.reached_at = now()
#         emergency.status = "in_progress"
#         emergency.save(update_fields=["reached_at", "status"])
#         return Response(self.get_serializer(emergency).data)

#     @action(detail=True, methods=['post'])
#     def resolve(self, request, id=None):
#         emergency = self.get_object()
#         emergency.resolved_at = now()
#         emergency.status = "resolved"
#         emergency.save(update_fields=["resolved_at", "status"])
#         # notify creator/admins
#         from .utils import send_notification
#         send_notification(message=f"Emergency {emergency.id} resolved by {request.user.get_full_name()}", emergency=emergency, type="info")
#         return Response(self.get_serializer(emergency).data)

#     @action(detail=False, methods=['get'])
#     def active(self, request):
#         qs = self.queryset.exclude(status__in=["resolved", "cancelled"])
#         serializer = self.get_serializer(qs, many=True)
#         return Response(serializer.data)

#     @action(detail=False, methods=['get'])
#     def desk(self, request):
#         """Desk dashboard: rooms + current patient + latest active call priority"""
#         rooms = Room.objects.select_related("patient").all()
#         data = []
#         for r in rooms:
#             latest_call = r.emergencies.exclude(status__in=["resolved","cancelled"]).order_by("-created_at").first()
#             data.append({
#                 "room": RoomSerializer(r).data,
#                 "latest_call": EmergencySerializer(latest_call).data if latest_call else None
#             })
#         return Response(data)
    
#     @action(detail=False, methods=['get'])
#     def analytics_distribution(self, request):
#         """Calls by status and priority"""
#         qs = self.queryset
#         by_status = qs.values('status').annotate(count=Count('id'))
#         by_priority = qs.values('priority').annotate(count=Count('id'))
#         return Response({"by_status": list(by_status), "by_priority": list(by_priority)})

#     @action(detail=False, methods=['get'])
#     def calls_by_department(self, request):
#         """
#         Requires Staff/Users linked to department (user.profile.department or Staff model).
#         We'll join via Emergency.assigned_user -> StaffProfile (if exists).
#         """
#         from django.db.models import OuterRef, Subquery
#         # assume Staff model has user FK and department field
#         from .models import Staff as StaffProfile
#         staff_qs = StaffProfile.objects.filter(user=OuterRef('assigned_user')).values('department')[:1]
#         qs = self.queryset.annotate(department=Subquery(staff_qs))
#         data = qs.values('department').annotate(count=Count('id')).order_by('-count')
#         return Response(list(data))

#     @action(detail=False, methods=['get'])
#     def response_time_trends(self, request):
#         """
#         Return average response time grouped by day (last N days)
#         """
#         days = int(request.query_params.get("days", 14))
#         since = now() - timedelta(days=days)
#         qs = self.queryset.filter(created_at__gte=since).exclude(acknowledged_at__isnull=True)
#         qs = qs.annotate(response_time=ExpressionWrapper(F('acknowledged_at') - F('created_at'), output_field=DurationField()))
#         daily = qs.values(day=TruncDay('created_at')).annotate(avg_response=Avg('response_time')).order_by('day')
#         # TruncDay import: from django.db.models.functions import TruncDay
#         return Response(list(daily))




class NotificationViewSet(ProtectedModelViewSet):
    queryset = (
        Notification.objects
        .select_related("user", "role", "emergency")
        .all()
        .order_by("-created_at")
    )
    serializer_class = NotificationSerializer
    model_name = "Notification"
    lookup_field = "slug"   # switched to slug for consistency across your project

    # -------------------
    # Fetching
    # -------------------
    @action(detail=False, methods=["get"])
    def unread(self, request):
        """Fetch unread notifications for current user"""
        qs = self.queryset.filter(user=request.user, is_read=False)
        return Response(self.get_serializer(qs, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"])
    def read(self, request):
        """Fetch read notifications for current user"""
        qs = self.queryset.filter(user=request.user, is_read=True)
        return Response(self.get_serializer(qs, many=True, context={"request": request}).data)

    @action(detail=False, methods=["get"])
    def stats(self, request):
        """Notification count stats for current user"""
        qs = self.queryset.filter(user=request.user)
        stats = qs.aggregate(
            total=Count("id"),
            unread=Count("id", filter=Q(is_read=False)),
        )
        stats["read"] = stats["total"] - stats["unread"]
        return Response(stats)

    # -------------------
    # Updating
    # -------------------
    @action(detail=True, methods=["post"])
    def mark_read(self, request, slug=None):
        """Mark a notification as read"""
        notification = self.get_object()
        if not notification.is_read:
            notification.is_read = True
            notification.read_at = now()
            notification.save(update_fields=["is_read", "read_at"])
        return Response(self.get_serializer(notification, context={"request": request}).data)

    @action(detail=True, methods=["post"])
    def mark_unread(self, request, slug=None):
        """Optionally mark a notification as unread"""
        notification = self.get_object()
        if notification.is_read:
            notification.is_read = False
            notification.read_at = None
            notification.save(update_fields=["is_read", "read_at"])
        return Response(self.get_serializer(notification, context={"request": request}).data)

    # -------------------
    # Manual sending
    # -------------------
    @action(detail=False, methods=["post"])
    def send(self, request):
        """
        Send notification manually.
        Payload options:
        {
            "user_id": "<uuid>",               # optional if role/department is provided
            "role": "nurse | admin | staff",   # optional
            "department": "<id>",              # optional
            "type": "info | warning | emergency",
            "message": "Custom message",
            "emergency_id": "<uuid>"           # optional
        }
        """
        user_id = request.data.get("user_id")
        role = request.data.get("role")
        department = request.data.get("department")
        message = request.data.get("message")
        notif_type = request.data.get("type", "info")
        emergency_id = request.data.get("emergency_id")

        if not message:
            return Response({"error": "Message is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Validate emergency if provided
        emergency = None
        if emergency_id:
            emergency = Emergency.objects.filter(id=emergency_id).first()
            if not emergency:
                return Response({"error": "Invalid emergency_id."}, status=status.HTTP_400_BAD_REQUEST)

        notifications = []

        # Case 1: Send to single user
        if user_id:
            try:
                user = User.objects.get(id=user_id)
                role_obj = getattr(user, "role", None)
                notifications.append(Notification.objects.create(
                    user=user, role=role_obj, emergency=emergency,
                    type=notif_type, message=message
                ))
            except User.DoesNotExist:
                return Response({"error": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        # Case 2: Send to all staff in a role
        elif role:
            staff_qs = Staff.objects.filter(role__iexact=role)
            for staff in staff_qs:
                notifications.append(Notification.objects.create(
                    user=staff.user, role=staff.role, emergency=emergency,
                    type=notif_type, message=message
                ))

        # Case 3: Send to department staff
        elif department:
            staff_qs = Staff.objects.filter(department_id=department)
            for staff in staff_qs:
                notifications.append(Notification.objects.create(
                    user=staff.user, role=staff.role, emergency=emergency,
                    type=notif_type, message=message
                ))

        else:
            return Response({"error": "Must provide user_id, role, or department."},
                            status=status.HTTP_400_BAD_REQUEST)

        serializer = self.get_serializer(notifications, many=True, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)

