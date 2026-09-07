"""
Validateurs métier de Flux Gestion.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

#: Un objectif se pose pour le mois courant ou les mois proches, pas pour 2043.
MAX_MONTHS_AHEAD = 12
MAX_MONTHS_BACK = 36

#: Une période de rapport au-delà d'un an relève du bilan annuel, pas du suivi.
MAX_PERIOD_DAYS = 366


def validate_month_not_too_far(value):
    """Garde-fou sur le mois d'un objectif : évite les saisies aberrantes."""
    if value is None:
        return

    today = timezone.localdate()
    months_apart = (value.year - today.year) * 12 + (value.month - today.month)

    if months_apart > MAX_MONTHS_AHEAD:
        raise ValidationError(
            _("Un objectif ne peut pas être fixé plus de %(max)d mois à l'avance."),
            code='month_too_far',
            params={'max': MAX_MONTHS_AHEAD},
        )
    if months_apart < -MAX_MONTHS_BACK:
        raise ValidationError(
            _("Ce mois est trop ancien (au-delà de %(max)d mois)."),
            code='month_too_old',
            params={'max': MAX_MONTHS_BACK},
        )


def validate_period_order(start, end):
    """Vérifie la cohérence d'une période de rapport."""
    if start is None or end is None:
        return

    if start > end:
        raise ValidationError(
            _("La date de début doit précéder la date de fin."),
            code='invalid_range',
        )
    if end - start > timedelta(days=MAX_PERIOD_DAYS):
        raise ValidationError(
            _("La période couverte ne peut pas dépasser un an."),
            code='period_too_long',
        )


def validate_positive_amount(value):
    """Un montant de chiffre d'affaires ne peut pas être négatif."""
    if value is not None and value < 0:
        raise ValidationError(
            _("Le montant doit être positif."),
            code='negative_amount',
        )


def validate_progress(value):
    """Un avancement s'exprime entre 0 et 100."""
    if value is not None and not 0 <= value <= 100:
        raise ValidationError(
            _("L'avancement doit être compris entre 0 et 100."),
            code='invalid_progress',
        )
