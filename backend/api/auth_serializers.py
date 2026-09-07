"""
Serializers d'authentification.
"""

from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .models import Member


class RegisterSerializer(serializers.ModelSerializer):
    """Création de compte avec confirmation du mot de passe.

    Le profil métier est créé par un signal ; les champs de poste sont
    optionnels et appliqués juste après.
    """

    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    email = serializers.EmailField(required=True)
    job_title = serializers.CharField(required=False, allow_blank=True, write_only=True)
    department = serializers.ChoiceField(
        choices=Member.DEPARTMENT_CHOICES, required=False, write_only=True
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name',
                  'password', 'password_confirm', 'job_title', 'department')

    def validate_email(self, value):
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("Cet email est déjà utilisé.")
        return value

    def validate(self, attrs):
        if attrs['password'] != attrs.pop('password_confirm'):
            raise serializers.ValidationError(
                {'password_confirm': "Les mots de passe ne correspondent pas."}
            )
        return attrs

    def create(self, validated_data):
        job_title = validated_data.pop('job_title', '')
        department = validated_data.pop('department', None)

        user = User.objects.create_user(**validated_data)

        # `create_member_profile` a déjà créé le profil et l'a mis en cache sur
        # `user`. On modifie cette instance-là : repasser par une requête
        # créerait un second objet, et la réponse renverrait le profil périmé.
        try:
            member = user.member
        except Member.DoesNotExist:
            member = None

        if member and (job_title or department):
            member.job_title = job_title
            if department:
                member.department = department
            member.save(update_fields=['job_title', 'department', 'updated_at'])
        return user


class LoginSerializer(serializers.Serializer):
    """Vérifie les identifiants et expose l'utilisateur authentifié."""

    username = serializers.CharField()
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})

    def validate(self, attrs):
        user = authenticate(
            request=self.context.get('request'),
            username=attrs['username'],
            password=attrs['password'],
        )
        if user is None:
            raise serializers.ValidationError(
                "Nom d'utilisateur ou mot de passe incorrect.", code='authorization'
            )
        if not user.is_active:
            raise serializers.ValidationError("Ce compte est désactivé.", code='inactive')

        attrs['user'] = user
        return attrs


class ChangePasswordSerializer(serializers.Serializer):
    """Changement de mot de passe d'un utilisateur connecté."""

    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, validators=[validate_password])

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError("Mot de passe actuel incorrect.")
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        return user


class ProfileSerializer(serializers.ModelSerializer):
    """Profil de l'utilisateur courant, rôle métier compris."""

    display_name = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()
    role_label = serializers.SerializerMethodField()
    job_title = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    is_founder = serializers.SerializerMethodField()
    is_manager = serializers.SerializerMethodField()
    member_id = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'member_id', 'username', 'email', 'first_name', 'last_name',
                  'display_name', 'role', 'role_label', 'job_title', 'department',
                  'is_founder', 'is_manager', 'date_joined', 'last_login')
        read_only_fields = ('id', 'username', 'date_joined', 'last_login')

    def _member(self, obj):
        # L'accesseur inverse d'un OneToOne lève une exception au lieu de
        # renvoyer None quand le profil n'existe pas encore.
        try:
            return obj.member
        except Member.DoesNotExist:
            return None

    def get_member_id(self, obj):
        member = self._member(obj)
        return member.pk if member else None

    def get_display_name(self, obj):
        member = self._member(obj)
        return member.display_name if member else obj.username

    def get_role(self, obj):
        member = self._member(obj)
        return member.role if member else None

    def get_role_label(self, obj):
        member = self._member(obj)
        return member.get_role_display() if member else None

    def get_job_title(self, obj):
        member = self._member(obj)
        return member.job_title if member else ''

    def get_department(self, obj):
        member = self._member(obj)
        return member.get_department_display() if member else ''

    def get_is_founder(self, obj):
        member = self._member(obj)
        return bool(member and member.is_founder)

    def get_is_manager(self, obj):
        member = self._member(obj)
        return bool(member and member.is_manager)
