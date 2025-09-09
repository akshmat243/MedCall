from rest_framework import viewsets
from .permissions import HasModelPermission
from .models import Role, AppModel, PermissionType, RoleModelPermission, AuditLog, RoleCategory
from .serializers import (
    RoleCategorySerializer,
    RoleSerializer,
    AppModelSerializer,
    PermissionTypeSerializer,
    RoleModelPermissionSerializer,
    AuditLogSerializer
)
from .utils import serialize_instance
from django.db.models.signals import post_save


class ProtectedModelViewSet(viewsets.ModelViewSet):
    model_name = None
    permission_code = 'r'
    permission_classes = [HasModelPermission]

    def get_permissions(self):
        if self.action == 'create':
            self.permission_code = 'c'
        elif self.action in ['update', 'partial_update']:
            self.permission_code = 'u'
        elif self.action == 'destroy':
            self.permission_code = 'd'
        else:
            self.permission_code = 'r'
        return [permission() for permission in self.permission_classes]

    def perform_create(self, serializer):
        serializer.context['request'] = self.request
        instance = serializer.save()
        instance._request_user = self.request.user
        post_save.send(sender=instance.__class__, instance=instance, created=True)
        # instance.save()

    def perform_update(self, serializer):
        instance = self.get_object()
        instance._old_data = serialize_instance(instance)
        instance._request_user = self.request.user
        updated_instance = serializer.save()
        updated_instance._request_user = self.request.user
        updated_instance._old_data = instance._old_data
        updated_instance.save()

    def perform_destroy(self, instance):
        instance._request_user = self.request.user
        instance.delete()


class RoleCategoryViewSet(ProtectedModelViewSet):
    queryset = RoleCategory.objects.all()
    serializer_class = RoleCategorySerializer
    model_name = 'RoleCategory'
    lookup_field = 'slug'


class RoleViewSet(ProtectedModelViewSet):
    queryset = Role.objects.all()
    serializer_class = RoleSerializer
    model_name = 'Role'
    lookup_field = 'slug'


class AppModelViewSet(ProtectedModelViewSet):
    queryset = AppModel.objects.all()
    serializer_class = AppModelSerializer
    model_name = 'AppModel'
    lookup_field = 'slug'


class PermissionTypeViewSet(ProtectedModelViewSet):
    queryset = PermissionType.objects.all()
    serializer_class = PermissionTypeSerializer
    model_name = 'PermissionType'
    lookup_field = 'slug'


class RoleModelPermissionViewSet(ProtectedModelViewSet):
    queryset = RoleModelPermission.objects.select_related('role', 'model', 'permission_type').all()
    serializer_class = RoleModelPermissionSerializer
    model_name = 'RoleModelPermission'
    lookup_field = 'slug'


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all().order_by('-timestamp')
    serializer_class = AuditLogSerializer
    model_name = 'AuditLog'
    permission_classes = [HasModelPermission]
    permission_code = 'r'  # read-only

    def get_queryset(self):
        queryset = super().get_queryset()
        user_email = self.request.query_params.get('user')
        action = self.request.query_params.get('action')

        if user_email:
            queryset = queryset.filter(user__email__icontains=user_email)
        if action:
            queryset = queryset.filter(action=action)
        return queryset
