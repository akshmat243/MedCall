from rest_framework import status
from rest_framework.response import Response
from django.contrib.auth import authenticate, logout, login
from rest_framework.permissions import IsAuthenticated
from MBP.models import RoleModelPermission
from accounts.models import UserRole
from accounts.serializers import UserSerializer, RegisterUserSerializer, UserRoleSerializer
from rest_framework.views import APIView
from MBP.utils import log_audit
from MBP.views import ProtectedModelViewSet
from django.contrib.auth import get_user_model

User = get_user_model()

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.throttling import UserRateThrottle


class UserViewSet(ProtectedModelViewSet):
    queryset = User.objects.all().order_by('-date_joined')
    serializer_class = UserSerializer
    model_name = 'User'
    lookup_field = 'slug'
    
    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return User.objects.all().order_by('-date_joined')
        return User.objects.filter(created_by=user).order_by('-date_joined')

class UserRoleViewSet(ProtectedModelViewSet):
    queryset = UserRole.objects.select_related('user', 'role').all().order_by('-assigned_at')
    serializer_class = UserRoleSerializer
    model_name = 'UserRole'
    lookup_field = 'slug'

class RegisterView(APIView):
    permission_classes = []

    def post(self, request):
        serializer = RegisterUserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            log_audit(
                request=request,
                action='create',
                model_name='User',
                object_id=user.id,
                details=f"User {user.email} registered manually.",
                new_data=serializer.data
            )
            return Response({
                "message": "Registered successfully. Awaiting admin approval.",
                "user_id": user.id
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = []
    throttle_classes = [UserRateThrottle]

    def post(self, request):
        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(request, email=email, password=password)

        if user is not None:
            if not user.is_active:
                return Response({"error": "Account is inactive."}, status=status.HTTP_403_FORBIDDEN)

            refresh = RefreshToken.for_user(user)

            log_audit(
                request=request,
                action='login',
                model_name='User',
                object_id=user.id,
                details=f"{user.email} logged in"
            )

            role_name = None
            accessible_models = []
            if hasattr(user, 'user_role') and user.user_role.role:
                role = user.user_role.role
                role_name = role.name
                role_perms = RoleModelPermission.objects.filter(role=role)
                for rp in role_perms:
                    accessible_models.append({
                        "model_name": rp.model.name,
                        "permission": rp.permission_type.code
                    })

            return Response({
                "refresh": str(refresh),
                "access": str(refresh.access_token),
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": role_name,
                    "permissions": accessible_models
                }
            }, status=status.HTTP_200_OK)

        return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)


from rest_framework_simplejwt.tokens import TokenError, AccessToken
from django.core.cache import cache
import datetime

class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        access_token = request.headers.get("Authorization", "").split(" ")[1]  # Extract access token

        if not refresh_token:
            return Response({"error": "Refresh token is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Blacklist refresh token
            token = RefreshToken(refresh_token)
            token.blacklist()

            # Blacklist access token by adding its jti to cache
            access = AccessToken(access_token)
            jti = access['jti']
            exp = access['exp']

            # Calculate expiry time from token
            expiry_time = datetime.datetime.fromtimestamp(exp) - datetime.datetime.now()
            cache.set(f"blacklisted_{jti}", True, timeout=expiry_time.total_seconds())

            log_audit(
                request=request,
                action='logout',
                model_name='User',
                object_id=request.user.id,
                details=f"{request.user.email} logged out."
            )

            return Response({"message": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)

        except TokenError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)





# class LoginView(APIView):
#     permission_classes = []

#     def post(self, request):
#         login_type = request.data.get("login_type", "simple")  # 'simple' or 'oauth'

#         if login_type == "simple":
#             email = request.data.get("email")
#             password = request.data.get("password")
#             user = authenticate(request, email=email, password=password)

#             if not user:
#                 return Response({"error": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)

#         elif login_type == "oauth":
#             email = request.data.get("email")
#             try:
#                 user = User.objects.get(email=email)
#             except User.DoesNotExist:
#                 return Response({"error": "User not found. Please register first."}, status=status.HTTP_404_NOT_FOUND)

#         else:
#             return Response({"error": "Invalid login type."}, status=status.HTTP_400_BAD_REQUEST)

#         if not user.is_active:
#             return Response({"error": "Account is inactive."}, status=status.HTTP_403_FORBIDDEN)

#         login(request, user)

#         log_audit(
#             request=request,
#             action='login',
#             model_name='User',
#             object_id=user.id,
#             details=f"{user.email} logged in via {login_type}"
#         )

#         # Role-based permission info
#         role = user.role
#         accessible_models = []
#         if role:
#             role_perms = RoleModelPermission.objects.filter(role=role)
#             for rp in role_perms:
#                 model_info = {
#                     "model_name": rp.model.name,
#                     "permission": rp.permission_type.code
#                 }
#                 accessible_models.append(model_info)

#         return Response({
#             "message": "Login successful.",
#             "user": {
#                 "id": str(user.id),
#                 "email": user.email,
#                 "full_name": user.full_name,
#                 "role": user.role.name if user.role else None,
#                 "permissions": accessible_models
#             }
#         }, status=status.HTTP_200_OK)


# class LogoutView(APIView):
#     permission_classes = [IsAuthenticated]

#     def post(self, request):
#         log_audit(
#             request=request,
#             action='logout',
#             model_name='User',
#             object_id=request.user.id,
#             details=f"{request.user.email} logged out."
#         )

#         logout(request)

#         return Response({"message": "Logged out successfully."}, status=status.HTTP_205_RESET_CONTENT)