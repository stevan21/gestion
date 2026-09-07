"""
Vues de l'API Flux Gestion.

Toutes les collections passent par `visible_to()` : un membre ne voit que ses
données, un fondateur voit l'équipe entière.
"""

import csv
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .filters import (
    AttendanceFilter, DailyTaskFilter, LeaveRequestFilter, MemberFilter,
    MonthlyObjectiveFilter, PayslipFilter, ReactionFilter, ReportFilter,
    RoadmapItemFilter, StaffEventFilter, SuggestionFilter,
)
from .credentials import generate_password
from .managers import month_range, month_start
from .models import (
    Attendance, DailyTask, LeaveRequest, Member, MonthlyObjective, Payslip,
    Reaction, Report, RoadmapItem, StaffEvent, Suggestion, working_days,
)
from .permissions import (
    HasMemberProfile, IsFounder, IsManager, IsOwnerOrFounder, IsSelfOrFounder,
)
from .serializers import (
    AttendanceSerializer, DailyTaskSerializer, LeaveRequestSerializer,
    MemberAdminSerializer, MemberSerializer, MonthlyObjectiveDetailSerializer,
    MonthlyObjectiveSerializer, PayslipSerializer, ReactionSerializer,
    ReportSerializer, RoadmapItemSerializer, StaffEventSerializer,
    SuggestionSerializer,
)


class MemberScopedMixin:
    """Résout le profil métier et le met à disposition des permissions."""

    def initial(self, request, *args, **kwargs):
        # Fixé avant `check_permissions` : les permissions s'appuient dessus.
        request.member = Member.objects.for_user(request.user)
        super().initial(request, *args, **kwargs)

    @property
    def member(self):
        return getattr(self.request, 'member', None)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['member'] = self.member
        return context


def parse_month(request, param='month'):
    """Lit un mois `AAAA-MM` en query string, ou retourne le mois courant."""
    raw = request.query_params.get(param)
    if not raw:
        return month_start()
    try:
        year, month = raw.split('-')
        return month_start(timezone.datetime(int(year), int(month), 1).date())
    except (ValueError, TypeError):
        raise ValueError("Mois invalide (format attendu : AAAA-MM)")


class MemberViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Profils de l'équipe, et administration des comptes pour un fondateur."""

    serializer_class = MemberSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile, IsSelfOrFounder]
    filterset_class = MemberFilter
    search_fields = ['user__first_name', 'user__last_name', 'user__username', 'job_title']
    ordering_fields = ['user__first_name', 'joined_on', 'department']
    ordering = ['user__first_name']

    def get_queryset(self):
        return Member.objects.visible_to(self.member).with_user()

    def get_serializer_class(self):
        """Le sérialiseur d'administration ouvre l'identifiant et le rôle."""
        if self.member and self.member.is_founder and self.action not in ('me',):
            return MemberAdminSerializer
        return MemberSerializer

    def get_permissions(self):
        # Créer un compte n'a pas d'objet sur lequel vérifier l'appartenance :
        # la permission de fondateur s'applique à la vue elle-même.
        if self.action in ('create', 'destroy', 'set_active', 'reset_password'):
            return [IsAuthenticated(), HasMemberProfile(), IsFounder()]
        return super().get_permissions()

    @action(detail=False, methods=['get', 'patch'])
    def me(self, request):
        """Profil du membre connecté."""
        if request.method == 'PATCH':
            serializer = MemberSerializer(
                self.member, data=request.data, partial=True,
                context=self.get_serializer_context(),
            )
            serializer.is_valid(raise_exception=True)
            serializer.save()
            return Response(serializer.data)
        return Response(MemberSerializer(self.member).data)

    def perform_update(self, serializer):
        """Un rôle ne se retire pas au dernier fondateur."""
        instance = serializer.instance
        nouveau = serializer.validated_data.get('role', instance.role)
        if instance.role == 'founder' and nouveau != 'founder':
            self._check_last_founder(instance)
        serializer.save()

    def perform_destroy(self, instance):
        """Supprime définitivement un compte, garde-fous compris."""
        if instance.pk == self.member.pk:
            raise ValidationError(
                {'detail': "Vous ne pouvez pas supprimer votre propre compte."}
            )
        if instance.role == 'founder':
            self._check_last_founder(instance)
        instance.user.delete()

    @action(detail=True, methods=['patch'])
    def set_active(self, request, pk=None):
        """Active ou désactive un compte, sans toucher à son historique.

        C'est la voie à préférer à la suppression : le compte ne peut plus se
        connecter, mais ses objectifs, ses tâches et ses bulletins restent.
        """
        member = self.get_object()
        actif = bool(request.data.get('active', False))

        if member.pk == self.member.pk:
            return Response(
                {'detail': "Vous ne pouvez pas désactiver votre propre compte."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not actif and member.role == 'founder':
            self._check_last_founder(member)

        member.user.is_active = actif
        member.user.save(update_fields=['is_active'])
        return Response(MemberAdminSerializer(member).data)

    @action(detail=True, methods=['patch'])
    def reset_password(self, request, pk=None):
        """Engendre un nouveau mot de passe et le retourne une seule fois."""
        member = self.get_object()
        motdepasse = generate_password()
        member.user.set_password(motdepasse)
        member.user.save(update_fields=['password'])

        données = MemberAdminSerializer(member).data
        données['generated_password'] = motdepasse
        return Response(données)

    def _check_last_founder(self, instance):
        """Une instance sans fondateur ne se réadministre plus."""
        autres = Member.objects.founders().exclude(pk=instance.pk)
        if not autres.exists():
            raise ValidationError(
                {'detail': "Cette instance n'aurait plus aucun fondateur."}
            )


class MonthlyObjectiveViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Objectifs mensuels : CA et clients attendus contre réalisés."""

    permission_classes = [IsAuthenticated, HasMemberProfile, IsOwnerOrFounder]
    filterset_class = MonthlyObjectiveFilter
    search_fields = ['focus', 'notes', 'member__user__first_name', 'member__user__last_name']
    ordering_fields = ['month', 'revenue_target', 'revenue_achieved', 'clients_achieved']
    ordering = ['-month']

    def get_queryset(self):
        return MonthlyObjective.objects.visible_to(self.member).with_related()

    def get_serializer_class(self):
        if self.action in ('retrieve', 'current'):
            return MonthlyObjectiveDetailSerializer
        return MonthlyObjectiveSerializer

    def perform_create(self, serializer):
        """Un membre pose ses propres objectifs."""
        serializer.save(member=self.member)

    @action(detail=False, methods=['get'])
    def current(self, request):
        """Objectifs du mois en cours pour le membre connecté."""
        objective = (
            MonthlyObjective.objects.owned_by(self.member)
            .with_related().for_month().first()
        )
        if objective is None:
            return Response(
                {'detail': "Aucun objectif n'est encore défini pour ce mois.",
                 'month': month_start().isoformat()},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(self.get_serializer(objective).data)

    @action(detail=True, methods=['patch'])
    def close(self, request, pk=None):
        """Clôture le mois : les chiffres ne sont plus censés bouger."""
        objective = self.get_object()
        if objective.status == 'closed':
            return Response(
                {'detail': 'Ce mois est déjà clôturé.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        objective.status = 'closed'
        objective.save(update_fields=['status', 'updated_at'])
        return Response(self.get_serializer(objective).data)

    @action(detail=False, methods=['get'])
    def history(self, request):
        """Évolution mensuelle du CA et des clients sur les N derniers mois."""
        try:
            months = max(1, min(int(request.query_params.get('months', 6)), 36))
        except ValueError:
            return Response(
                {'error': 'Le paramètre months doit être un entier'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.filter_queryset(self.get_queryset())
        buckets = {
            row['month']: row
            for row in queryset.values('month').annotate(
                revenue_target=Sum('revenue_target'),
                revenue_achieved=Sum('revenue_achieved'),
                clients_target=Sum('clients_target'),
                clients_achieved=Sum('clients_achieved'),
            )
        }

        # Série continue : un mois sans objectif apparaît à zéro plutôt
        # que de disparaître du graphique.
        result = []
        for offset in range(months - 1, -1, -1):
            start, _ = month_range(months_back=offset)
            row = buckets.get(start)
            result.append({
                'month': f'{start:%Y-%m}',
                'revenue_target': float(row['revenue_target'] or 0) if row else 0.0,
                'revenue_achieved': float(row['revenue_achieved'] or 0) if row else 0.0,
                'clients_target': (row['clients_target'] or 0) if row else 0,
                'clients_achieved': (row['clients_achieved'] or 0) if row else 0,
            })
        return Response(result)

    @action(detail=False, methods=['get'])
    def export(self, request):
        """Export CSV des objectifs visibles, filtres compris."""
        queryset = self.filter_queryset(self.get_queryset())

        response = HttpResponse(content_type='text/csv; charset=utf-8')
        filename = f'objectifs-{timezone.now():%Y%m%d-%H%M}.csv'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response.write('﻿')  # BOM : Excel reconnaît alors l'UTF-8

        writer = csv.writer(response, delimiter=';')
        writer.writerow([
            'Mois', 'Membre', 'Pôle', 'CA attendu (FCFA)', 'CA réalisé (FCFA)',
            'Écart (FCFA)', 'Clients attendus', 'Clients signés', 'Avancement %',
            'Statut', 'Objectif principal',
        ])
        for objective in queryset:
            writer.writerow([
                objective.month_label,
                objective.member.display_name,
                objective.member.get_department_display(),
                objective.revenue_target,
                objective.revenue_achieved,
                objective.revenue_achieved - objective.revenue_target,
                objective.clients_target,
                objective.clients_achieved,
                objective.completion if objective.completion is not None else '',
                objective.get_status_display(),
                objective.focus,
            ])
        return response


class RoadmapItemViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Jalons de la feuille de route."""

    serializer_class = RoadmapItemSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile, IsOwnerOrFounder]
    filterset_class = RoadmapItemFilter
    search_fields = ['title', 'description']
    ordering_fields = ['position', 'due_date', 'progress', 'created_at']
    ordering = ['position', 'due_date']

    def get_queryset(self):
        return RoadmapItem.objects.visible_to(self.member).with_related()

    @action(detail=False, methods=['get'])
    def overdue(self, request):
        """Jalons non terminés dont l'échéance est passée."""
        items = self.filter_queryset(self.get_queryset()).overdue()
        return Response(self.get_serializer(items, many=True).data)

    @action(detail=True, methods=['patch'])
    def complete(self, request, pk=None):
        """Marque un jalon comme terminé."""
        item = self.get_object()
        if item.status == 'done':
            return Response(
                {'detail': 'Ce jalon est déjà terminé.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        item.status = 'done'
        item.save()
        return Response(self.get_serializer(item).data)


class DailyTaskViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Tâches quotidiennes."""

    serializer_class = DailyTaskSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile, IsOwnerOrFounder]
    filterset_class = DailyTaskFilter
    search_fields = ['title', 'description']
    ordering_fields = ['date', 'priority', 'status', 'created_at']
    ordering = ['-date', '-priority']

    def get_queryset(self):
        return DailyTask.objects.visible_to(self.member).with_related()

    def perform_create(self, serializer):
        serializer.save(member=self.member)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """Tâches du jour, complétées par les retards non traités."""
        base = DailyTask.objects.owned_by(self.member).with_related()
        today = base.today()
        late = base.late()
        return Response({
            'date': timezone.localdate().isoformat(),
            'today': self.get_serializer(today, many=True).data,
            'late': self.get_serializer(late, many=True).data,
            'done_count': today.done().count(),
            'total_count': today.count(),
        })

    @action(detail=True, methods=['patch'])
    def start(self, request, pk=None):
        """Démarre la tâche et lance le décompte du temps passé."""
        task = self.get_object()
        if task.status == 'done':
            return Response(
                {'detail': 'Cette tâche est déjà terminée.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if task.status == 'in_progress':
            return Response(
                {'detail': 'Cette tâche est déjà démarrée.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        task.start()
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=['patch'])
    def complete(self, request, pk=None):
        """Marque une tâche comme terminée."""
        task = self.get_object()
        if task.status == 'done':
            return Response(
                {'detail': 'Cette tâche est déjà terminée.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        task.status = 'done'
        task.save()
        return Response(self.get_serializer(task).data)

    @action(detail=False, methods=['post'])
    def carry_over(self, request):
        """Reporte sur aujourd'hui les tâches en retard non terminées."""
        today = timezone.localdate()
        late = DailyTask.objects.owned_by(self.member).late()
        moved = late.update(date=today, updated_at=timezone.now())
        return Response({'moved': moved, 'date': today.isoformat()})


class ReportViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Rapports d'activité."""

    serializer_class = ReportSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile, IsOwnerOrFounder]
    filterset_class = ReportFilter
    search_fields = ['title', 'summary', 'achievements', 'blockers',
                     'decisions', 'next_steps', 'participants', 'location']
    ordering_fields = ['period_end', 'created_at', 'period_type']
    ordering = ['-period_end']

    def get_queryset(self):
        return Report.objects.visible_to(self.member).with_related()

    def perform_create(self, serializer):
        serializer.save(member=self.member)

    def perform_update(self, serializer):
        """Un rapport soumis n'est plus modifiable par son auteur."""
        if serializer.instance.status == 'submitted' and not self.member.is_founder:
            raise ValidationError(
                {'detail': "Ce rapport est déjà soumis et ne peut plus être modifié."}
            )
        serializer.save()

    @action(detail=True, methods=['patch'])
    def submit(self, request, pk=None):
        """Soumet le rapport : il devient visible comme rendu."""
        report = self.get_object()
        if report.status == 'submitted':
            return Response(
                {'detail': 'Ce rapport est déjà soumis.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not report.summary.strip():
            return Response(
                {'detail': 'Le bilan doit être rempli avant de soumettre.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        report.submit()
        return Response(self.get_serializer(report).data)


class PayslipViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Bulletins de paie : tenus par le gérant, consultés par chacun."""

    serializer_class = PayslipSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile]
    filterset_class = PayslipFilter
    search_fields = ['member__user__first_name', 'member__user__last_name', 'notes']
    ordering_fields = ['month', 'created_at']
    ordering = ['-month']

    #: Actions qui touchent à la paie : le gérant seul les exerce.
    MANAGER_ACTIONS = ('create', 'update', 'partial_update', 'destroy', 'summary')

    def get_permissions(self):
        if self.action in self.MANAGER_ACTIONS:
            return [IsAuthenticated(), HasMemberProfile(), IsManager()]
        return super().get_permissions()

    def get_queryset(self):
        # `visible_to` tranche : tout pour le gérant, ses propres bulletins
        # pour les autres.
        return Payslip.objects.visible_to(self.member).with_related()

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Masse salariale du mois demandé."""
        month = parse_month(request)
        payslips = Payslip.objects.for_month(month)

        totals = payslips.aggregate(
            base=Sum('base_salary'), overtime=Sum('overtime_amount'),
            bonuses=Sum('bonuses'), deductions=Sum('deductions'),
            contributions=Sum('contributions'), hours=Sum('overtime_hours'),
            worked=Sum('worked_hours'),
        )
        gross = ((totals['base'] or 0) + (totals['overtime'] or 0)
                 + (totals['bonuses'] or 0))

        return Response({
            'month': f'{month:%Y-%m}',
            'count': payslips.count(),
            'team_size': Member.objects.active().count(),
            'gross': gross,
            'net': gross - (totals['deductions'] or 0) - (totals['contributions'] or 0),
            'worked_hours': totals['worked'] or 0,
            'overtime_hours': totals['hours'] or 0,
        })


class StaffEventViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Mises à pied, observations, retards et heures supplémentaires."""

    serializer_class = StaffEventSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile, IsManager]
    filterset_class = StaffEventFilter
    search_fields = ['reason', 'decision', 'member__user__first_name',
                     'member__user__last_name']
    ordering_fields = ['date', 'kind', 'created_at']
    ordering = ['-date']

    def get_queryset(self):
        return StaffEvent.objects.with_related()

    def perform_create(self, serializer):
        # L'auteur de la fiche est celui qui la saisit : une sanction doit
        # rester imputable.
        serializer.save(recorded_by=self.member)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Compte des évènements du mois, par nature."""
        month = parse_month(request)
        events = StaffEvent.objects.in_month(month)

        counts = {kind: 0 for kind, _ in StaffEvent.KIND_CHOICES}
        for row in events.values('kind').annotate(total=Count('id')):
            counts[row['kind']] = row['total']

        return Response({
            'month': f'{month:%Y-%m}',
            'total': events.count(),
            'counts': counts,
            'late_minutes': events.of_kind('lateness').aggregate(
                total=Sum('minutes'))['total'] or 0,
            'overtime_hours': events.of_kind('overtime').aggregate(
                total=Sum('hours'))['total'] or 0,
        })


class LeaveRequestViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Demandes de congé : chacun pose les siennes, la direction tranche."""

    serializer_class = LeaveRequestSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile, IsOwnerOrFounder]
    filterset_class = LeaveRequestFilter
    search_fields = ['reason', 'decision', 'member__user__first_name',
                     'member__user__last_name']
    ordering_fields = ['start_date', 'status', 'created_at']
    ordering = ['-start_date']

    def get_queryset(self):
        return LeaveRequest.objects.visible_to(self.member).with_related()

    def perform_create(self, serializer):
        # Une demande est toujours celle de son auteur : personne ne pose un
        # congé au nom d'un collègue, pas même la direction.
        serializer.save(member=self.member)

    def perform_update(self, serializer):
        """Une demande tranchée ne se retouche plus : elle se repose."""
        if not serializer.instance.is_pending:
            raise ValidationError({
                'detail': "Cette demande a reçu une réponse et n'est plus modifiable."
            })
        serializer.save()

    def perform_destroy(self, instance):
        if not instance.is_pending and not self.member.is_founder:
            raise ValidationError({
                'detail': "Cette demande a reçu une réponse : elle se retire "
                          "en l'annulant, pas en l'effaçant."
            })
        instance.delete()

    @action(detail=True, methods=['patch'], permission_classes=[
        IsAuthenticated, HasMemberProfile, IsFounder,
    ])
    def decide(self, request, pk=None):
        """Accorde ou refuse une demande (direction)."""
        demande = self.get_object()
        statut = request.data.get('status')

        if statut not in ('approved', 'refused'):
            return Response(
                {'status': "Décision attendue : « approved » ou « refused »."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if demande.status in ('cancelled',):
            return Response(
                {'detail': "Cette demande a été annulée par son auteur."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        demande.decide(statut, member=self.member,
                       decision=(request.data.get('decision') or '').strip())
        return Response(self.get_serializer(demande).data)

    @action(detail=True, methods=['patch'])
    def cancel(self, request, pk=None):
        """Retire une demande : son auteur y renonce, la direction la reprend."""
        demande = self.get_object()

        if demande.status in ('refused', 'cancelled'):
            return Response(
                {'detail': "Cette demande n'est plus en cours."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if demande.end_date < timezone.localdate():
            return Response(
                {'detail': "Un congé déjà écoulé ne s'annule plus."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        demande.decide('cancelled', member=self.member,
                       decision=(request.data.get('decision') or '').strip())
        return Response(self.get_serializer(demande).data)

    @action(detail=False, methods=['get'])
    def balance(self, request):
        """Solde de congés de l'année : le sien, ou celui de l'équipe.

        Le droit annuel est porté par le profil ; seuls les congés payés
        accordés l'entament, et les demandes en attente sont montrées à part —
        elles ne sont pas encore prises.
        """
        try:
            annee = int(request.query_params.get('year') or timezone.localdate().year)
        except ValueError:
            return Response({'error': "Année invalide."},
                            status=status.HTTP_400_BAD_REQUEST)

        lignes = []
        for membre in Member.objects.visible_to(self.member).active().with_user():
            demandes = LeaveRequest.objects.owned_by(membre).in_year(annee)
            pris = demandes.counted().total_days()
            lignes.append({
                'member_id': membre.pk,
                'member_name': membre.display_name,
                'department': membre.department,
                'entitlement': membre.leave_entitlement,
                'taken': pris,
                'pending': demandes.pending().total_days(),
                'balance': round(membre.leave_entitlement - pris, 1),
            })

        return Response({
            'year': annee,
            'members': sorted(lignes, key=lambda ligne: ligne['balance']),
        })


class AttendanceViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Pointage : chacun pointe sa journée, la direction relit et corrige."""

    serializer_class = AttendanceSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile]
    filterset_class = AttendanceFilter
    search_fields = ['note', 'member__user__first_name', 'member__user__last_name']
    ordering_fields = ['date', 'check_in', 'late_minutes']
    ordering = ['-date']

    #: Corriger un pointage revient à corriger des heures payées : l'équipe
    #: pointe, la direction seule retouche.
    DIRECTION_ACTIONS = ('create', 'update', 'partial_update', 'destroy')

    def get_permissions(self):
        if self.action in self.DIRECTION_ACTIONS:
            return [IsAuthenticated(), HasMemberProfile(), IsFounder()]
        return super().get_permissions()

    def get_queryset(self):
        return Attendance.objects.visible_to(self.member).with_related()

    @action(detail=False, methods=['get'])
    def today(self, request):
        """Sa journée en cours, et ce que le mois compte déjà."""
        jour = timezone.localdate()
        pointage = Attendance.objects.owned_by(self.member).for_date(jour).first()
        mois = Attendance.objects.owned_by(self.member).in_month(jour)

        conge = (LeaveRequest.objects.owned_by(self.member).approved()
                 .covering(jour).first())

        return Response({
            'date': jour,
            'attendance': self.get_serializer(pointage).data if pointage else None,
            'on_leave': LeaveRequestSerializer(conge).data if conge else None,
            'month': {
                'days': mois.count(),
                'hours': round(mois.total_minutes() / 60, 2),
                'late_minutes': mois.aggregate(total=Sum('late_minutes'))['total'] or 0,
            },
        })

    @action(detail=False, methods=['post'])
    def check_in(self, request):
        """Pointe l'arrivée du jour."""
        pointage, cree = Attendance.open_for(self.member)

        if not cree and not pointage.is_open:
            return Response(
                {'detail': "Votre journée est déjà pointée, départ compris."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            self.get_serializer(pointage).data,
            status=status.HTTP_201_CREATED if cree else status.HTTP_200_OK,
        )

    @action(detail=False, methods=['post'])
    def check_out(self, request):
        """Pointe le départ du jour."""
        pointage = Attendance.objects.owned_by(self.member).today().first()

        if pointage is None:
            return Response(
                {'detail': "Vous n'avez pas pointé votre arrivée aujourd'hui."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not pointage.is_open:
            return Response(
                {'detail': "Votre départ est déjà pointé."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        pointage.close()
        return Response(self.get_serializer(pointage).data)

    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Présence du mois, membre par membre.

        Les jours ouvrables écoulés servent de repère : ce qui n'est ni pointé
        ni couvert par un congé accordé compte comme une absence.
        """
        try:
            month = parse_month(request)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        debut, fin = month_range(months_back=0, reference=month)
        aujourdhui = timezone.localdate()
        # Un mois en cours ne se juge que sur les jours déjà passés.
        ouvrables = working_days(debut, min(fin, aujourdhui))

        pointages = Attendance.objects.visible_to(self.member).in_period(debut, fin)
        par_membre = Attendance.objects.hours_by_member(pointages.with_related())

        conges = {}
        for demande in (LeaveRequest.objects.visible_to(self.member).approved()
                        .in_period(debut, fin)):
            # Un congé à cheval sur deux mois ne compte ici que ses jours du mois.
            jours = working_days(max(demande.start_date, debut),
                                 min(demande.end_date, fin))
            conges[demande.member_id] = conges.get(demande.member_id, 0) + jours

        lignes = []
        for membre in Member.objects.visible_to(self.member).active().with_user():
            ligne = par_membre.get(membre.pk, {'days': 0, 'minutes': 0,
                                               'late_minutes': 0})
            jours_conges = conges.get(membre.pk, 0)
            lignes.append({
                'member_id': membre.pk,
                'member_name': membre.display_name,
                'department': membre.department,
                'job_title': membre.job_title,
                'days': ligne['days'],
                'hours': round(ligne['minutes'] / 60, 2),
                'late_minutes': ligne['late_minutes'],
                'leave_days': jours_conges,
                'absences': max(ouvrables - ligne['days'] - jours_conges, 0),
            })

        return Response({
            'month': f'{month:%Y-%m}',
            'working_days': ouvrables,
            'totals': {
                'members': len(lignes),
                'days': sum(l['days'] for l in lignes),
                'hours': round(sum(l['hours'] for l in lignes), 2),
                'late_minutes': sum(l['late_minutes'] for l in lignes),
                'leave_days': sum(l['leave_days'] for l in lignes),
                'absences': sum(l['absences'] for l in lignes),
            },
            'members': sorted(lignes, key=lambda l: (-l['absences'],
                                                     -l['late_minutes'],
                                                     l['member_name'])),
        })


class ReactionViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Points accordés par la direction ; chacun relit les siens."""

    serializer_class = ReactionSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile]
    filterset_class = ReactionFilter
    search_fields = ['reason', 'member__user__first_name', 'member__user__last_name']
    ordering_fields = ['date', 'points', 'created_at']
    ordering = ['-date']

    #: Accorder ou retirer des points engage la direction, pas l'équipe.
    WRITE_ACTIONS = ('create', 'update', 'partial_update', 'destroy')

    def get_permissions(self):
        if self.action in self.WRITE_ACTIONS:
            return [IsAuthenticated(), HasMemberProfile(), IsFounder()]
        return super().get_permissions()

    def get_queryset(self):
        return Reaction.objects.visible_to(self.member).with_related()

    def perform_create(self, serializer):
        serializer.save(author=self.member)

    @action(detail=False, methods=['get'])
    def scale(self, request):
        """Barème des réactions : natures, points par défaut, valeur du point."""
        return Response({
            'point_value': Reaction.POINT_VALUE,
            'kinds': [
                {
                    'kind': code,
                    'label': libelle,
                    'points': Reaction.DEFAULT_POINTS.get(code, 0),
                }
                for code, libelle in Reaction.KIND_CHOICES
            ],
        })


class SuggestionViewSet(MemberScopedMixin, viewsets.ModelViewSet):
    """Boîte à suggestions : chacun dépose, la direction relève."""

    serializer_class = SuggestionSerializer
    permission_classes = [IsAuthenticated, HasMemberProfile]
    filterset_class = SuggestionFilter
    search_fields = ['message', 'reply']
    ordering_fields = ['created_at', 'status']
    ordering = ['-created_at']

    def get_queryset(self):
        return Suggestion.objects.visible_to(self.member).with_related()

    def perform_create(self, serializer):
        serializer.save(author=self.member)

    def perform_update(self, serializer):
        """Son auteur corrige son message tant que personne ne l'a ouvert."""
        suggestion = serializer.instance
        if not self.member.is_founder and suggestion.status != 'new':
            raise ValidationError(
                {'detail': "Cette suggestion a été lue et n'est plus modifiable."}
            )
        serializer.save()

    def perform_destroy(self, instance):
        if not self.member.is_founder and instance.status != 'new':
            raise ValidationError(
                {'detail': "Cette suggestion a été lue et ne peut plus être retirée."}
            )
        instance.delete()

    @action(detail=True, methods=['patch'], permission_classes=[
        IsAuthenticated, HasMemberProfile, IsFounder,
    ])
    def handle(self, request, pk=None):
        """Marque la suggestion comme lue ou traitée, avec une réponse."""
        suggestion = self.get_object()
        statut = request.data.get('status', 'done')
        if statut not in dict(Suggestion.STATUS_CHOICES):
            return Response(
                {'status': f"État inconnu : {statut}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        suggestion.mark(statut, member=self.member,
                        reply=(request.data.get('reply') or '').strip())
        return Response(self.get_serializer(suggestion).data)


class DashboardViewSet(MemberScopedMixin, viewsets.ViewSet):
    """Vues d'ensemble : personnelle et, pour un fondateur, d'équipe."""

    permission_classes = [IsAuthenticated, HasMemberProfile]

    @action(detail=False, methods=['get'])
    def overview(self, request):
        """Tableau de bord du membre connecté."""
        member = self.member
        today = timezone.localdate()

        objective = MonthlyObjective.objects.owned_by(member).for_month().first()
        tasks_today = DailyTask.objects.owned_by(member).today()
        attendance = Attendance.objects.owned_by(member).for_date(today).first()
        leave = (LeaveRequest.objects.owned_by(member).approved()
                 .covering(today).first())
        roadmap = RoadmapItem.objects.owned_by(member).filter(
            objective__month=month_start()
        )
        last_report = Report.objects.owned_by(member).with_related().first()

        return Response({
            'member': MemberSerializer(member).data,
            'month': month_start().isoformat(),
            'objective': (
                MonthlyObjectiveDetailSerializer(objective).data if objective else None
            ),
            'tasks': {
                'total': tasks_today.count(),
                'done': tasks_today.done().count(),
                'blocked': tasks_today.blocked().count(),
                'late': DailyTask.objects.owned_by(member).late().count(),
                'items': DailyTaskSerializer(
                    tasks_today.order_by('-priority', 'id'), many=True
                ).data,
            },
            'roadmap': {
                'total': roadmap.count(),
                'done': roadmap.done().count(),
                'blocked': roadmap.blocked().count(),
                'overdue': roadmap.overdue().count(),
            },
            'attendance': (
                AttendanceSerializer(attendance).data if attendance else None
            ),
            'on_leave': LeaveRequestSerializer(leave).data if leave else None,
            'leave_balance': member.leave_balance,
            'last_report': ReportSerializer(last_report).data if last_report else None,
            'reports_this_month': Report.objects.owned_by(member).filter(
                period_end__gte=month_start(), period_end__lte=today
            ).count(),
        })

    @action(detail=False, methods=['get'])
    def notifications(self, request):
        """Alertes du moment pour le membre connecté.

        Elles ne sont pas stockées : chacune décrit une situation vérifiée à
        l'instant. Une tâche rattrapée ou une suggestion traitée fait
        disparaître la ligne d'elle-même, sans « marquer comme lu ».
        """
        member = self.member
        alertes = []

        objective = MonthlyObjective.objects.owned_by(member).for_month().first()
        if objective is None:
            alertes.append({
                'kind': 'objective_missing', 'level': 'info', 'page': 'objectives',
                'title': "Objectifs du mois non définis",
                'detail': "Fixez le chiffre d'affaires et les clients visés.",
                'count': 1,
            })
        elif objective.is_at_risk:
            alertes.append({
                'kind': 'objective_at_risk', 'level': 'warning', 'page': 'dashboard',
                'title': "Vous êtes en retard sur le mois",
                'detail': (f"{objective.completion:.0f} % atteint pour "
                           f"{objective.elapsed_ratio:.0f} % du mois écoulé."),
                'count': 1,
            })

        late = DailyTask.objects.owned_by(member).late().count()
        if late:
            alertes.append({
                'kind': 'tasks_late', 'level': 'warning', 'page': 'tasks',
                'title': f"{late} tâche(s) en retard",
                'detail': "Reportez-les ou terminez-les.",
                'count': late,
            })

        overdue = RoadmapItem.objects.owned_by(member).overdue().count()
        if overdue:
            alertes.append({
                'kind': 'roadmap_overdue', 'level': 'warning', 'page': 'roadmap',
                'title': f"{overdue} jalon(s) dépassé(s)",
                'detail': "Leur échéance est passée.",
                'count': overdue,
            })

        # Le pointage ne se rappelle qu'un jour ouvré, et pas à quelqu'un dont
        # le congé est accordé : lui reprocher son absence n'aurait aucun sens.
        jour = timezone.localdate()
        if jour.weekday() < 5:
            pointage = Attendance.objects.owned_by(member).for_date(jour).first()
            en_conge = (LeaveRequest.objects.owned_by(member).approved()
                        .covering(jour).exists())
            if pointage is None and not en_conge:
                alertes.append({
                    'kind': 'attendance_missing', 'level': 'info', 'page': None,
                    'title': "Vous n'avez pas pointé votre arrivée",
                    'detail': "Le pointage se fait depuis la barre du haut.",
                    'count': 1,
                })
            elif pointage is not None and pointage.is_open and not en_conge:
                alertes.append({
                    'kind': 'attendance_open', 'level': 'info', 'page': None,
                    'title': "Votre journée est en cours",
                    'detail': f"Arrivée à {timezone.localtime(pointage.check_in):%H:%M}, "
                              "départ non pointé.",
                    'count': 1,
                })

        # La boîte à suggestions et les congés ne sont relevés que par la direction.
        if member.is_founder:
            nouvelles = Suggestion.objects.pending().count()
            if nouvelles:
                alertes.append({
                    'kind': 'suggestions_new', 'level': 'info', 'page': None,
                    'title': f"{nouvelles} suggestion(s) à lire",
                    'detail': "Boîte à suggestions de l'équipe.",
                    'count': nouvelles,
                })

            demandes = LeaveRequest.objects.pending().count()
            if demandes:
                alertes.append({
                    'kind': 'leaves_pending', 'level': 'warning', 'page': 'leaves',
                    'title': f"{demandes} demande(s) de congé en attente",
                    'detail': "Elles attendent une réponse de la direction.",
                    'count': demandes,
                })

        return Response({
            'count': sum(a['count'] for a in alertes),
            'items': alertes,
        })

    @action(detail=False, methods=['get'], permission_classes=[
        IsAuthenticated, HasMemberProfile, IsFounder,
    ])
    def panel(self, request):
        """Activité de l'équipe à l'instant, membre par membre.

        Le panel répond à trois questions : qui travaille en ce moment, qui
        laisse ses tâches de côté, et quels rapports viennent d'arriver. Tout
        est recalculé à l'appel — le client rafraîchit, rien n'est mis en cache.
        """
        jour = timezone.localdate()
        maintenant = timezone.now()
        membres = Member.objects.active().with_user().order_by('user__first_name')

        taches = DailyTask.objects.for_date(jour).with_related()
        retards = DailyTask.objects.late()
        # Qui a pointé, qui est en congé : sans eux, une journée d'absence
        # ressemble à une journée sans tâches.
        pointages = {p.member_id: p for p in Attendance.objects.for_date(jour)}
        conges = {c.member_id: c
                  for c in LeaveRequest.objects.approved().covering(jour)}
        # Points du mois, en une requête pour toute l'équipe.
        points = dict(
            Reaction.objects.in_month(jour)
            .values_list('member_id')
            .annotate(total=Sum('points'))
        )

        # Un seul passage par collection : le nombre de membres est petit, mais
        # une requête par membre et par métrique le serait moins.
        par_membre = {membre.pk: {
            'total': 0, 'done': 0, 'running': None, 'minutes': 0, 'late': 0,
        } for membre in membres}

        for tache in taches:
            ligne = par_membre.get(tache.member_id)
            if ligne is None:
                continue
            ligne['total'] += 1
            if tache.status == 'done':
                ligne['done'] += 1
            if tache.started_at:
                ligne['minutes'] += tache.duration_minutes or 0
            if tache.status == 'in_progress' and tache.started_at:
                ligne['running'] = tache

        for tache in retards:
            ligne = par_membre.get(tache.member_id)
            if ligne is not None:
                ligne['late'] += 1

        lignes = []
        for membre in membres:
            ligne = par_membre[membre.pk]
            tache = ligne['running']
            pointage = pointages.get(membre.pk)
            conge = conges.get(membre.pk)

            # Un congé accordé prime sur tout le reste : il explique l'absence
            # de tâche comme de pointage.
            if conge is not None:
                etat = 'on_leave'
            elif tache is not None:
                etat = 'working'
            elif ligne['total'] == 0:
                etat = 'no_tasks'
            elif ligne['done'] == ligne['total']:
                etat = 'done'
            else:
                etat = 'idle'

            gagnes = points.get(membre.pk, 0)
            lignes.append({
                'member_id': membre.pk,
                'member_name': membre.display_name,
                'job_title': membre.job_title,
                'department': membre.department,
                'status': etat,
                'points_month': gagnes,
                'bonus_earned': max(gagnes, 0) * Reaction.POINT_VALUE,
                'tasks_total': ligne['total'],
                'tasks_done': ligne['done'],
                'tasks_late': ligne['late'],
                'minutes_logged': ligne['minutes'],
                'on_leave': conge.get_kind_display() if conge is not None else '',
                'attendance': {
                    'check_in': pointage.check_in,
                    'check_out': pointage.check_out,
                    'is_open': pointage.is_open,
                    'late_minutes': pointage.late_minutes,
                    'duration_label': pointage.duration_label,
                } if pointage is not None else None,
                'current_task': {
                    'id': tache.id,
                    'title': tache.title,
                    'started_at': tache.started_at,
                    'duration_minutes': tache.duration_minutes,
                    'duration_label': tache.duration_label,
                    'over_estimate': tache.over_estimate,
                } if tache is not None else None,
            })

        # L'ordre porte le message : ce qui cloche d'abord, le reste ensuite.
        # Un congé accordé ne cloche pas : il ferme la liste.
        rang = {'idle': 0, 'no_tasks': 1, 'working': 2, 'done': 3, 'on_leave': 4}
        lignes.sort(key=lambda l: (rang[l['status']], -l['tasks_late'],
                                   -l['minutes_logged'], l['member_name']))

        rapports = Report.objects.with_related()[:8]

        return Response({
            'generated_at': maintenant,
            'date': jour,
            'totals': {
                'team_size': len(lignes),
                'working': sum(1 for l in lignes if l['status'] == 'working'),
                'idle': sum(1 for l in lignes if l['status'] == 'idle'),
                'no_tasks': sum(1 for l in lignes if l['status'] == 'no_tasks'),
                'on_leave': sum(1 for l in lignes if l['status'] == 'on_leave'),
                'checked_in': sum(1 for l in lignes if l['attendance']),
                'late_arrivals': sum(1 for l in lignes if l['attendance']
                                     and l['attendance']['late_minutes']),
                'minutes_logged': sum(l['minutes_logged'] for l in lignes),
                'tasks_total': sum(l['tasks_total'] for l in lignes),
                'tasks_done': sum(l['tasks_done'] for l in lignes),
                'tasks_late': sum(l['tasks_late'] for l in lignes),
                'points_month': sum(l['points_month'] for l in lignes),
            },
            'members': lignes,
            'recent_reports': ReportSerializer(rapports, many=True).data,
        })

    @action(detail=False, methods=['get'], permission_classes=[
        IsAuthenticated, HasMemberProfile, IsFounder,
    ])
    def team(self, request):
        """Synthèse de l'équipe pour le mois demandé (fondateurs)."""
        try:
            month = parse_month(request)
        except ValueError as exc:
            return Response({'error': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        month_end = month_range(months_back=0, reference=month)[1]

        objectives = MonthlyObjective.objects.filter(month=month).select_related(
            'member', 'member__user'
        )
        by_member = {obj.member_id: obj for obj in objectives}

        # Compteurs agrégés en deux requêtes plutôt qu'une par membre, et
        # bornés au mois affiché : la ligne entière décrit alors la même période.
        open_tasks = dict(
            DailyTask.objects.exclude(status='done')
            .filter(date__range=[month, month_end])
            .values_list('member_id').annotate(n=Count('id'))
        )
        # Un rapport compte dès qu'il couvre une partie du mois : une semaine à
        # cheval sur deux mois appartient aux deux.
        submitted_reports = dict(
            Report.objects.submitted()
            .filter(period_start__lte=month_end, period_end__gte=month)
            .values_list('member_id').annotate(n=Count('id'))
        )

        rows = []
        for member in Member.objects.active().with_user():
            objective = by_member.get(member.pk)
            rows.append({
                'member_id': member.pk,
                'member_name': member.display_name,
                'department': member.get_department_display(),
                'job_title': member.job_title,
                'has_objective': objective is not None,
                'revenue_target': float(objective.revenue_target) if objective else 0.0,
                'revenue_achieved': float(objective.revenue_achieved) if objective else 0.0,
                'clients_target': objective.clients_target if objective else 0,
                'clients_achieved': objective.clients_achieved if objective else 0,
                'completion': objective.completion if objective else None,
                'is_at_risk': objective.is_at_risk if objective else False,
                'focus': objective.focus if objective else '',
                'open_tasks': open_tasks.get(member.pk, 0),
                'reports_submitted': submitted_reports.get(member.pk, 0),
            })

        totals = MonthlyObjective.objects.totals(objectives)
        revenue_target = float(totals['revenue_target'] or 0)
        revenue_achieved = float(totals['revenue_achieved'] or 0)

        return Response({
            'month': month.isoformat(),
            'team_size': len(rows),
            'members_with_objective': sum(1 for r in rows if r['has_objective']),
            'members_at_risk': sum(1 for r in rows if r['is_at_risk']),
            'revenue_target': revenue_target,
            'revenue_achieved': revenue_achieved,
            'revenue_completion': (
                round(revenue_achieved / revenue_target * 100, 1)
                if revenue_target else None
            ),
            'clients_target': totals['clients_target'] or 0,
            'clients_achieved': totals['clients_achieved'] or 0,
            'members': sorted(rows, key=lambda r: (r['completion'] is None, r['completion'] or 0)),
        })

    @action(detail=False, methods=['get'])
    def activity(self, request):
        """Activité des N derniers jours : tâches créées et terminées."""
        try:
            days = max(1, min(int(request.query_params.get('days', 14)), 90))
        except ValueError:
            return Response(
                {'error': 'Le paramètre days doit être un entier'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        end = timezone.localdate()
        start = end - timedelta(days=days - 1)
        tasks = DailyTask.objects.visible_to(self.member).in_period(start, end)

        buckets = {
            row['date']: row
            for row in tasks.values('date').annotate(
                total=Count('id'),
                done=Count('id', filter=Q(status='done')),
            )
        }

        return Response([
            {
                'date': (start + timedelta(days=offset)).isoformat(),
                'total': buckets.get(start + timedelta(days=offset), {}).get('total', 0),
                'done': buckets.get(start + timedelta(days=offset), {}).get('done', 0),
            }
            for offset in range(days)
        ])
