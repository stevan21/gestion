"""
Tâches Celery de Flux Gestion.

Sans broker configuré, les settings activent le mode eager : ces tâches
s'exécutent en ligne et l'application reste utilisable sans worker.
"""

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .formatting import format_fcfa

logger = logging.getLogger(__name__)


@shared_task
def open_monthly_objectives():
    """Reconduit les objectifs du mois précédent en brouillon pour le mois courant.

    Chacun ajuste ensuite ses chiffres : l'idée est d'éviter la page blanche
    le premier du mois, pas de figer des cibles.
    """
    from api.managers import month_range, month_start
    from api.models import Member, MonthlyObjective

    current = month_start()
    previous, _ = month_range(months_back=1)
    created = 0

    for member in Member.objects.active():
        if MonthlyObjective.objects.filter(member=member, month=current).exists():
            continue

        last = MonthlyObjective.objects.filter(member=member, month=previous).first()
        MonthlyObjective.objects.create(
            member=member,
            month=current,
            revenue_target=last.revenue_target if last else 0,
            clients_target=last.clients_target if last else 0,
            status='draft',
            notes='Reconduit automatiquement, à ajuster.' if last else '',
        )
        created += 1

    logger.info("%s objectif(s) ouvert(s) pour %s", created, current)
    return f"{created} objectif(s) ouvert(s) pour {current:%m/%Y}"


@shared_task
def close_previous_month():
    """Clôture les objectifs du mois écoulé encore ouverts."""
    from api.managers import month_range
    from api.models import MonthlyObjective

    previous, _ = month_range(months_back=1)
    closed = MonthlyObjective.objects.filter(
        month=previous, status__in=['draft', 'active']
    ).update(status='closed', updated_at=timezone.now())

    logger.info("%s objectif(s) clôturé(s) pour %s", closed, previous)
    return f"{closed} objectif(s) clôturé(s)"


@shared_task
def notify_objectives_at_risk():
    """Alerte les fondateurs sur les membres en retard marqué sur leurs cibles."""
    from api.managers import month_start
    from api.models import Member, MonthlyObjective

    objectives = MonthlyObjective.objects.filter(
        month=month_start(), status='active'
    ).select_related('member', 'member__user')

    at_risk = [obj for obj in objectives if obj.is_at_risk]
    if not at_risk:
        return "Aucun objectif en retard"

    recipients = list(
        Member.objects.founders().active()
        .exclude(user__email='')
        .values_list('user__email', flat=True)
    )
    if not recipients:
        logger.info("%s objectif(s) en retard, aucun fondateur joignable", len(at_risk))
        return f"{len(at_risk)} objectif(s) en retard, aucun destinataire"

    lines = [
        f"- {obj.member.display_name} : {obj.completion:.0f} % atteint "
        f"alors que {obj.elapsed_ratio:.0f} % du mois est écoulé "
        f"(CA {format_fcfa(obj.revenue_achieved)} / {format_fcfa(obj.revenue_target)})"
        for obj in at_risk
    ]
    send_mail(
        f"[Flux Gestion] {len(at_risk)} objectif(s) en retard",
        "Objectifs en retard sur le mois en cours :\n\n" + "\n".join(lines),
        settings.DEFAULT_FROM_EMAIL,
        recipients,
        fail_silently=True,
    )
    logger.info("Alerte envoyée pour %s objectif(s) en retard", len(at_risk))
    return f"{len(at_risk)} objectif(s) signalé(s)"


@shared_task
def remind_missing_reports(period_type='weekly'):
    """Rappelle aux membres n'ayant pas rendu leur rapport de la période."""
    from api.models import Member, Report

    today = timezone.localdate()
    if period_type == 'weekly':
        start = today - timedelta(days=today.weekday() + 7)
        end = start + timedelta(days=6)
    else:
        start = (today.replace(day=1) - timedelta(days=1)).replace(day=1)
        end = today.replace(day=1) - timedelta(days=1)

    reminded = 0
    for member in Member.objects.active().select_related('user'):
        if not member.user.email:
            continue
        already = Report.objects.filter(
            member=member, period_type=period_type,
            period_start__gte=start, period_end__lte=end, status='submitted',
        ).exists()
        if already:
            continue

        send_mail(
            "[Flux Gestion] Votre rapport est attendu",
            f"Bonjour {member.display_name},\n\n"
            f"Votre rapport pour la période du {start:%d/%m/%Y} au {end:%d/%m/%Y} "
            f"n'a pas encore été soumis.\n",
            settings.DEFAULT_FROM_EMAIL,
            [member.user.email],
            fail_silently=True,
        )
        reminded += 1

    logger.info("%s rappel(s) de rapport envoyé(s)", reminded)
    return f"{reminded} rappel(s) envoyé(s)"


@shared_task
def carry_over_late_tasks():
    """Reporte sur aujourd'hui les tâches en retard restées ouvertes."""
    from api.models import DailyTask

    today = timezone.localdate()
    moved = DailyTask.objects.late().update(date=today, updated_at=timezone.now())

    logger.info("%s tâche(s) reportée(s) sur %s", moved, today)
    return f"{moved} tâche(s) reportée(s)"


@shared_task
def close_stale_attendance():
    """Referme les pointages laissés ouverts les jours précédents.

    Un départ oublié n'est pas une journée sans fin : il se referme sur
    l'heure de fin prévue du membre, jamais sur l'heure courante, sans quoi le
    compteur du mois gonflerait de nuits entières.
    """
    from datetime import datetime

    from api.models import Attendance

    aujourdhui = timezone.localdate()
    fermes = 0

    for pointage in (Attendance.objects.open()
                     .filter(date__lt=aujourdhui).select_related('member')):
        prevue = timezone.make_aware(
            datetime.combine(pointage.date, pointage.member.work_ends_at)
        )
        pointage.close(max(prevue, pointage.check_in))
        fermes += 1

    logger.info("%s pointage(s) refermé(s) d'office", fermes)
    return f"{fermes} pointage(s) refermé(s)"


@shared_task
def cleanup_old_data(days=730):
    """Purge les tâches et rapports au-delà de la durée de conservation."""
    from api.models import DailyTask, Report

    cutoff = timezone.localdate() - timedelta(days=days)
    tasks, _ = DailyTask.objects.filter(date__lt=cutoff).delete()
    reports, _ = Report.objects.filter(period_end__lt=cutoff).delete()

    logger.info("Nettoyage : %s tâches et %s rapports supprimés", tasks, reports)
    return f"{tasks} tâche(s) et {reports} rapport(s) supprimé(s)"
