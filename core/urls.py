from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoomViewSet, StaffViewSet, EmergencyViewSet, NotificationViewSet, PatientViewSet

router = DefaultRouter()
router.register(r"rooms", RoomViewSet)
router.register(r"staff", StaffViewSet)
router.register(r"emergencies", EmergencyViewSet)
router.register(r"notifications", NotificationViewSet)
router.register(r"patients", PatientViewSet, basename="patient")

urlpatterns = [
    path("", include(router.urls)),
]
