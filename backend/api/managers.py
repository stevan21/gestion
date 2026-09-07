"""
Managers personnalisés de Flux Gestion.

Ils portent les règles de visibilité (un membre voit ses données, un fondateur
voit toute l'équipe) et les filtres temporels réutilisés par les vues, les
tâches Celery et les commandes.
"""

from datetime import date, timedelta

from django.db import models
from django.utils import timezone


def month_start(value=None):
    """Premier jour du mois de la date donnée (aujourd'hui par défaut)."""
    reference = value or timezone.localdate()
    return reference.replace(day=1)


def month_range(months_back=0, reference=None):
    """Bornes (début, fin incluse) d'un mois situé N mois en arrière."""
    start = month_start(reference)
    index = start.year * 12 + (start.month - 1) - months_back
    start = date(index // 12, index % 12 + 1, 1)

    if start.month == 12:
        next_start = date(start.year + 1, 1, 1)
    else:
        next_start = date(start.year, start.month + 1, 1)
    return start, next_start - timedelta(days=1)


class MemberQuerySet(models.QuerySet):
    """QuerySet chaînable pour les membres de l'équipe."""

    def founders(self):
        return self.filter(role='founder')

    def managers(self):
        return self.filter(role='manager')

    def active(self):
        return self.filter(user__is_active=True)

    def visible_to(self, member):
        """Un fondateur voit toute l'équipe, un membre ne voit que lui-même."""
        if member is None:
            return self.none()
        if member.is_founder:
            return self.all()
        return self.filter(pk=member.pk)

    def with_user(self):
        return self.select_related('user')


class MemberManager(models.Manager.from_queryset(MemberQuerySet)):
    """Manager du modèle Member."""

    def for_user(self, user):
        """Profil métier d'un utilisateur, ou None s'il n'en a pas encore."""
        if not user or not user.is_authenticated:
            return None
        return self.select_related('user').filter(user=user).first()


class OwnedByMemberQuerySet(models.QuerySet):
    """Base des objets rattachés à un membre, avec la règle de visibilité."""

    #: Chemin vers le membre propriétaire depuis ce modèle.
    member_path = 'member'

    def owned_by(self, member):
        return self.filter(**{self.member_path: member})

    def visible_to(self, member):
        if member is None:
            return self.none()
        if member.is_founder:
            return self.all()
        return self.owned_by(member)


class MonthlyObjectiveQuerySet(OwnedByMemberQuerySet):
    """QuerySet chaînable pour les objectifs mensuels."""

    def for_month(self, reference=None):
        return self.filter(month=month_start(reference))

    def current_month(self):
        return self.for_month()

    def last_months(self, count=6):
        """Objectifs des N derniers mois, mois courant inclus."""
        start, _ = month_range(months_back=max(0, count - 1))
        return self.filter(month__gte=start)

    def active(self):
        return self.filter(status='active')

    def closed(self):
        return self.filter(status='closed')

    def with_related(self):
        return self.select_related('member', 'member__user').prefetch_related('roadmap')


class MonthlyObjectiveManager(models.Manager.from_queryset(MonthlyObjectiveQuerySet)):
    """Manager du modèle MonthlyObjective."""

    def totals(self, queryset=None):
        """Cumuls d'équipe : CA et clients attendus contre réalisés."""
        source = queryset if queryset is not None else self.all()
        return source.aggregate(
            revenue_target=models.Sum('revenue_target'),
            revenue_achieved=models.Sum('revenue_achieved'),
            clients_target=models.Sum('clients_target'),
            clients_achieved=models.Sum('clients_achieved'),
            count=models.Count('id'),
        )


class RoadmapItemQuerySet(OwnedByMemberQuerySet):
    """QuerySet chaînable pour les jalons de feuille de route."""

    member_path = 'objective__member'

    def open(self):
        return self.exclude(status='done')

    def done(self):
        return self.filter(status='done')

    def blocked(self):
        return self.filter(status='blocked')

    def overdue(self):
        return self.open().filter(due_date__lt=timezone.localdate())

    def with_related(self):
        return self.select_related('objective', 'objective__member', 'objective__member__user')


class RoadmapItemManager(models.Manager.from_queryset(RoadmapItemQuerySet)):
    """Manager du modèle RoadmapItem."""


class DailyTaskQuerySet(OwnedByMemberQuerySet):
    """QuerySet chaînable pour les tâches quotidiennes."""

    def for_date(self, day=None):
        return self.filter(date=day or timezone.localdate())

    def today(self):
        return self.for_date()

    def open(self):
        return self.exclude(status='done')

    def done(self):
        return self.filter(status='done')

    def blocked(self):
        return self.filter(status='blocked')

    def late(self):
        """Tâches non terminées dont le jour est passé."""
        return self.open().filter(date__lt=timezone.localdate())

    def in_period(self, start, end):
        return self.filter(date__range=[start, end])

    def running(self):
        """Tâches en cours à l'instant : démarrées, pas encore terminées."""
        return self.filter(status='in_progress', started_at__isnull=False)

    def started(self):
        """Tâches dont le chronomètre a tourné, terminées ou non."""
        return self.filter(started_at__isnull=False)

    def with_related(self):
        return self.select_related('member', 'member__user', 'roadmap_item')


class DailyTaskManager(models.Manager.from_queryset(DailyTaskQuerySet)):
    """Manager du modèle DailyTask."""

    def completion_rate(self, queryset=None):
        """Part des tâches terminées, en pourcentage."""
        source = queryset if queryset is not None else self.all()
        total = source.count()
        if not total:
            return None
        return round(source.filter(status='done').count() / total * 100, 1)


class ReportQuerySet(OwnedByMemberQuerySet):
    """QuerySet chaînable pour les rapports."""

    def submitted(self):
        return self.filter(status='submitted')

    def drafts(self):
        return self.filter(status='draft')

    def of_type(self, period_type):
        return self.filter(period_type=period_type)

    def covering(self, day):
        return self.filter(period_start__lte=day, period_end__gte=day)

    def with_related(self):
        return self.select_related('member', 'member__user')


class ReportManager(models.Manager.from_queryset(ReportQuerySet)):
    """Manager du modèle Report."""


class ReactionQuerySet(models.QuerySet):
    """QuerySet chaînable pour les réactions."""

    member_path = 'member'

    def owned_by(self, member):
        return self.filter(member=member)

    def visible_to(self, member):
        """Chacun voit les réactions reçues ; la direction les voit toutes."""
        if member is None:
            return self.none()
        if member.is_founder:
            return self.all()
        return self.owned_by(member)

    def in_month(self, reference=None):
        start = month_start(reference)
        _, end = month_range(0, start)
        return self.filter(date__gte=start, date__lte=end)

    def total_points(self):
        """Somme des points, ou zéro si la sélection est vide."""
        return self.aggregate(total=models.Sum('points'))['total'] or 0

    def with_related(self):
        return self.select_related('member', 'member__user', 'author', 'author__user')


class ReactionManager(models.Manager.from_queryset(ReactionQuerySet)):
    """Manager du modèle Reaction."""


class SuggestionQuerySet(models.QuerySet):
    """QuerySet chaînable pour les suggestions.

    La visibilité s'écarte de la règle commune : un membre relit les siennes,
    un fondateur ou un gérant les lit toutes, puisque la boîte leur est
    adressée.
    """

    #: Chemin vers l'auteur, pour rester lisible dans les filtres.
    member_path = 'author'

    def owned_by(self, member):
        return self.filter(author=member)

    def visible_to(self, member):
        if member is None:
            return self.none()
        if member.is_founder:
            return self.all()
        return self.owned_by(member)

    def pending(self):
        """Suggestions que personne n'a encore ouvertes."""
        return self.filter(status='new')

    def with_related(self):
        return self.select_related('author', 'author__user', 'handled_by')


class SuggestionManager(models.Manager.from_queryset(SuggestionQuerySet)):
    """Manager du modèle Suggestion."""


class PayslipQuerySet(OwnedByMemberQuerySet):
    """QuerySet chaînable pour les bulletins de paie."""

    def visible_to(self, member):
        """La paie ne suit pas la règle commune.

        Un fondateur voit l'avancement de son équipe, pas ses salaires : seul
        le gérant lit toute la paie. Chacun consulte en revanche ses propres
        bulletins : un bulletin enregistré est un bulletin établi, il n'y a
        plus de brouillon à tenir à l'écart.
        """
        if member is None:
            return self.none()
        if member.is_manager:
            return self.all()
        return self.owned_by(member)

    def for_month(self, reference=None):
        return self.filter(month=month_start(reference))

    def with_related(self):
        return self.select_related('member', 'member__user')


class PayslipManager(models.Manager.from_queryset(PayslipQuerySet)):
    """Manager du modèle Payslip."""


class StaffEventQuerySet(OwnedByMemberQuerySet):
    """QuerySet chaînable pour les évènements de personnel."""

    def of_kind(self, kind):
        return self.filter(kind=kind)

    def in_month(self, reference=None):
        start = month_start(reference)
        _, end = month_range(0, start)
        return self.filter(date__gte=start, date__lte=end)

    def with_related(self):
        return self.select_related('member', 'member__user', 'recorded_by')


class StaffEventManager(models.Manager.from_queryset(StaffEventQuerySet)):
    """Manager du modèle StaffEvent."""


class LeaveRequestQuerySet(OwnedByMemberQuerySet):
    """QuerySet chaînable pour les demandes de congé."""

    def pending(self):
        return self.filter(status='pending')

    def approved(self):
        return self.filter(status='approved')

    def blocking(self):
        """Demandes qui occupent le calendrier : en attente ou accordées."""
        return self.filter(status__in=['pending', 'approved'])

    def counted(self):
        """Congés accordés qui entament le droit annuel."""
        return self.filter(kind='paid', status='approved')

    def in_year(self, year=None):
        """Demandes commencées dans l'année civile."""
        return self.filter(start_date__year=year or timezone.localdate().year)

    def in_period(self, start, end):
        """Demandes qui chevauchent la période, même partiellement."""
        return self.filter(start_date__lte=end, end_date__gte=start)

    def in_month(self, reference=None):
        start = month_start(reference)
        _, end = month_range(0, start)
        return self.in_period(start, end)

    def covering(self, day=None):
        """Demandes couvrant ce jour, accordées ou en attente."""
        jour = day or timezone.localdate()
        return self.blocking().filter(start_date__lte=jour, end_date__gte=jour)

    def total_days(self):
        """Somme des jours ouvrables demandés.

        Le décompte tombe les samedis et dimanches : il se calcule en Python,
        jour par jour, plutôt qu'en base où le calendrier n'existe pas.
        """
        return round(sum(demande.days for demande in self), 1)

    def with_related(self):
        return self.select_related('member', 'member__user', 'decided_by',
                                   'decided_by__user')


class LeaveRequestManager(models.Manager.from_queryset(LeaveRequestQuerySet)):
    """Manager du modèle LeaveRequest."""


class AttendanceQuerySet(OwnedByMemberQuerySet):
    """QuerySet chaînable pour les pointages."""

    def for_date(self, day=None):
        return self.filter(date=day or timezone.localdate())

    def today(self):
        return self.for_date()

    def open(self):
        """Journées entamées dont le départ n'est pas pointé."""
        return self.filter(check_out__isnull=True)

    def closed(self):
        return self.filter(check_out__isnull=False)

    def late(self):
        return self.filter(late_minutes__gt=0)

    def in_period(self, start, end):
        return self.filter(date__range=[start, end])

    def in_month(self, reference=None):
        start = month_start(reference)
        _, end = month_range(0, start)
        return self.in_period(start, end)

    def total_minutes(self):
        """Minutes de présence cumulées.

        La durée dépend de l'heure courante pour une journée encore ouverte :
        elle se somme en Python, comme elle s'affiche.
        """
        return sum(pointage.minutes for pointage in self)

    def with_related(self):
        return self.select_related('member', 'member__user')


class AttendanceManager(models.Manager.from_queryset(AttendanceQuerySet)):
    """Manager du modèle Attendance."""

    def hours_by_member(self, queryset=None):
        """Minutes et retards du mois, membre par membre."""
        source = queryset if queryset is not None else self.all()
        lignes = {}
        for pointage in source:
            ligne = lignes.setdefault(
                pointage.member_id, {'days': 0, 'minutes': 0, 'late_minutes': 0}
            )
            ligne['days'] += 1
            ligne['minutes'] += pointage.minutes
            ligne['late_minutes'] += pointage.late_minutes
        return lignes
