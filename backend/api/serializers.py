"""
Serializers de l'API Flux Gestion.

Ils portent la validation métier et empêchent un membre de rattacher ses
objets à ceux d'un collègue.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from .credentials import generate_password

from .models import (
    Attendance, DailyTask, LeaveRequest, Member, MonthlyObjective, Payslip,
    Reaction, Report, RoadmapItem, StaffEvent, Suggestion, first_day_of_month,
    working_days,
)
from .validators import validate_month_not_too_far, validate_period_order


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'first_name', 'last_name', 'email')
        read_only_fields = ('id', 'username')


class MemberSerializer(serializers.ModelSerializer):
    """Profil d'un membre de l'équipe."""

    username = serializers.CharField(source='user.username', read_only=True)
    email = serializers.EmailField(source='user.email', read_only=True)
    first_name = serializers.CharField(source='user.first_name', required=False, allow_blank=True)
    last_name = serializers.CharField(source='user.last_name', required=False, allow_blank=True)
    display_name = serializers.CharField(read_only=True)
    is_founder = serializers.BooleanField(read_only=True)
    is_manager = serializers.BooleanField(read_only=True)
    department_label = serializers.CharField(source='get_department_display', read_only=True)
    role_label = serializers.CharField(source='get_role_display', read_only=True)

    is_active = serializers.BooleanField(source='user.is_active', read_only=True)
    last_login = serializers.DateTimeField(source='user.last_login', read_only=True)
    points_total = serializers.IntegerField(read_only=True)
    points_month = serializers.IntegerField(read_only=True)
    bonus_earned = serializers.IntegerField(read_only=True)
    leave_days_taken = serializers.FloatField(read_only=True)
    leave_balance = serializers.FloatField(read_only=True)

    class Meta:
        model = Member
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'display_name',
                  'role', 'role_label', 'job_title', 'department', 'department_label',
                  'phone', 'joined_on', 'base_salary', 'points_total', 'points_month',
                  'bonus_earned', 'work_starts_at', 'work_ends_at',
                  'leave_entitlement', 'leave_days_taken', 'leave_balance',
                  'is_founder', 'is_manager', 'is_active',
                  'last_login', 'created_at', 'updated_at')
        # Un membre ne se donne ni un rôle, ni un salaire, ni ses horaires ou
        # son droit à congé : seul le sérialiseur d'administration les rend
        # modifiables, et lui est réservé aux fondateurs.
        read_only_fields = ('id', 'role', 'base_salary', 'work_starts_at',
                            'work_ends_at', 'leave_entitlement',
                            'created_at', 'updated_at')

    def update(self, instance, validated_data):
        # `source='user.x'` produit un sous-dictionnaire qu'il faut appliquer
        # explicitement au User lié.
        user_data = validated_data.pop('user', {})
        for field, value in user_data.items():
            setattr(instance.user, field, value)
        if user_data:
            instance.user.save(update_fields=list(user_data))
        return super().update(instance, validated_data)


class MemberAdminSerializer(MemberSerializer):
    """Création et modification d'un compte par un fondateur.

    Le sérialiseur ordinaire fige l'identifiant et le rôle ; celui-ci les ouvre,
    et n'est monté que sur les vues protégées par `IsFounder`.
    """

    username = serializers.CharField(source='user.username', max_length=150)
    email = serializers.EmailField(
        source='user.email', required=False, allow_blank=True
    )
    is_active = serializers.BooleanField(source='user.is_active', required=False)
    password = serializers.CharField(
        write_only=True, required=False, allow_blank=True,
        help_text="Laissé vide à la création, un mot de passe est engendré.",
    )
    # Rendu à la création seulement : c'est la seule fois où il est lisible.
    generated_password = serializers.CharField(read_only=True)

    class Meta(MemberSerializer.Meta):
        fields = MemberSerializer.Meta.fields + ('password', 'generated_password')
        read_only_fields = ('id', 'created_at', 'updated_at', 'display_name',
                            'is_founder', 'is_manager', 'last_login',
                            'points_total', 'points_month', 'bonus_earned',
                            'leave_days_taken', 'leave_balance')

    def validate_username(self, value):
        identifiant = value.strip()
        if not identifiant:
            raise serializers.ValidationError("L'identifiant est obligatoire.")

        existants = User.objects.filter(username__iexact=identifiant)
        if self.instance is not None:
            existants = existants.exclude(pk=self.instance.user_id)
        if existants.exists():
            raise serializers.ValidationError(
                f"L'identifiant « {identifiant} » est déjà pris."
            )
        return identifiant

    def validate_password(self, value):
        """Applique les règles de robustesse du projet, comme à l'inscription."""
        if not value:
            return value
        validate_password(value)
        return value

    def create(self, validated_data):
        user_data = validated_data.pop('user', {})
        choisi = validated_data.pop('password', '')
        motdepasse = choisi or generate_password()

        user = User.objects.create_user(
            username=user_data['username'],
            email=user_data.get('email', ''),
            password=motdepasse,
            first_name=user_data.get('first_name', ''),
            last_name=user_data.get('last_name', ''),
            is_active=user_data.get('is_active', True),
        )

        # Le signal a déjà posé un profil : on l'aligne sur la saisie.
        member = Member.objects.for_user(user)
        for champ, valeur in validated_data.items():
            setattr(member, champ, valeur)
        member.save()

        # Rendu une seule fois, et seulement si le serveur l'a engendré : un
        # mot de passe choisi par l'appelant, il le connaît déjà, et le lui
        # réémettre l'exposerait pour rien.
        member.generated_password = '' if choisi else motdepasse
        return member

    def update(self, instance, validated_data):
        motdepasse = validated_data.pop('password', '')
        member = super().update(instance, validated_data)
        if motdepasse:
            member.user.set_password(motdepasse)
            member.user.save(update_fields=['password'])
        return member


class ReactionSerializer(serializers.ModelSerializer):
    """Points accordés ou retirés par la direction."""

    member_name = serializers.CharField(source='member.display_name', read_only=True)
    author_name = serializers.CharField(
        source='author.display_name', read_only=True, default=''
    )
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    is_positive = serializers.BooleanField(read_only=True)
    value = serializers.IntegerField(read_only=True)
    # Facultatif à la saisie : omis, il prend la valeur du barème. La
    # vérification des champs précède `validate()`, d'où ce `required=False`.
    points = serializers.IntegerField(required=False)

    class Meta:
        model = Reaction
        fields = ('id', 'member', 'member_name', 'kind', 'kind_label', 'points',
                  'value', 'is_positive', 'reason', 'date', 'author',
                  'author_name', 'created_at')
        read_only_fields = ('author', 'created_at')

    def validate(self, attrs):
        """Une réaction sans points ne dit rien et ne pèse rien."""
        if 'points' not in attrs and self.instance is None:
            nature = attrs.get('kind')
            attrs['points'] = Reaction.DEFAULT_POINTS.get(nature, 0)

        points = attrs.get('points', getattr(self.instance, 'points', 0))
        if points == 0:
            raise serializers.ValidationError(
                {'points': "Une réaction accorde ou retire des points, jamais zéro."}
            )
        return attrs


class RoadmapItemSerializer(serializers.ModelSerializer):
    """Jalon de feuille de route."""

    status_label = serializers.CharField(source='get_status_display', read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    member_name = serializers.CharField(source='objective.member.display_name', read_only=True)
    month = serializers.DateField(source='objective.month', read_only=True)
    open_tasks = serializers.SerializerMethodField()

    class Meta:
        model = RoadmapItem
        fields = ('id', 'objective', 'month', 'member_name', 'title', 'description',
                  'due_date', 'status', 'status_label', 'progress', 'position',
                  'is_overdue', 'open_tasks', 'created_at', 'updated_at', 'completed_at')
        read_only_fields = ('created_at', 'updated_at', 'completed_at')

    def get_open_tasks(self, obj):
        return obj.tasks.exclude(status='done').count()

    def validate_objective(self, value):
        """Interdit d'accrocher un jalon à l'objectif d'un collègue."""
        member = self.context.get('member')
        if member and not member.is_founder and value.member_id != member.pk:
            raise serializers.ValidationError(
                "Vous ne pouvez ajouter un jalon qu'à vos propres objectifs."
            )
        return value


class DailyTaskSerializer(serializers.ModelSerializer):
    """Tâche du jour."""

    status_label = serializers.CharField(source='get_status_display', read_only=True)
    priority_label = serializers.CharField(source='get_priority_display', read_only=True)
    member_name = serializers.CharField(source='member.display_name', read_only=True)
    roadmap_title = serializers.CharField(
        source='roadmap_item.title', read_only=True, default=None
    )
    duration_minutes = serializers.IntegerField(read_only=True)
    duration_label = serializers.CharField(read_only=True)
    over_estimate = serializers.BooleanField(read_only=True)

    class Meta:
        model = DailyTask
        fields = ('id', 'member', 'member_name', 'date', 'title', 'description',
                  'status', 'status_label', 'priority', 'priority_label',
                  'roadmap_item', 'roadmap_title', 'estimated_minutes',
                  'started_at', 'completed_at', 'duration_minutes', 'duration_label',
                  'over_estimate', 'created_at', 'updated_at')
        read_only_fields = ('member', 'created_at', 'updated_at', 'completed_at',
                            'started_at')

    def validate_roadmap_item(self, value):
        """Une tâche ne se rattache qu'à un jalon du membre lui-même."""
        if value is None:
            return value
        member = self.context.get('member')
        if member and not member.is_founder and value.objective.member_id != member.pk:
            raise serializers.ValidationError(
                "Ce jalon appartient à un autre membre de l'équipe."
            )
        return value


class MonthlyObjectiveSerializer(serializers.ModelSerializer):
    """Objectifs du mois d'un membre."""

    member_name = serializers.CharField(source='member.display_name', read_only=True)
    department = serializers.CharField(source='member.department', read_only=True)
    month_label = serializers.CharField(read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)

    revenue_completion = serializers.FloatField(read_only=True)
    clients_completion = serializers.FloatField(read_only=True)
    completion = serializers.FloatField(read_only=True)
    elapsed_ratio = serializers.FloatField(read_only=True)
    is_at_risk = serializers.BooleanField(read_only=True)
    revenue_gap = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    roadmap_count = serializers.SerializerMethodField()
    roadmap_done = serializers.SerializerMethodField()

    month = serializers.DateField(validators=[validate_month_not_too_far])

    class Meta:
        model = MonthlyObjective
        fields = ('id', 'member', 'member_name', 'department', 'month', 'month_label',
                  'revenue_target', 'revenue_achieved', 'clients_target',
                  'clients_achieved', 'focus', 'notes', 'status', 'status_label',
                  'revenue_completion', 'clients_completion', 'completion',
                  'elapsed_ratio', 'is_at_risk', 'revenue_gap',
                  'roadmap_count', 'roadmap_done', 'created_at', 'updated_at')
        read_only_fields = ('member', 'created_at', 'updated_at')

    def get_roadmap_count(self, obj):
        return obj.roadmap.count()

    def get_roadmap_done(self, obj):
        return obj.roadmap.filter(status='done').count()

    def validate(self, attrs):
        """Vérifie qu'un objectif est utile et qu'il n'existe pas déjà.

        La contrainte d'unicité en base protège de toute façon, mais elle
        remonterait une erreur 500 : on la devance ici pour rendre un 400 lisible.
        """
        member = self.context.get('member')
        month = attrs.get('month') or getattr(self.instance, 'month', None)

        if month is not None:
            month = month.replace(day=1)
            owner = self.instance.member if self.instance else member
            if owner is not None:
                clash = MonthlyObjective.objects.filter(member=owner, month=month)
                if self.instance:
                    clash = clash.exclude(pk=self.instance.pk)
                if clash.exists():
                    raise serializers.ValidationError({
                        'month': "Des objectifs existent déjà pour ce mois."
                    })

        revenue_target = attrs.get(
            'revenue_target', getattr(self.instance, 'revenue_target', 0)
        )
        clients_target = attrs.get(
            'clients_target', getattr(self.instance, 'clients_target', 0)
        )
        if not revenue_target and not clients_target:
            raise serializers.ValidationError(
                "Renseignez au moins un CA attendu ou un nombre de clients attendu."
            )
        return attrs


class MonthlyObjectiveDetailSerializer(MonthlyObjectiveSerializer):
    """Objectif détaillé, feuille de route incluse."""

    roadmap = RoadmapItemSerializer(many=True, read_only=True)

    class Meta(MonthlyObjectiveSerializer.Meta):
        fields = MonthlyObjectiveSerializer.Meta.fields + ('roadmap',)


class ReportSerializer(serializers.ModelSerializer):
    """Rapport d'activité rédigé par un membre."""

    member_name = serializers.CharField(source='member.display_name', read_only=True)
    department = serializers.CharField(source='member.department', read_only=True)
    period_label = serializers.CharField(source='get_period_type_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    is_event = serializers.BooleanField(read_only=True)

    class Meta:
        model = Report
        fields = ('id', 'member', 'member_name', 'department', 'period_type',
                  'period_label', 'is_event', 'period_start', 'period_end',
                  'title', 'location', 'participants', 'summary', 'achievements',
                  'blockers', 'decisions', 'next_steps', 'status', 'status_label',
                  'submitted_at', 'created_at', 'updated_at')
        read_only_fields = ('member', 'status', 'submitted_at', 'created_at', 'updated_at')

    def _field(self, attrs, name):
        """Valeur soumise, ou celle déjà enregistrée lors d'une mise à jour."""
        if name in attrs:
            return attrs[name]
        return getattr(self.instance, name, None)

    def validate(self, attrs):
        start = self._field(attrs, 'period_start')
        end = self._field(attrs, 'period_end')
        validate_period_order(start, end)

        # Une mission ou une réunion se retrouve par son objet : « Rapport de
        # mission » seul ne distingue pas deux déplacements du même mois.
        period_type = self._field(attrs, 'period_type')
        if period_type in Report.EVENT_TYPES and not (self._field(attrs, 'title') or '').strip():
            raise serializers.ValidationError({
                'title': "L'objet est obligatoire pour un rapport de mission "
                         "ou de réunion."
            })
        return attrs


class PayslipEventSerializer(serializers.ModelSerializer):
    """Évènement du mois tel qu'il figure sur un bulletin de paie.

    Volontairement plus court que la fiche du suivi du personnel : le salarié
    lit ce qui s'est passé et la suite donnée, pas qui a saisi la fiche.
    """

    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    summary = serializers.CharField(read_only=True)
    days = serializers.IntegerField(read_only=True)
    is_disciplinary = serializers.BooleanField(read_only=True)

    class Meta:
        model = StaffEvent
        fields = ('id', 'kind', 'kind_label', 'date', 'end_date', 'minutes',
                  'hours', 'is_paid', 'days', 'summary', 'is_disciplinary',
                  'reason', 'decision')
        read_only_fields = fields


class PayslipSerializer(serializers.ModelSerializer):
    """Bulletin de paie d'un membre pour un mois."""

    member_name = serializers.CharField(source='member.display_name', read_only=True)
    department = serializers.CharField(source='member.department', read_only=True)
    job_title = serializers.CharField(source='member.job_title', read_only=True)
    month_label = serializers.CharField(read_only=True)
    gross = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    net = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    # Retards, observations, mises à pied et heures supplémentaires du mois :
    # ils expliquent le décompte, le bulletin les porte donc avec lui.
    staff_events = PayslipEventSerializer(many=True, read_only=True)

    class Meta:
        model = Payslip
        fields = ('id', 'member', 'member_name', 'department', 'job_title', 'month',
                  'month_label', 'base_salary', 'worked_hours', 'overtime_hours',
                  'overtime_amount', 'bonuses', 'deductions', 'contributions',
                  'gross', 'net', 'notes', 'staff_events', 'issued_at',
                  'created_at', 'updated_at')
        read_only_fields = ('issued_at', 'created_at', 'updated_at')

    def validate_month(self, value):
        validate_month_not_too_far(value)
        # Le mois est ramené au 1er dès la validation, et pas seulement à
        # l'enregistrement : sans cela, corriger un bulletin vers le 15 d'un
        # mois déjà payé passerait le contrôle d'unicité et casserait en base.
        return first_day_of_month(value)

    def validate(self, attrs):
        """Un net négatif traduit une saisie erronée, pas une paie réelle."""
        def field(name):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name, Decimal('0'))

        gross = field('base_salary') + field('overtime_amount') + field('bonuses')
        if gross - field('deductions') - field('contributions') < 0:
            raise serializers.ValidationError({
                'deductions': "Les retenues et cotisations dépassent le brut : "
                              "le net à payer serait négatif."
            })
        return attrs


class StaffEventSerializer(serializers.ModelSerializer):
    """Mise à pied, observation, retard ou heures supplémentaires."""

    member_name = serializers.CharField(source='member.display_name', read_only=True)
    department = serializers.CharField(source='member.department', read_only=True)
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    recorded_by_name = serializers.CharField(
        source='recorded_by.display_name', read_only=True, default=''
    )
    days = serializers.IntegerField(read_only=True)
    summary = serializers.CharField(read_only=True)
    is_disciplinary = serializers.BooleanField(read_only=True)

    class Meta:
        model = StaffEvent
        fields = ('id', 'member', 'member_name', 'department', 'kind', 'kind_label',
                  'date', 'end_date', 'minutes', 'hours', 'is_paid', 'days', 'summary',
                  'is_disciplinary', 'reason', 'decision', 'recorded_by',
                  'recorded_by_name', 'created_at', 'updated_at')
        read_only_fields = ('recorded_by', 'created_at', 'updated_at')

    def validate(self, attrs):
        """Chaque nature d'évènement porte sa propre mesure."""
        def field(name):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name, None)

        kind = field('kind')
        date = field('date')

        if kind == 'suspension':
            end = field('end_date')
            if end is None:
                raise serializers.ValidationError({
                    'end_date': "Une mise à pied a une date de fin."
                })
            if date and end < date:
                raise serializers.ValidationError({
                    'end_date': "La fin doit suivre le début de la mise à pied."
                })
        elif kind == 'lateness' and not field('minutes'):
            raise serializers.ValidationError({
                'minutes': "Indiquez le retard en minutes."
            })
        elif kind == 'overtime' and not field('hours'):
            raise serializers.ValidationError({
                'hours': "Indiquez le nombre d'heures supplémentaires."
            })

        if not (field('reason') or '').strip():
            raise serializers.ValidationError({
                'reason': "Le motif est obligatoire."
            })
        return attrs


class LeaveRequestSerializer(serializers.ModelSerializer):
    """Demande de congé : posée par un membre, tranchée par la direction."""

    member_name = serializers.CharField(source='member.display_name', read_only=True)
    department = serializers.CharField(source='member.department', read_only=True)
    kind_label = serializers.CharField(source='get_kind_display', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    decided_by_name = serializers.CharField(
        source='decided_by.display_name', read_only=True, default=''
    )
    days = serializers.FloatField(read_only=True)
    days_label = serializers.CharField(read_only=True)
    is_counted = serializers.BooleanField(read_only=True)

    class Meta:
        model = LeaveRequest
        fields = ('id', 'member', 'member_name', 'department', 'kind', 'kind_label',
                  'start_date', 'end_date', 'half_day', 'days', 'days_label',
                  'is_counted', 'reason', 'status', 'status_label', 'decision',
                  'decided_by', 'decided_by_name', 'decided_at',
                  'created_at', 'updated_at')
        # L'état ne se pose pas à la saisie : il vient de la décision, et la
        # demande est toujours celle de son auteur.
        read_only_fields = ('member', 'status', 'decision', 'decided_by',
                            'decided_at', 'created_at', 'updated_at')

    def _field(self, attrs, name):
        """Valeur soumise, ou celle déjà enregistrée lors d'une mise à jour."""
        if name in attrs:
            return attrs[name]
        return getattr(self.instance, name, None)

    def validate(self, attrs):
        start = self._field(attrs, 'start_date')
        end = self._field(attrs, 'end_date')
        validate_period_order(start, end)

        if self._field(attrs, 'half_day') and start != end:
            raise serializers.ValidationError({
                'half_day': "Une demi-journée tient sur un seul jour."
            })

        if start and end and working_days(start, end) == 0:
            raise serializers.ValidationError({
                'start_date': "Cette période ne compte aucun jour ouvrable."
            })

        if not (self._field(attrs, 'reason') or '').strip():
            raise serializers.ValidationError({
                'reason': "Le motif est obligatoire."
            })

        # Deux congés qui se chevauchent compteraient deux fois les mêmes
        # jours : l'auteur corrige sa demande plutôt que d'en poser une autre.
        member = self.instance.member if self.instance else self.context.get('member')
        if member and start and end:
            voisines = (LeaveRequest.objects.owned_by(member).blocking()
                        .in_period(start, end))
            if self.instance is not None:
                voisines = voisines.exclude(pk=self.instance.pk)
            if voisines.exists():
                raise serializers.ValidationError({
                    'start_date': "Une autre demande couvre déjà cette période."
                })
        return attrs


class AttendanceSerializer(serializers.ModelSerializer):
    """Pointage d'une journée : arrivée, départ et temps de présence."""

    member_name = serializers.CharField(source='member.display_name', read_only=True)
    department = serializers.CharField(source='member.department', read_only=True)
    job_title = serializers.CharField(source='member.job_title', read_only=True)
    minutes = serializers.IntegerField(read_only=True)
    hours = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    duration_label = serializers.CharField(read_only=True)
    is_open = serializers.BooleanField(read_only=True)
    is_late = serializers.BooleanField(read_only=True)

    class Meta:
        model = Attendance
        fields = ('id', 'member', 'member_name', 'department', 'job_title', 'date',
                  'check_in', 'check_out', 'minutes', 'hours', 'duration_label',
                  'late_minutes', 'is_open', 'is_late', 'note',
                  'created_at', 'updated_at')
        # Le retard se déduit de l'arrivée : le saisir à la main permettrait de
        # l'effacer sans corriger l'heure.
        read_only_fields = ('late_minutes', 'created_at', 'updated_at')

    def validate(self, attrs):
        def field(name):
            if name in attrs:
                return attrs[name]
            return getattr(self.instance, name, None)

        arrivee, depart = field('check_in'), field('check_out')
        if arrivee and depart and depart < arrivee:
            raise serializers.ValidationError({
                'check_out': "Le départ doit suivre l'arrivée."
            })
        return attrs


class SuggestionSerializer(serializers.ModelSerializer):
    """Message de la boîte à suggestions."""

    author_name = serializers.CharField(source='author.display_name', read_only=True)
    department = serializers.CharField(source='author.department', read_only=True)
    category_label = serializers.CharField(
        source='get_category_display', read_only=True
    )
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    handled_by_name = serializers.CharField(
        source='handled_by.display_name', read_only=True, default=''
    )
    excerpt = serializers.CharField(read_only=True)

    class Meta:
        model = Suggestion
        fields = ('id', 'author', 'author_name', 'department', 'category',
                  'category_label', 'message', 'excerpt', 'status', 'status_label',
                  'reply', 'handled_by', 'handled_by_name', 'handled_at',
                  'created_at', 'updated_at')
        read_only_fields = ('author', 'status', 'reply', 'handled_by', 'handled_at',
                            'created_at', 'updated_at')

    def validate_message(self, value):
        """Une suggestion vide n'apprend rien à personne."""
        texte = value.strip()
        if len(texte) < 10:
            raise serializers.ValidationError(
                "Dites-en un peu plus : au moins dix caractères."
            )
        return texte


class TeamMemberSummarySerializer(serializers.Serializer):
    """Ligne de synthèse d'un membre dans la vue d'équipe (lecture seule)."""

    member_id = serializers.IntegerField()
    member_name = serializers.CharField()
    department = serializers.CharField()
    job_title = serializers.CharField()
    revenue_target = serializers.DecimalField(max_digits=12, decimal_places=2)
    revenue_achieved = serializers.DecimalField(max_digits=12, decimal_places=2)
    clients_target = serializers.IntegerField()
    clients_achieved = serializers.IntegerField()
    completion = serializers.FloatField(allow_null=True)
    is_at_risk = serializers.BooleanField()
    open_tasks = serializers.IntegerField()
    reports_submitted = serializers.IntegerField()
