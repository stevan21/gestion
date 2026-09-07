"""
Signaux de Flux Gestion.

Ils garantissent qu'un compte a toujours un profil métier et gardent l'état
des objectifs cohérent avec la feuille de route.
"""

import logging

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .models import DailyTask, Member, MonthlyObjective, Report, RoadmapItem

logger = logging.getLogger(__name__)


@receiver(post_save, sender=User)
def create_member_profile(sender, instance, created, **kwargs):
    """Attache un profil métier à tout nouveau compte.

    Le premier compte créé devient fondateur : sans cela, personne ne pourrait
    consulter l'équipe sur une instance neuve.
    """
    if not created:
        return

    is_first = not Member.objects.exists()
    Member.objects.get_or_create(
        user=instance,
        defaults={
            'role': 'founder' if (is_first or instance.is_superuser) else 'member',
            'department': 'direction' if is_first else 'commercial',
        },
    )
    logger.info("Profil créé pour %s", instance.username)


@receiver(post_save, sender=MonthlyObjective)
def objective_saved(sender, instance, created, **kwargs):
    """Purge les synthèses mises en cache."""
    cache.delete_many(['team_overview', f'member_overview_{instance.member_id}'])
    if created:
        logger.info(
            "Objectifs %s posés par %s",
            instance.month_label, instance.member.display_name,
        )


@receiver(post_save, sender=RoadmapItem)
@receiver(post_delete, sender=RoadmapItem)
def roadmap_changed(sender, instance, **kwargs):
    """Un jalon modifié change l'avancement affiché de l'objectif."""
    cache.delete(f'member_overview_{instance.objective.member_id}')


@receiver(post_save, sender=DailyTask)
@receiver(post_delete, sender=DailyTask)
def task_changed(sender, instance, **kwargs):
    """Une tâche modifiée change le tableau de bord du membre."""
    cache.delete(f'member_overview_{instance.member_id}')


@receiver(post_save, sender=Report)
def report_saved(sender, instance, created, **kwargs):
    """Trace la soumission des rapports."""
    cache.delete('team_overview')
    if instance.status == 'submitted' and instance.submitted_at:
        logger.info(
            "Rapport %s soumis par %s",
            instance.label, instance.member.display_name,
        )
