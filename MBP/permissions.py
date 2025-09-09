from rest_framework.permissions import BasePermission
from .models import RoleModelPermission, AppModel, PermissionType

class HasModelPermission(BasePermission):
    def has_permission(self, request, view):
        if request.user.is_superuser:
            return True

        role = getattr(request.user, 'role', None)
        if not role:
            return False

        # Auto infer model_name from view's queryset
        model_name = getattr(view, 'model_name', None)
        if not model_name and hasattr(view, 'queryset'):
            model_class = view.queryset.model
            model_name = model_class.__name__  # Use class name like 'Hotel', 'Room'

        permission_code = getattr(view, 'permission_code', None)
        if not model_name or not permission_code:
            return False

        try:
            model_obj = AppModel.objects.get(name__iexact=model_name)
            perm_type = PermissionType.objects.get(code=permission_code.lower())
            return RoleModelPermission.objects.filter(
                role=role,
                model=model_obj,
                permission_type=perm_type
            ).exists()
        except (AppModel.DoesNotExist, PermissionType.DoesNotExist):
            return False
