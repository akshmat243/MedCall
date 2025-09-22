from datetime import timedelta
from django.db.models import Avg, F, ExpressionWrapper, DurationField
from django.utils.timezone import now

from .models import Notification, StaffPerformance, Emergency, Staff


# -------------------------
# 🔹 Notifications
# -------------------------
def send_notification(message, emergency=None, user=None, role=None, type="info"):
    """
    Utility to create notifications consistently.
    """
    return Notification.objects.create(
        user=user,
        role=role,
        emergency=emergency,
        type=type,
        message=message
    )


# -------------------------
# 🔹 Formatting Helpers
# -------------------------
def format_duration(td):
    """Return human friendly string for a timedelta (or '0s')."""
    if not td:
        return "0s"
    if isinstance(td, (int, float)):  # seconds fallback
        total_seconds = int(td)
    else:
        total_seconds = int(td.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


# -------------------------
# 🔹 Staff Performance Recalc
# -------------------------
def recalc_staff_performance(staff: Staff, store: bool = False):
    """
    Recalculate performance stats for a given staff.
    - If `store=True`, saves/updates in StaffPerformance table.
    - If `store=False`, returns dict (no DB write).
    """
    user = staff.user
    qs = Emergency.objects.filter(assigned_user=user)

    total_assigned = qs.count()
    resolved = qs.filter(status="resolved").count()
    resolution_rate = (resolved / total_assigned * 100) if total_assigned else 0.0

    avg_response = (
        qs.exclude(acknowledged_at__isnull=True)
        .annotate(
            response_time=ExpressionWrapper(
                F("acknowledged_at") - F("created_at"),
                output_field=DurationField(),
            )
        )
        .aggregate(avg=Avg("response_time"))["avg"]
        or timedelta(0)
    )

    avg_resolution = (
        qs.exclude(resolved_at__isnull=True)
        .annotate(
            resolution_time=ExpressionWrapper(
                F("resolved_at") - F("created_at"),
                output_field=DurationField(),
            )
        )
        .aggregate(avg=Avg("resolution_time"))["avg"]
        or timedelta(0)
    )

    if store:
        perf, _ = StaffPerformance.objects.update_or_create(
            staff=staff,
            defaults={
                "total_assigned": total_assigned,
                "resolved": resolved,
                "resolution_rate": round(resolution_rate, 2),
                "avg_response_time": avg_response,
                "avg_resolution_time": avg_resolution,
                "satisfaction_percent": 0.0,  # placeholder
                "rating": 0.0,                # placeholder
                "last_updated": now(),
            },
        )
        return perf

    return {
        "staff": staff,
        "total_assigned": total_assigned,
        "resolved": resolved,
        "resolution_rate": round(resolution_rate, 2),
        "avg_response_time": avg_response,
        "avg_resolution_time": avg_resolution,
        "satisfaction_percent": 0.0,
        "rating": 0.0,
        "last_updated": None,
    }
