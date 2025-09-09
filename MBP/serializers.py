from rest_framework import serializers
from .models import RoleCategory, Role, AppModel, PermissionType, RoleModelPermission, AuditLog, RoleCategory
from django.utils.text import slugify


class RoleCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = RoleCategory
        fields = ['id', 'name', 'description', 'slug']
        read_only_fields = ['id', 'slug']

    def validate_name(self, value):
        qs = RoleCategory.objects.exclude(id=self.instance.id) if self.instance else RoleCategory.objects.all()
        if qs.filter(name=value).exists():
            raise serializers.ValidationError("A role category with this name already exists.")
        return value
    
    def validate(self, data):
        """
        Ensure slug is unique if it's being auto-generated from the name.
        """
        name = data.get('name', getattr(self.instance, 'name', None))
        slug = slugify(name)
        qs = RoleCategory.objects.exclude(id=self.instance.id) if self.instance else RoleCategory.objects.all()
        if qs.filter(slug=slug).exists():
            raise serializers.ValidationError({"slug": "Slug generated from name already exists."})
        return data


class RoleSerializer(serializers.ModelSerializer):
    category = RoleCategorySerializer(read_only=True)
    category_slug = serializers.SlugField(write_only=True)

    class Meta:
        model = Role
        fields = ['id', 'name', 'slug', 'description', 'category', 'category_slug']
        read_only_fields = ['id', 'slug']

    def validate_name(self, value):
        qs = Role.objects.exclude(id=self.instance.id) if self.instance else Role.objects.all()
        if qs.filter(name=value).exists():
            raise serializers.ValidationError("A role with this name already exists.")
        return value

    def create(self, validated_data):
        slug = validated_data.pop('category_slug')
        try:
            category = RoleCategory.objects.get(slug=slug)
        except RoleCategory.DoesNotExist:
            raise serializers.ValidationError({'category_slug': 'Invalid category slug.'})
        validated_data['category'] = category
        return super().create(validated_data)

    def update(self, instance, validated_data):
        slug = validated_data.pop('category_slug', None)
        if slug:
            try:
                category = RoleCategory.objects.get(slug=slug)
                validated_data['category'] = category
            except RoleCategory.DoesNotExist:
                raise serializers.ValidationError({'category_slug': 'Invalid category slug.'})
        return super().update(instance, validated_data)



class AppModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppModel
        fields = ['id', 'name', 'slug', 'verbose_name', 'description', 'app_label']
        read_only_fields = ['id', 'slug']

    def validate_name(self, value):
        qs = AppModel.objects.exclude(id=self.instance.id) if self.instance else AppModel.objects.all()
        if qs.filter(name=value).exists():
            raise serializers.ValidationError("A model with this name already exists.")
        return value


class PermissionTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PermissionType
        fields = ['id', 'name', 'slug', 'code']
        read_only_fields = ['id', 'slug']

    def validate_code(self, value):
        allowed_codes = ['c', 'r', 'u', 'd']
        if value not in allowed_codes:
            raise serializers.ValidationError("Code must be one of 'c', 'r', 'u', 'd'.")
        return value

    def validate_name(self, value):
        qs = PermissionType.objects.exclude(id=self.instance.id) if self.instance else PermissionType.objects.all()
        if qs.filter(name=value).exists():
            raise serializers.ValidationError("Permission type with this name already exists.")
        return value


class RoleModelPermissionSerializer(serializers.ModelSerializer):
    role = serializers.SlugRelatedField(slug_field='slug', queryset=Role.objects.all())
    model = serializers.SlugRelatedField(slug_field='slug', queryset=AppModel.objects.all())
    permission_type = serializers.SlugRelatedField(slug_field='slug', queryset=PermissionType.objects.all())

    role_name = serializers.CharField(source='role.name', read_only=True)
    model_name = serializers.CharField(source='model.name', read_only=True)
    permission_name = serializers.CharField(source='permission_type.name', read_only=True)

    class Meta:
        model = RoleModelPermission
        fields = [
            'id', 'role', 'model', 'permission_type',
            'role_name', 'model_name', 'permission_name'
        ]
        read_only_fields = ['id', 'role_name', 'model_name', 'permission_name']

    def validate(self, data):
        role = data.get('role')
        model = data.get('model')
        permission = data.get('permission_type')

        exists = RoleModelPermission.objects.filter(
            role=role, model=model, permission_type=permission
        )
        if self.instance:
            exists = exists.exclude(id=self.instance.id)

        if exists.exists():
            raise serializers.ValidationError("Permission already assigned to this role for this model.")
        return data


class AuditLogSerializer(serializers.ModelSerializer):
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = AuditLog
        fields = [
            'id', 'user', 'user_email', 'action', 'model_name',
            'object_id', 'details', 'old_data', 'new_data',
            'ip_address', 'user_agent', 'timestamp'
        ]
        read_only_fields = fields  # All fields are read-only to prevent tampering
