from django.contrib import admin
from .models import (
    RoleCategory, Role, AppModel, PermissionType,
    RoleModelPermission, AuditLog
)

@admin.register(RoleCategory)
class RoleCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'description')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'category', 'description')
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ('name',)
    list_filter = ('category',)


@admin.register(AppModel)
class AppModelAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'verbose_name', 'app_label', 'description')
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ('name', 'verbose_name', 'app_label')


@admin.register(PermissionType)
class PermissionTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code')
    search_fields = ('name', 'code')


@admin.register(RoleModelPermission)
class RoleModelPermissionAdmin(admin.ModelAdmin):
    list_display = ('role_name', 'model_name', 'permission_name')
    list_filter = ('role', 'model', 'permission_type')
    search_fields = ('role__name', 'model__name', 'permission_type__name')

    def role_name(self, obj):
        return obj.role.name

    def model_name(self, obj):
        return obj.model.name

    def permission_name(self, obj):
        return obj.permission_type.name


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['timestamp', 'user', 'action', 'model_name', 'object_id']
    search_fields = ['user__email', 'action', 'model_name', 'details']
    list_filter = ['action', 'model_name', 'timestamp']
    readonly_fields = [field.name for field in AuditLog._meta.fields]
