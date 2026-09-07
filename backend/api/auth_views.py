"""
Vues d'authentification par token.
"""

from django.contrib.auth import logout as django_logout
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .auth_serializers import (
    ChangePasswordSerializer, LoginSerializer, ProfileSerializer, RegisterSerializer,
)


def _token_payload(user):
    token, _ = Token.objects.get_or_create(user=user)
    return {'token': token.key, 'user': ProfileSerializer(user).data}


class RegisterView(APIView):
    """POST /api/auth/register/ — crée un compte et retourne un token."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        return Response(_token_payload(user), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login/ — retourne le token d'authentification."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data['user']
        return Response(_token_payload(user))


class LogoutView(APIView):
    """POST /api/auth/logout/ — invalide le token courant."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        if request.user.is_authenticated and hasattr(request, 'session'):
            django_logout(request)
        return Response({'detail': 'Déconnecté.'}, status=status.HTTP_200_OK)


class ProfileView(APIView):
    """GET/PATCH /api/auth/me/ — profil de l'utilisateur courant."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ChangePasswordView(APIView):
    """POST /api/auth/change-password/ — remplace le mot de passe et le token."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data, context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        # Le token précédent est révoqué : le client doit utiliser le nouveau.
        Token.objects.filter(user=user).delete()
        return Response(_token_payload(user))
