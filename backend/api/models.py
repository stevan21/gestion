"""
Modèles de Flux Gestion.

Le domaine est le suivi de performance d'une équipe de startup : chaque membre
pose ses objectifs du mois (chiffre d'affaires et clients attendus), détaille
sa feuille de route, planifie ses tâches quotidiennes et rend ses rapports.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from .managers import (
    AttendanceManager, DailyTaskManager, LeaveRequestManager, MemberManager,
    MonthlyObjectiveManager, PayslipManager, ReactionManager, ReportManager,
    RoadmapItemManager, StaffEventManager, SuggestionManager,
)


def first_day_of_month(value):
    """Ramène une date au premier jour de son mois."""
    return value.replace(day=1)


def working_days(start, end):
    """Jours ouvrables entre deux dates, bornes comprises.

    Le samedi et le dimanche ne comptent pas : un congé posé du vendredi au
    lundi retire deux jours au solde, pas quatre.
    """
    if start is None or end is None or end < start:
        return 0

    total = 0
    day = start
    while day <= end:
        if day.weekday() < 5:
            total += 1
        day += timedelta(days=1)
    return total


class Member(models.Model):
    """Profil métier d'un utilisateur : son rôle et sa place dans l'équipe."""

    ROLE_CHOICES = [
        ('founder', 'Fondateur'),
        ('manager', 'Gérant'),
        ('member', 'Membre'),
    ]

    #: Rôles voyant l'ensemble de l'équipe.
    TEAM_WIDE_ROLES = ('founder', 'manager')

    DEPARTMENT_CHOICES = [
        ('direction', 'Direction'),
        ('commercial', 'Commercial'),
        ('marketing', 'Marketing'),
        ('produit', 'Produit'),
        ('technique', 'Technique'),
        ('finance', 'Finance'),
        ('operations', 'Opérations'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='member')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    job_title = models.CharField('Poste', max_length=100, blank=True)
    department = models.CharField(
        'Pôle', max_length=20, choices=DEPARTMENT_CHOICES, default='commercial'
    )
    phone = models.CharField('Téléphone', max_length=30, blank=True)
    joined_on = models.DateField('Arrivée dans l\'équipe', default=timezone.localdate)

    # Rémunération de référence, portée par le profil : elle se consulte sans
    # attendre qu'un bulletin ait été établi, et sert de base à celui-ci.
    base_salary = models.DecimalField(
        'Salaire de base', max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )

    # Journée de référence : elle sert de repère au pointage. Arriver après
    # l'heure de début, tolérance passée, constitue un retard.
    work_starts_at = models.TimeField('Début de journée', default=time(8, 0))
    work_ends_at = models.TimeField('Fin de journée', default=time(17, 0))

    # Droit à congé annuel, en jours ouvrables : dix-huit jours, soit un jour
    # et demi par mois de service, l'usage en zone CEMAC.
    leave_entitlement = models.PositiveSmallIntegerField(
        'Congés annuels (jours)', default=18,
        validators=[MaxValueValidator(90)],
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MemberManager()

    class Meta:
        verbose_name = 'Membre'
        verbose_name_plural = 'Membres'
        ordering = ['user__first_name', 'user__username']

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        """Nom lisible : prénom + nom si renseignés, sinon identifiant."""
        full_name = self.user.get_full_name().strip()
        return full_name or self.user.username

    @property
    def is_founder(self):
        """Accès à l'ensemble de l'équipe : fondateur ou gérant.

        Le gérant reprend tout ce que voit un fondateur et y ajoute la gestion
        du personnel ; cette propriété gouverne la visibilité d'équipe, pas le
        titre porté par la personne.
        """
        return self.role in self.TEAM_WIDE_ROLES or self.user.is_staff

    @property
    def is_manager(self):
        """Un gérant tient la paie et le suivi disciplinaire du personnel."""
        return self.role == 'manager' or self.user.is_superuser

    @property
    def points_total(self):
        """Points cumulés depuis l'arrivée dans l'équipe."""
        return self.reactions.total_points()

    @property
    def points_month(self):
        """Points du mois en cours : ceux qui ouvrent la prime."""
        return self.reactions.in_month().total_points()

    @property
    def bonus_earned(self):
        """Prime acquise ce mois-ci par les points reçus.

        Des points négatifs n'entament pas le salaire : ils font retomber la
        prime à zéro, sans jamais la rendre débitrice.
        """
        return max(self.points_month, 0) * Reaction.POINT_VALUE

    @property
    def leave_days_taken(self):
        """Jours de congé payé accordés depuis le 1er janvier.

        Seul le congé payé entame le droit annuel : une maladie ou une absence
        exceptionnelle se pose sans être décomptée.
        """
        return self.leaves.counted().in_year().total_days()

    @property
    def leave_balance(self):
        """Solde de congés : le droit annuel, moins ce qui a été pris."""
        return round(self.leave_entitlement - self.leave_days_taken, 1)


class MonthlyObjective(models.Model):
    """Objectifs d'un membre pour un mois : chiffre d'affaires et clients."""

    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('active', 'En cours'),
        ('closed', 'Clôturé'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='objectives')
    month = models.DateField('Mois', help_text='Ramené au premier jour du mois')

    # Le chiffre d'affaires est un montant : Decimal, jamais un flottant.
    # Les montants sont exprimés en francs CFA ; les deux décimales conservées
    # en base absorbent un éventuel arrondi, elles ne sont pas affichées.
    revenue_target = models.DecimalField(
        'CA attendu', max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    revenue_achieved = models.DecimalField(
        'CA réalisé', max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    clients_target = models.PositiveIntegerField('Clients attendus', default=0)
    clients_achieved = models.PositiveIntegerField('Clients signés', default=0)

    focus = models.CharField(
        'Objectif principal', max_length=255, blank=True,
        help_text='La priorité du mois en une phrase',
    )
    notes = models.TextField('Commentaire', blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = MonthlyObjectiveManager()

    class Meta:
        verbose_name = 'Objectif mensuel'
        verbose_name_plural = 'Objectifs mensuels'
        ordering = ['-month', 'member__user__first_name']
        # Un seul jeu d'objectifs par membre et par mois.
        constraints = [
            models.UniqueConstraint(
                fields=['member', 'month'], name='unique_objective_per_member_month'
            ),
        ]
        indexes = [
            models.Index(fields=['-month'], name='api_objective_month_idx'),
            models.Index(fields=['member', '-month'], name='api_objective_member_idx'),
        ]

    def __str__(self):
        return f"{self.member.display_name} — {self.month:%m/%Y}"

    def save(self, *args, **kwargs):
        # Le mois est toujours stocké sur son premier jour : sans cette
        # normalisation, deux saisies du même mois créeraient deux objectifs.
        if self.month:
            self.month = first_day_of_month(self.month)
        super().save(*args, **kwargs)

    @property
    def month_label(self):
        return f"{self.month:%Y-%m}"

    @property
    def revenue_completion(self):
        """Part du CA attendu déjà réalisée, en pourcentage."""
        if not self.revenue_target:
            return None
        return round(float(self.revenue_achieved) / float(self.revenue_target) * 100, 1)

    @property
    def clients_completion(self):
        """Part des clients attendus déjà signés, en pourcentage."""
        if not self.clients_target:
            return None
        return round(self.clients_achieved / self.clients_target * 100, 1)

    @property
    def completion(self):
        """Avancement global : moyenne des cibles réellement fixées."""
        parts = [p for p in (self.revenue_completion, self.clients_completion)
                 if p is not None]
        if not parts:
            return None
        return round(sum(parts) / len(parts), 1)

    @property
    def elapsed_ratio(self):
        """Part du mois déjà écoulée, en pourcentage.

        Sert de référence : un mois à moitié écoulé attend ~50 % d'avancement.
        """
        today = timezone.localdate()
        start = self.month
        end = self.next_month_start() - timedelta(days=1)

        if today < start:
            return 0.0
        if today > end:
            return 100.0
        return round(today.day / end.day * 100, 1)

    @property
    def is_at_risk(self):
        """Vrai si l'avancement accuse un retard net sur le temps écoulé.

        La marge de 15 points évite de signaler un simple décalage de quelques
        jours, courant en début de mois.
        """
        progress = self.completion
        if progress is None or self.status == 'closed':
            return False
        return progress < self.elapsed_ratio - 15

    @property
    def revenue_gap(self):
        """Montant restant à réaliser pour atteindre la cible."""
        return max(self.revenue_target - self.revenue_achieved, Decimal('0'))

    def next_month_start(self):
        """Premier jour du mois suivant."""
        if self.month.month == 12:
            return date(self.month.year + 1, 1, 1)
        return date(self.month.year, self.month.month + 1, 1)


class RoadmapItem(models.Model):
    """Jalon de la feuille de route rattachée à un objectif mensuel."""

    STATUS_CHOICES = [
        ('todo', 'À faire'),
        ('in_progress', 'En cours'),
        ('done', 'Terminé'),
        ('blocked', 'Bloqué'),
    ]

    objective = models.ForeignKey(
        MonthlyObjective, on_delete=models.CASCADE, related_name='roadmap'
    )
    title = models.CharField('Jalon', max_length=200)
    description = models.TextField(blank=True)
    due_date = models.DateField('Échéance', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    progress = models.PositiveSmallIntegerField(
        'Avancement (%)', default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    position = models.PositiveSmallIntegerField('Ordre', default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = RoadmapItemManager()

    class Meta:
        verbose_name = 'Jalon de feuille de route'
        verbose_name_plural = 'Feuille de route'
        ordering = ['position', 'due_date', 'id']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        # Statut et avancement restent cohérents quel que soit le champ modifié.
        if self.status == 'done':
            self.progress = 100
            if self.completed_at is None:
                self.completed_at = timezone.now()
        else:
            self.completed_at = None
            if self.progress == 100:
                self.progress = 99
        super().save(*args, **kwargs)

    @property
    def is_overdue(self):
        return bool(
            self.due_date
            and self.status != 'done'
            and self.due_date < timezone.localdate()
        )


class DailyTask(models.Model):
    """Tâche qu'un membre se fixe pour une journée."""

    STATUS_CHOICES = [
        ('todo', 'À faire'),
        ('in_progress', 'En cours'),
        ('done', 'Terminée'),
        ('blocked', 'Bloquée'),
    ]

    # Priorité numérique : permet un tri par importance décroissante.
    PRIORITY_CHOICES = [
        (1, 'Basse'),
        (2, 'Normale'),
        (3, 'Haute'),
        (4, 'Urgente'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='tasks')
    date = models.DateField('Jour', default=timezone.localdate)
    title = models.CharField('Tâche', max_length=200)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='todo')
    priority = models.PositiveSmallIntegerField(choices=PRIORITY_CHOICES, default=2)

    # Rattachement facultatif : relie le quotidien à la feuille de route.
    roadmap_item = models.ForeignKey(
        RoadmapItem, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='tasks',
    )
    estimated_minutes = models.PositiveIntegerField(
        'Durée estimée (min)', null=True, blank=True
    )

    # Temps réellement passé : `started_at` est posé au démarrage,
    # `completed_at` à l'achèvement. L'écart donne la durée observée, à
    # comparer avec `estimated_minutes`.
    started_at = models.DateTimeField('Démarrée le', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    objects = DailyTaskManager()

    class Meta:
        verbose_name = 'Tâche du jour'
        verbose_name_plural = 'Tâches du jour'
        ordering = ['-date', '-priority', 'id']
        indexes = [
            models.Index(fields=['member', '-date'], name='api_task_member_date_idx'),
            models.Index(fields=['-date'], name='api_task_date_idx'),
        ]

    def __str__(self):
        return f"{self.date:%d/%m} — {self.title}"

    def save(self, *args, **kwargs):
        if self.status == 'done':
            if self.completed_at is None:
                self.completed_at = timezone.now()
            # Une tâche terminée sans départ connu : on prend l'achèvement
            # comme repère, plutôt que de laisser une durée impossible.
            if self.started_at is None:
                self.started_at = self.completed_at
        else:
            self.completed_at = None

        if self.status == 'in_progress' and self.started_at is None:
            self.started_at = timezone.now()

        super().save(*args, **kwargs)

    def start(self):
        """Démarre le chronomètre et passe la tâche en cours."""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.completed_at = None
        self.save(update_fields=['status', 'started_at', 'completed_at', 'updated_at'])
        return self

    @property
    def duration_minutes(self):
        """Minutes écoulées entre le départ et l'achèvement.

        Une tâche encore en cours compte le temps jusqu'à maintenant : c'est
        ce qui rend le compteur utile pendant qu'on travaille.
        """
        if self.started_at is None:
            return None
        fin = self.completed_at or timezone.now()
        return max(int((fin - self.started_at).total_seconds() // 60), 0)

    @property
    def duration_label(self):
        """Durée lisible : « 45 min », « 2 h 05 »."""
        minutes = self.duration_minutes
        if minutes is None:
            return ''
        if minutes < 60:
            return f"{minutes} min"
        return f"{minutes // 60} h {minutes % 60:02d}"

    @property
    def over_estimate(self):
        """Vrai si le temps passé dépasse l'estimation d'un quart."""
        if not self.estimated_minutes or self.duration_minutes is None:
            return False
        return self.duration_minutes > self.estimated_minutes * 1.25


class Report(models.Model):
    """Rapport rédigé par un membre : bilan de période, mission ou réunion."""

    PERIOD_CHOICES = [
        ('daily', 'Journalier'),
        ('weekly', 'Hebdomadaire'),
        ('monthly', 'Mensuel'),
        ('mission', 'Rapport de mission'),
        ('meeting', 'Rapport de réunion'),
    ]

    # Une mission et une réunion rendent compte d'un évènement daté, pas d'une
    # période de travail : elles portent un objet, un lieu et des participants,
    # là où un bilan hebdomadaire n'en a pas besoin.
    EVENT_TYPES = ('mission', 'meeting')

    STATUS_CHOICES = [
        ('draft', 'Brouillon'),
        ('submitted', 'Soumis'),
    ]

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='reports')
    period_type = models.CharField(
        'Type de rapport', max_length=20, choices=PERIOD_CHOICES, default='weekly'
    )
    period_start = models.DateField('Début de période')
    period_end = models.DateField('Fin de période')

    title = models.CharField('Objet', max_length=200, blank=True)
    location = models.CharField('Lieu', max_length=200, blank=True)
    participants = models.TextField('Participants', blank=True)

    summary = models.TextField('Bilan')
    achievements = models.TextField('Réalisations', blank=True)
    blockers = models.TextField('Difficultés', blank=True)
    decisions = models.TextField('Décisions', blank=True)
    next_steps = models.TextField('Prochaines étapes', blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    submitted_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = ReportManager()

    class Meta:
        verbose_name = 'Rapport'
        verbose_name_plural = 'Rapports'
        ordering = ['-period_end', '-created_at']
        indexes = [
            models.Index(fields=['member', '-period_end'], name='api_report_member_idx'),
        ]

    def __str__(self):
        return f"{self.label} — {self.member.display_name}"

    @property
    def is_event(self):
        """Un rapport de mission ou de réunion, par opposition à un bilan."""
        return self.period_type in self.EVENT_TYPES

    @property
    def label(self):
        """Intitulé lisible : l'objet s'il existe, le type sinon."""
        return self.title.strip() or self.get_period_type_display()

    def submit(self):
        """Marque le rapport comme rendu et horodate l'envoi."""
        self.status = 'submitted'
        self.submitted_at = timezone.now()
        self.save(update_fields=['status', 'submitted_at', 'updated_at'])
        return self


class Payslip(models.Model):
    """Bulletin de paie d'un membre pour un mois donné.

    Le bulletin n'a pas d'état intermédiaire : l'enregistrer, c'est l'établir.
    Un brouillon obligeait à une seconde manipulation pour rien, et retenait le
    bulletin loin du salarié à qui il est destiné.
    """

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='payslips')
    month = models.DateField('Mois', help_text='Ramené au premier jour du mois')

    # Tous les montants sont des Decimal, en francs CFA : une paie ne se calcule
    # pas en flottant, où 0,1 + 0,2 ne vaut pas 0,3.
    base_salary = models.DecimalField(
        'Salaire de base', max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    worked_hours = models.DecimalField(
        'Heures travaillées', max_digits=7, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Heures effectuées dans le mois, hors heures supplémentaires',
    )
    overtime_hours = models.DecimalField(
        'Heures supplémentaires', max_digits=6, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    overtime_amount = models.DecimalField(
        'Montant des heures supplémentaires', max_digits=12, decimal_places=2,
        default=Decimal('0'), validators=[MinValueValidator(Decimal('0'))],
    )
    bonuses = models.DecimalField(
        'Primes', max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    deductions = models.DecimalField(
        'Retenues', max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
        help_text='Absences, mises à pied sans solde, avances',
    )
    contributions = models.DecimalField(
        'Cotisations', max_digits=12, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )

    notes = models.TextField('Observations', blank=True)
    issued_at = models.DateTimeField('Établi le', null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PayslipManager()

    class Meta:
        verbose_name = 'Bulletin de paie'
        verbose_name_plural = 'Bulletins de paie'
        ordering = ['-month', 'member__user__first_name']
        constraints = [
            # Un seul bulletin par membre et par mois : deux bulletins pour le
            # même mois signifieraient un double paiement.
            models.UniqueConstraint(
                fields=['member', 'month'], name='unique_payslip_per_member_month'
            ),
        ]
        indexes = [
            models.Index(fields=['-month'], name='api_payslip_month_idx'),
            models.Index(fields=['member', '-month'], name='api_payslip_member_idx'),
        ]

    def __str__(self):
        return f"{self.member.display_name} — {self.month:%m/%Y}"

    def save(self, *args, **kwargs):
        if self.month:
            self.month = first_day_of_month(self.month)
        # Le bulletin porte sa date d'établissement dès le premier
        # enregistrement : elle date le document, pas sa dernière retouche.
        if self.issued_at is None:
            self.issued_at = timezone.now()
        super().save(*args, **kwargs)

    @property
    def month_label(self):
        return f"{self.month:%Y-%m}"

    @property
    def staff_events(self):
        """Retards, observations et mises à pied du mois, repris au bulletin.

        Le décompte de la paie ne se lit pas sans eux : une retenue s'explique
        par une absence, une prime par des heures faites. Ils sont rattachés au
        mois du bulletin, jamais saisis depuis lui — le suivi du personnel
        reste leur seule source.
        """
        return self.member.staff_events.in_month(self.month)

    @property
    def gross(self):
        """Salaire brut : base, heures supplémentaires et primes."""
        return self.base_salary + self.overtime_amount + self.bonuses

    @property
    def net(self):
        """Net à payer, une fois les retenues et cotisations déduites."""
        return self.gross - self.deductions - self.contributions


class StaffEvent(models.Model):
    """Évènement de personnel : mise à pied, observation, retard, heures sup."""

    KIND_CHOICES = [
        ('suspension', 'Mise à pied'),
        ('observation', 'Observation'),
        ('lateness', 'Retard'),
        ('overtime', 'Heures supplémentaires'),
    ]

    #: Évènements qui pèsent sur le dossier disciplinaire.
    DISCIPLINARY_KINDS = ('suspension', 'observation')

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='staff_events'
    )
    kind = models.CharField('Nature', max_length=20, choices=KIND_CHOICES)
    date = models.DateField('Date')
    end_date = models.DateField(
        'Fin', null=True, blank=True, help_text='Dernier jour d\'une mise à pied'
    )

    minutes = models.PositiveIntegerField(
        'Minutes de retard', null=True, blank=True
    )
    hours = models.DecimalField(
        'Heures supplémentaires', max_digits=6, decimal_places=2,
        null=True, blank=True, validators=[MinValueValidator(Decimal('0'))],
    )
    is_paid = models.BooleanField(
        'Avec solde', default=False,
        help_text='Mise à pied rémunérée, ou heures supplémentaires payées',
    )

    reason = models.TextField('Motif')
    decision = models.TextField('Suite donnée', blank=True)

    # L'auteur de la fiche est conservé : une sanction doit être imputable.
    recorded_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='staff_events_recorded',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = StaffEventManager()

    class Meta:
        verbose_name = 'Évènement de personnel'
        verbose_name_plural = 'Évènements de personnel'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['member', '-date'], name='api_staffevent_member_idx'),
            models.Index(fields=['kind', '-date'], name='api_staffevent_kind_idx'),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} — {self.member.display_name} ({self.date:%d/%m/%Y})"

    @property
    def is_disciplinary(self):
        return self.kind in self.DISCIPLINARY_KINDS

    @property
    def days(self):
        """Durée d'une mise à pied, bornes comprises."""
        if self.kind != 'suspension' or not self.end_date:
            return None
        return (self.end_date - self.date).days + 1

    @property
    def summary(self):
        """Quantité de l'évènement, dans son unité."""
        if self.kind == 'lateness' and self.minutes is not None:
            return f"{self.minutes} min"
        if self.kind == 'overtime' and self.hours is not None:
            return f"{self.hours:.2f} h".replace('.', ',')
        if self.kind == 'suspension' and self.days:
            return f"{self.days} jour{'s' if self.days > 1 else ''}"
        return ''


class Suggestion(models.Model):
    """Message déposé par un membre dans la boîte à suggestions."""

    CATEGORY_CHOICES = [
        ('idea', 'Idée'),
        ('problem', 'Problème'),
        ('question', 'Question'),
    ]

    STATUS_CHOICES = [
        ('new', 'Nouvelle'),
        ('read', 'Lue'),
        ('done', 'Traitée'),
    ]

    author = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='suggestions'
    )
    category = models.CharField(
        'Nature', max_length=20, choices=CATEGORY_CHOICES, default='idea'
    )
    message = models.TextField('Message')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='new')
    # La réponse et son auteur restent liés : une suite donnée doit être
    # imputable, comme pour une fiche de personnel.
    reply = models.TextField('Réponse', blank=True)
    handled_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='suggestions_handled',
    )
    handled_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = SuggestionManager()

    class Meta:
        verbose_name = 'Suggestion'
        verbose_name_plural = 'Suggestions'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='api_suggestion_idx'),
        ]

    def __str__(self):
        return f"{self.get_category_display()} — {self.author.display_name}"

    @property
    def excerpt(self):
        """Début du message, pour une liste ou une notification."""
        texte = ' '.join(self.message.split())
        return texte if len(texte) <= 90 else texte[:89] + '…'

    def mark(self, status, member=None, reply=''):
        """Change l'état de la suggestion et trace qui s'en est occupé."""
        self.status = status
        if reply:
            self.reply = reply
        if status == 'new':
            self.handled_by = None
            self.handled_at = None
        else:
            self.handled_by = member
            self.handled_at = timezone.now()
        self.save(update_fields=['status', 'reply', 'handled_by', 'handled_at',
                                 'updated_at'])
        return self


class Reaction(models.Model):
    """Points attribués par la direction à un membre de l'équipe.

    Une réaction dit ce qui est salué ou rappelé, et pèse en points. Le cumul
    du mois ouvre une prime, à raison de `POINT_VALUE` francs CFA par point.
    """

    #: Valeur d'un point, en francs CFA.
    POINT_VALUE = 2000

    #: Nature de la réaction et points accordés par défaut. Ils restent
    #: modifiables à la saisie : une même occasion ne pèse pas toujours pareil.
    KIND_CHOICES = [
        ('objectif', 'Objectif atteint'),
        ('bravo', 'Bravo'),
        ('entraide', 'Entraide'),
        ('initiative', 'Initiative'),
        ('rappel', 'Rappel à l\'ordre'),
        ('manquement', 'Manquement'),
    ]

    DEFAULT_POINTS = {
        'objectif': 20,
        'bravo': 10,
        'entraide': 5,
        'initiative': 15,
        'rappel': -5,
        'manquement': -15,
    }

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='reactions'
    )
    kind = models.CharField('Nature', max_length=20, choices=KIND_CHOICES)
    points = models.IntegerField(
        'Points', help_text='Négatif pour retirer des points'
    )
    reason = models.CharField('Motif', max_length=255, blank=True)
    date = models.DateField('Date', default=timezone.localdate)

    # L'auteur reste attaché : accorder ou retirer des points engage celui
    # qui le fait.
    author = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reactions_given',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects = ReactionManager()

    class Meta:
        verbose_name = 'Réaction'
        verbose_name_plural = 'Réactions'
        ordering = ['-date', '-created_at']
        indexes = [
            models.Index(fields=['member', '-date'], name='api_reaction_member_idx'),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.points:+d} — {self.member.display_name}"

    @property
    def is_positive(self):
        return self.points >= 0

    @property
    def value(self):
        """Contrepartie en francs CFA des points de cette réaction."""
        return self.points * self.POINT_VALUE


class LeaveRequest(models.Model):
    """Demande de congé ou d'absence, adressée à la direction.

    Le membre pose ses dates et son motif ; la direction accorde ou refuse.
    Tant que personne n'a tranché, la demande reste modifiable par son auteur.
    """

    KIND_CHOICES = [
        ('paid', 'Congé payé'),
        ('unpaid', 'Congé sans solde'),
        ('sick', 'Maladie'),
        ('special', 'Absence exceptionnelle'),
    ]

    #: Natures décomptées du droit annuel. Une maladie ou une absence
    #: exceptionnelle se pose sans entamer le solde.
    COUNTED_KINDS = ('paid',)

    STATUS_CHOICES = [
        ('pending', 'En attente'),
        ('approved', 'Accordée'),
        ('refused', 'Refusée'),
        ('cancelled', 'Annulée'),
    ]

    #: États qui occupent le calendrier : ils interdisent un chevauchement.
    BLOCKING_STATUSES = ('pending', 'approved')

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='leaves'
    )
    kind = models.CharField('Nature', max_length=20, choices=KIND_CHOICES,
                            default='paid')
    start_date = models.DateField('Premier jour')
    end_date = models.DateField('Dernier jour')
    half_day = models.BooleanField(
        'Demi-journée', default=False,
        help_text="Une seule journée, prise pour moitié",
    )

    reason = models.TextField('Motif')

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    # La réponse et son auteur restent liés : accorder ou refuser un congé
    # engage celui qui décide, comme une fiche de personnel.
    decision = models.TextField('Réponse', blank=True)
    decided_by = models.ForeignKey(
        Member, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='leaves_decided',
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = LeaveRequestManager()

    class Meta:
        verbose_name = 'Demande de congé'
        verbose_name_plural = 'Demandes de congé'
        ordering = ['-start_date', '-created_at']
        indexes = [
            models.Index(fields=['member', '-start_date'], name='api_leave_member_idx'),
            models.Index(fields=['status', '-start_date'], name='api_leave_status_idx'),
        ]

    def __str__(self):
        return (f"{self.get_kind_display()} — {self.member.display_name} "
                f"({self.start_date:%d/%m/%Y})")

    @property
    def days(self):
        """Jours ouvrables demandés ; une demi-journée en vaut la moitié."""
        if self.half_day and self.start_date == self.end_date:
            return 0.5 if self.start_date.weekday() < 5 else 0.0
        return float(working_days(self.start_date, self.end_date))

    @property
    def days_label(self):
        """Durée lisible : « 0,5 jour », « 3 jours »."""
        jours = self.days
        texte = f"{jours:.1f}".rstrip('0').rstrip('.').replace('.', ',')
        return f"{texte} jour{'s' if jours > 1 else ''}"

    @property
    def is_pending(self):
        return self.status == 'pending'

    @property
    def is_counted(self):
        """Vrai si la demande entame le droit à congé annuel."""
        return self.kind in self.COUNTED_KINDS

    def covers(self, day):
        """Vrai si la demande couvre ce jour, accordée ou en attente."""
        return (self.status in self.BLOCKING_STATUSES
                and self.start_date <= day <= self.end_date)

    def decide(self, status, member=None, decision=''):
        """Accorde, refuse ou annule la demande, et trace qui a tranché."""
        self.status = status
        if decision:
            self.decision = decision
        self.decided_by = member
        self.decided_at = timezone.now()
        self.save(update_fields=['status', 'decision', 'decided_by', 'decided_at',
                                 'updated_at'])
        return self


class Attendance(models.Model):
    """Pointage d'une journée : arrivée, départ et temps de présence.

    Une ligne par membre et par jour. Le retard se calcule à l'arrivée, contre
    l'heure de début portée par le profil : il n'est jamais saisi à la main.
    """

    #: Tolérance avant qu'une arrivée compte comme un retard.
    GRACE_MINUTES = 10

    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name='attendances'
    )
    date = models.DateField('Jour', default=timezone.localdate)
    check_in = models.DateTimeField('Arrivée')
    check_out = models.DateTimeField('Départ', null=True, blank=True)

    # Dérivé de l'arrivée, mais conservé : les synthèses du mois l'agrègent en
    # une requête au lieu de le recalculer ligne à ligne.
    late_minutes = models.PositiveIntegerField('Retard', default=0)
    note = models.CharField('Observation', max_length=200, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = AttendanceManager()

    class Meta:
        verbose_name = 'Pointage'
        verbose_name_plural = 'Pointages'
        ordering = ['-date', '-check_in']
        constraints = [
            # Une journée ne se pointe qu'une fois : deux lignes pour le même
            # jour compteraient les heures en double.
            models.UniqueConstraint(
                fields=['member', 'date'], name='unique_attendance_per_member_day'
            ),
        ]
        indexes = [
            models.Index(fields=['member', '-date'], name='api_attendance_member_idx'),
            models.Index(fields=['-date'], name='api_attendance_date_idx'),
        ]

    def __str__(self):
        return f"{self.member.display_name} — {self.date:%d/%m/%Y}"

    def save(self, *args, **kwargs):
        # Le retard suit l'arrivée, y compris quand la direction corrige un
        # pointage : la mesure ne doit jamais démentir l'heure affichée.
        self.late_minutes = self.lateness()
        champs = kwargs.get('update_fields')
        if champs is not None:
            kwargs['update_fields'] = list(set(champs) | {'late_minutes'})
        super().save(*args, **kwargs)

    def lateness(self):
        """Minutes de retard sur l'heure de début, tolérance déduite."""
        if self.check_in is None:
            return 0
        arrivee = timezone.localtime(self.check_in)
        attendue = self.member.work_starts_at
        ecart = ((arrivee.hour * 60 + arrivee.minute)
                 - (attendue.hour * 60 + attendue.minute))
        return max(ecart - self.GRACE_MINUTES, 0)

    @property
    def is_open(self):
        """Journée entamée dont le départ n'est pas encore pointé."""
        return self.check_out is None

    @property
    def is_late(self):
        return self.late_minutes > 0

    def _provisional_end(self):
        """Fin retenue tant que le départ n'est pas pointé.

        La journée en cours court jusqu'à maintenant ; une journée passée
        s'arrête à l'heure de fin prévue, sans quoi un départ oublié gonflerait
        le compteur de plusieurs jours.
        """
        maintenant = timezone.now()
        if self.date >= timezone.localdate():
            return maintenant
        prevue = timezone.make_aware(
            datetime.combine(self.date, self.member.work_ends_at)
        )
        return min(prevue, maintenant)

    @property
    def minutes(self):
        """Minutes de présence, de l'arrivée au départ."""
        if self.check_in is None:
            return 0
        fin = self.check_out or self._provisional_end()
        return max(int((fin - self.check_in).total_seconds() // 60), 0)

    @property
    def hours(self):
        """Heures de présence, au centième."""
        return (Decimal(self.minutes) / Decimal(60)).quantize(Decimal('0.01'))

    @property
    def duration_label(self):
        """Durée lisible : « 45 min », « 7 h 30 »."""
        minutes = self.minutes
        if minutes < 60:
            return f"{minutes} min"
        return f"{minutes // 60} h {minutes % 60:02d}"

    def close(self, moment=None):
        """Pointe le départ ; un départ déjà pointé n'est pas repoussé."""
        if self.check_out is not None:
            return self
        fin = moment or timezone.now()
        # Un départ ne précède jamais l'arrivée, quelle que soit l'horloge.
        self.check_out = max(fin, self.check_in)
        self.save(update_fields=['check_out', 'updated_at'])
        return self

    @classmethod
    def open_for(cls, member, moment=None):
        """Pointe l'arrivée du jour, ou rend le pointage déjà ouvert."""
        arrivee = moment or timezone.now()
        jour = timezone.localdate(arrivee)
        return cls.objects.get_or_create(
            member=member, date=jour, defaults={'check_in': arrivee},
        )
