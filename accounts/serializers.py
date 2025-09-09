from rest_framework import serializers
from django.core.exceptions import ValidationError
from .models import User, Role, UserRole


class RegisterUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ['id', 'email', 'full_name', 'password']
        read_only_fields = ['id']

    def create(self, validated_data):
        password = validated_data.pop('password')
        user = User(**validated_data)
        user.set_password(password)
        user.is_active = False
        user.save()
        return user


# User Serializer
class UserSerializer(serializers.ModelSerializer):
    created_by = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'slug', 'password',
            'is_active', 'date_joined', 'created_by'
        ]
        read_only_fields = ['id', 'slug', 'date_joined', 'created_by']
        extra_kwargs = {
            'password': {'write_only': True, 'required': False}
        }

    def get_created_by(self, obj):
        return obj.created_by.email if obj.created_by else None

    def create(self, validated_data):
        password = validated_data.pop('password', None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        user.is_active = True
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        return instance



class UserRoleSerializer(serializers.ModelSerializer):
    user = serializers.SlugRelatedField(slug_field='slug', queryset=User.objects.all())
    role = serializers.SlugRelatedField(slug_field='slug', queryset=Role.objects.all())
    assigned_by = serializers.SlugRelatedField(slug_field='slug', read_only=True)

    class Meta:
        model = UserRole
        fields = ['id', 'user', 'role', 'assigned_at', 'assigned_by']
        read_only_fields = ['id', 'assigned_at', 'assigned_by']

    def validate(self, data):
        # Check if user already has a role
        if UserRole.objects.filter(user=data['user']).exists():
            raise serializers.ValidationError({
                'user': 'This user already has a role assigned.'
            })
        return data

    def create(self, validated_data):
        request = self.context.get('request')
        assigned_by = request.user if request else None

        try:
            user_role = UserRole.objects.create(assigned_by=assigned_by, **validated_data)
            return user_role
        except ValidationError as e:
            raise serializers.ValidationError({'error': str(e)})
