"""
Permissions de Flux Gestion.

Règle de visibilité retenue : un membre accède à ses propres données, un
fondateur accède à celles de toute l'équipe.
"""

from rest_framework import permissions


def resolve_owner(obj):
    """Retrouve le membre propriétaire d'un objet, quel que soit son modèle."""
    if hasattr(obj, 'member_id'):
        return obj.member
    if hasattr(obj, 'objective'):
        return obj.objective.member
    if hasattr(obj, 'user'):  # l'objet est lui-même un Member
        return obj
    return None


class HasMemberProfile(permissions.BasePermission):
    """Exige un profil métier rattaché au compte."""

    message = ("Aucun profil d'équipe n'est rattaché à ce compte. "
               "Demandez à un fondateur de vous l'attribuer.")

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and getattr(request, 'member', None) is not None
        )


class IsOwnerOrFounder(permissions.BasePermission):
    """Lecture et écriture réservées au propriétaire, ou à un fondateur."""

    message = "Cet élément appartient à un autre membre de l'équipe."

    def has_object_permission(self, request, view, obj):
        member = getattr(request, 'member', None)
        if member is None:
            return False
        if member.is_founder:
            return True
        owner = resolve_owner(obj)
        return owner is not None and owner.pk == member.pk


class IsFounder(permissions.BasePermission):
    """Réservé aux fondateurs : vues d'équipe et administration."""

    message = "Cette vue est réservée aux fondateurs."

    def has_permission(self, request, view):
        member = getattr(request, 'member', None)
        return bool(member and member.is_founder)


class IsManager(permissions.BasePermission):
    """Réservé au gérant : paie et suivi du personnel.

    Ces données dépassent le pilotage de la performance : un fondateur voit
    l'avancement de son équipe, le gérant seul touche aux salaires et aux
    sanctions.
    """

    message = "Cette vue est réservée au gérant."

    def has_permission(self, request, view):
        member = getattr(request, 'member', None)
        return bool(member and member.is_manager)


class IsSelfOrFounder(permissions.BasePermission):
    """Un membre gère son propre profil ; un fondateur gère toute l'équipe.

    L'administration des comptes — création, rôle, désactivation — passe par
    l'API depuis que la direction en a besoin au quotidien ; les garde-fous
    (dernier fondateur, suppression de soi) vivent dans la vue.
    """

    message = "Cet élément appartient à un autre membre de l'équipe."

    def has_object_permission(self, request, view, obj):
        member = getattr(request, 'member', None)
        if member is None:
            return False
        if member.is_founder:
            return True
        if request.method in permissions.SAFE_METHODS:
            return obj.pk == member.pk
        return obj.pk == member.pk
