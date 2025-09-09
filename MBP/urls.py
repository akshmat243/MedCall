from rest_framework import routers
from django.urls import path, include
from .views import RoleViewSet, AppModelViewSet, PermissionTypeViewSet, RoleModelPermissionViewSet, AuditLogViewSet, RoleCategoryViewSet

router = routers.DefaultRouter()
router.register(r'role-categories', RoleCategoryViewSet, basename='role-categories')
router.register(r'roles', RoleViewSet, basename='roles')
router.register(r'appmodels', AppModelViewSet)
router.register(r'permission-types', PermissionTypeViewSet)
router.register(r'role-permissions', RoleModelPermissionViewSet)
router.register('logs', AuditLogViewSet, basename='auditlog')

urlpatterns = [
    path('api/', include(router.urls)),
]