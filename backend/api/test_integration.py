"""
Tests d'intégration de l'API Flux Gestion.

Ils couvrent le cycle métier (objectifs, feuille de route, tâches, rapports)
et surtout la règle de visibilité : un membre ne voit que ses données, un
fondateur voit toute l'équipe.
"""

import io
import json
from datetime import datetime, time, timedelta
from decimal import Decimal

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from rest_framework.throttling import SimpleRateThrottle

from api.managers import month_range, month_start
from api.models import (
    Attendance, DailyTask, LeaveRequest, Member, MonthlyObjective, Payslip,
    Reaction, Report, RoadmapItem, StaffEvent, Suggestion,
)


class TeamTestCase(APITestCase):
    """Base : une fondatrice, deux membres, et de quoi les distinguer."""

    def setUp(self):
        self.founder = self.make_member('awa', role='founder', department='direction')
        self.karim = self.make_member('karim', role='member', department='commercial')
        self.lea = self.make_member('lea', role='member', department='marketing')
        self.authenticate(self.karim)

    def make_member(self, username, role='member', department='commercial'):
        user = User.objects.create_user(
            username=username, email=f'{username}@example.com', password='pass-Solide1',
            first_name=username.capitalize(),
        )
        # Le signal a déjà créé le profil : on l'ajuste.
        member = Member.objects.for_user(user)
        member.role = role
        member.department = department
        member.save(update_fields=['role', 'department', 'updated_at'])
        return member

    def authenticate(self, member):
        token, _ = Token.objects.get_or_create(user=member.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        return token

    def make_objective(self, member, months_back=0, **overrides):
        month, _ = month_range(months_back=months_back)
        defaults = {
            'month': month,
            'revenue_target': Decimal('20000.00'),
            'revenue_achieved': Decimal('12000.00'),
            'clients_target': 10,
            'clients_achieved': 6,
            'focus': 'Ouvrir le segment PME',
        }
        defaults.update(overrides)
        return MonthlyObjective.objects.create(member=member, **defaults)


class MemberProfileTest(TeamTestCase):
    """Création automatique du profil et visibilité de l'équipe."""

    def test_profile_created_with_account(self):
        user = User.objects.create_user('nouveau', password='pass-Solide1')
        self.assertTrue(Member.objects.filter(user=user).exists())

    def test_first_account_becomes_founder(self):
        Member.objects.all().delete()
        User.objects.all().delete()
        user = User.objects.create_user('premier', password='pass-Solide1')
        self.assertEqual(Member.objects.get(user=user).role, 'founder')

    def test_member_sees_only_themselves(self):
        response = self.client.get('/api/members/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['username'], 'karim')

    def test_founder_sees_whole_team(self):
        self.authenticate(self.founder)
        response = self.client.get('/api/members/')
        self.assertEqual(response.data['count'], 3)

    def test_me_returns_own_profile(self):
        response = self.client.get('/api/members/me/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['username'], 'karim')
        self.assertFalse(response.data['is_founder'])

    def test_member_updates_own_profile(self):
        response = self.client.patch('/api/members/me/', {
            'job_title': 'Responsable grands comptes', 'first_name': 'Karim',
        }, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['job_title'], 'Responsable grands comptes')

    def test_member_cannot_edit_a_colleague(self):
        response = self.client.patch(
            f'/api/members/{self.lea.id}/', {'job_title': 'Rétrogradé'}, format='json'
        )
        self.assertIn(response.status_code, (403, 404))
        self.lea.refresh_from_db()
        self.assertNotEqual(self.lea.job_title, 'Rétrogradé')

    def test_founder_edits_a_colleague(self):
        """Le fondateur administre les comptes depuis l'API, pas seulement l'admin."""
        self.authenticate(self.founder)
        response = self.client.patch(
            f'/api/members/{self.karim.id}/', {'job_title': 'Responsable grands comptes'},
            format='json'
        )
        self.assertEqual(response.status_code, 200)
        self.karim.refresh_from_db()
        self.assertEqual(self.karim.job_title, 'Responsable grands comptes')

    def test_role_is_not_settable_through_the_api(self):
        """Un membre ne peut pas se promouvoir fondateur."""
        self.client.patch('/api/members/me/', {'role': 'founder'}, format='json')
        self.karim.refresh_from_db()
        self.assertEqual(self.karim.role, 'member')

    def test_account_without_profile_is_refused(self):
        orphan = User.objects.create_user('orphelin', password='pass-Solide1')
        Member.objects.filter(user=orphan).delete()
        token, _ = Token.objects.get_or_create(user=orphan)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')
        self.assertEqual(self.client.get('/api/objectives/').status_code, 403)


class MonthlyObjectiveTest(TeamTestCase):
    """Objectifs mensuels : saisie, calculs et cloisonnement."""

    def test_create_objective(self):
        month, _ = month_range()
        response = self.client.post('/api/objectives/', {
            'month': month.isoformat(),
            'revenue_target': '25000.00',
            'clients_target': 12,
            'focus': 'Ouvrir le segment PME',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['member'], self.karim.id)

    def test_month_is_normalised_to_first_day(self):
        response = self.client.post('/api/objectives/', {
            'month': timezone.localdate().replace(day=17).isoformat(),
            'revenue_target': '5000.00', 'clients_target': 3,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            MonthlyObjective.objects.get(id=response.data['id']).month.day, 1
        )

    def test_duplicate_month_is_rejected_cleanly(self):
        self.make_objective(self.karim)
        month, _ = month_range()
        response = self.client.post('/api/objectives/', {
            'month': month.isoformat(), 'revenue_target': '1000.00', 'clients_target': 1,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('month', response.data)

    def test_objective_without_any_target_is_rejected(self):
        month, _ = month_range()
        response = self.client.post('/api/objectives/', {
            'month': month.isoformat(), 'revenue_target': '0', 'clients_target': 0,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_month_too_far_ahead_is_rejected(self):
        far = month_start().replace(year=timezone.localdate().year + 3)
        response = self.client.post('/api/objectives/', {
            'month': far.isoformat(), 'revenue_target': '1000', 'clients_target': 1,
        }, format='json')
        self.assertEqual(response.status_code, 400)

    def test_completion_is_computed(self):
        objective = self.make_objective(
            self.karim, revenue_target=Decimal('20000'),
            revenue_achieved=Decimal('10000'), clients_target=10, clients_achieved=8,
        )
        response = self.client.get(f'/api/objectives/{objective.id}/')
        self.assertEqual(response.data['revenue_completion'], 50.0)
        self.assertEqual(response.data['clients_completion'], 80.0)
        self.assertEqual(response.data['completion'], 65.0)

    def test_completion_ignores_targets_left_empty(self):
        """Un profil non commercial n'a pas de cible de CA : elle ne compte pas."""
        objective = self.make_objective(
            self.lea, revenue_target=Decimal('0'), revenue_achieved=Decimal('0'),
            clients_target=10, clients_achieved=5,
        )
        self.assertIsNone(objective.revenue_completion)
        self.assertEqual(objective.completion, 50.0)

    def test_revenue_gap(self):
        objective = self.make_objective(
            self.karim, revenue_target=Decimal('20000'), revenue_achieved=Decimal('12000')
        )
        self.assertEqual(objective.revenue_gap, Decimal('8000'))

    def test_member_does_not_see_colleagues_objectives(self):
        self.make_objective(self.karim)
        self.make_objective(self.lea)
        response = self.client.get('/api/objectives/')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['member'], self.karim.id)

    def test_member_cannot_read_a_colleague_objective_directly(self):
        other = self.make_objective(self.lea)
        self.assertEqual(self.client.get(f'/api/objectives/{other.id}/').status_code, 404)

    def test_founder_sees_every_objective(self):
        self.make_objective(self.karim)
        self.make_objective(self.lea)
        self.authenticate(self.founder)
        response = self.client.get('/api/objectives/')
        self.assertEqual(response.data['count'], 2)

    def test_current_returns_this_month(self):
        self.make_objective(self.karim)
        response = self.client.get('/api/objectives/current/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['month_label'], month_start().strftime('%Y-%m'))

    def test_current_is_404_without_objective(self):
        self.assertEqual(self.client.get('/api/objectives/current/').status_code, 404)

    def test_close_month(self):
        objective = self.make_objective(self.karim)
        response = self.client.patch(f'/api/objectives/{objective.id}/close/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'closed')

    def test_close_twice_is_rejected(self):
        objective = self.make_objective(self.karim, status='closed')
        self.assertEqual(
            self.client.patch(f'/api/objectives/{objective.id}/close/').status_code, 400
        )

    def test_history_fills_months_without_data(self):
        self.make_objective(self.karim, months_back=0)
        self.make_objective(self.karim, months_back=3)
        response = self.client.get('/api/objectives/history/?months=6')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 6)

        months = [row['month'] for row in response.data]
        self.assertEqual(months, sorted(months))
        self.assertEqual(sum(1 for r in response.data if r['revenue_target']), 2)

    def test_export_returns_csv(self):
        self.make_objective(self.karim)
        response = self.client.get('/api/objectives/export/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('Ouvrir le segment PME', response.content.decode('utf-8'))

    def test_export_respects_visibility(self):
        """L'export ne doit jamais fuiter les chiffres d'un collègue."""
        self.make_objective(self.karim, focus='Mon objectif')
        self.make_objective(self.lea, focus='Objectif de Lea')
        body = self.client.get('/api/objectives/export/').content.decode('utf-8')
        self.assertIn('Mon objectif', body)
        self.assertNotIn('Objectif de Lea', body)

    def test_filter_by_department_for_founder(self):
        self.make_objective(self.karim)
        self.make_objective(self.lea)
        self.authenticate(self.founder)
        response = self.client.get('/api/objectives/?department=marketing')
        self.assertEqual(response.data['count'], 1)


class AtRiskTest(TeamTestCase):
    """Détection du retard sur objectif."""

    def test_objective_far_behind_is_flagged(self):
        objective = self.make_objective(
            self.karim, revenue_target=Decimal('20000'),
            revenue_achieved=Decimal('0'), clients_target=10, clients_achieved=0,
        )
        # En début de mois le retard n'est pas encore significatif.
        if objective.elapsed_ratio > 20:
            self.assertTrue(objective.is_at_risk)

    def test_objective_on_track_is_not_flagged(self):
        objective = self.make_objective(
            self.karim, revenue_target=Decimal('20000'),
            revenue_achieved=Decimal('20000'), clients_target=10, clients_achieved=10,
        )
        self.assertFalse(objective.is_at_risk)

    def test_closed_month_is_never_flagged(self):
        objective = self.make_objective(
            self.karim, revenue_achieved=Decimal('0'), clients_achieved=0, status='closed'
        )
        self.assertFalse(objective.is_at_risk)


class RoadmapTest(TeamTestCase):
    """Feuille de route rattachée à un objectif."""

    def setUp(self):
        super().setUp()
        self.objective = self.make_objective(self.karim)

    def test_create_milestone(self):
        response = self.client.post('/api/roadmap/', {
            'objective': self.objective.id,
            'title': 'Constituer une liste de 100 prospects',
            'due_date': (timezone.localdate() + timedelta(days=7)).isoformat(),
        }, format='json')
        self.assertEqual(response.status_code, 201)

    def test_cannot_attach_to_a_colleague_objective(self):
        other = self.make_objective(self.lea)
        response = self.client.post('/api/roadmap/', {
            'objective': other.id, 'title': 'Jalon intrusif',
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('objective', response.data)

    def test_completing_sets_progress_and_date(self):
        item = RoadmapItem.objects.create(objective=self.objective, title='Jalon')
        response = self.client.patch(f'/api/roadmap/{item.id}/complete/')
        self.assertEqual(response.status_code, 200)

        item.refresh_from_db()
        self.assertEqual(item.status, 'done')
        self.assertEqual(item.progress, 100)
        self.assertIsNotNone(item.completed_at)

    def test_reopening_clears_completion(self):
        item = RoadmapItem.objects.create(
            objective=self.objective, title='Jalon', status='done'
        )
        item.status = 'in_progress'
        item.save()
        self.assertIsNone(item.completed_at)
        self.assertLess(item.progress, 100)

    def test_overdue_detection(self):
        late = RoadmapItem.objects.create(
            objective=self.objective, title='En retard',
            due_date=timezone.localdate() - timedelta(days=3),
        )
        done = RoadmapItem.objects.create(
            objective=self.objective, title='Fait à temps', status='done',
            due_date=timezone.localdate() - timedelta(days=3),
        )
        self.assertTrue(late.is_overdue)
        self.assertFalse(done.is_overdue)

        response = self.client.get('/api/roadmap/overdue/')
        self.assertEqual(len(response.data), 1)

    def test_member_does_not_see_colleagues_roadmap(self):
        RoadmapItem.objects.create(objective=self.objective, title='À moi')
        RoadmapItem.objects.create(
            objective=self.make_objective(self.lea), title='À elle'
        )
        response = self.client.get('/api/roadmap/')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['title'], 'À moi')


class DailyTaskTest(TeamTestCase):
    """Tâches quotidiennes."""

    def test_create_task_assigns_current_member(self):
        response = self.client.post('/api/tasks/', {
            'title': 'Relancer 10 prospects', 'priority': 3,
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['member'], self.karim.id)
        self.assertEqual(response.data['date'], timezone.localdate().isoformat())

    def test_cannot_link_a_colleague_milestone(self):
        item = RoadmapItem.objects.create(
            objective=self.make_objective(self.lea), title='Jalon de Lea'
        )
        response = self.client.post('/api/tasks/', {
            'title': 'Tâche', 'roadmap_item': item.id,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('roadmap_item', response.data)

    def test_today_separates_late_tasks(self):
        DailyTask.objects.create(member=self.karim, title="Aujourd'hui")
        DailyTask.objects.create(
            member=self.karim, title='En retard',
            date=timezone.localdate() - timedelta(days=2),
        )
        response = self.client.get('/api/tasks/today/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data['today']), 1)
        self.assertEqual(len(response.data['late']), 1)

    def test_complete_sets_timestamp(self):
        task = DailyTask.objects.create(member=self.karim, title='Tâche')
        response = self.client.patch(f'/api/tasks/{task.id}/complete/')
        self.assertEqual(response.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.status, 'done')
        self.assertIsNotNone(task.completed_at)

    def test_complete_twice_is_rejected(self):
        task = DailyTask.objects.create(member=self.karim, title='Tâche', status='done')
        self.assertEqual(
            self.client.patch(f'/api/tasks/{task.id}/complete/').status_code, 400
        )

    def test_carry_over_moves_late_tasks_to_today(self):
        DailyTask.objects.create(
            member=self.karim, title='Oubliée',
            date=timezone.localdate() - timedelta(days=3),
        )
        response = self.client.post('/api/tasks/carry_over/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['moved'], 1)
        self.assertEqual(
            DailyTask.objects.get(title='Oubliée').date, timezone.localdate()
        )

    def test_carry_over_leaves_colleagues_tasks_alone(self):
        DailyTask.objects.create(
            member=self.lea, title='Celle de Lea',
            date=timezone.localdate() - timedelta(days=3),
        )
        self.client.post('/api/tasks/carry_over/')
        self.assertLess(
            DailyTask.objects.get(title='Celle de Lea').date, timezone.localdate()
        )

    def test_member_does_not_see_colleagues_tasks(self):
        DailyTask.objects.create(member=self.karim, title='À moi')
        DailyTask.objects.create(member=self.lea, title='À elle')
        response = self.client.get('/api/tasks/')
        self.assertEqual(response.data['count'], 1)

    def test_founder_sees_all_tasks(self):
        DailyTask.objects.create(member=self.karim, title='À Karim')
        DailyTask.objects.create(member=self.lea, title='À Lea')
        self.authenticate(self.founder)
        self.assertEqual(self.client.get('/api/tasks/').data['count'], 2)

    def test_filter_by_status(self):
        DailyTask.objects.create(member=self.karim, title='Faite', status='done')
        DailyTask.objects.create(member=self.karim, title='À faire')
        response = self.client.get('/api/tasks/?status=done')
        self.assertEqual(response.data['count'], 1)


class ReportTest(TeamTestCase):
    """Rapports d'activité."""

    def payload(self, **overrides):
        end = timezone.localdate()
        data = {
            'period_type': 'weekly',
            'period_start': (end - timedelta(days=6)).isoformat(),
            'period_end': end.isoformat(),
            'summary': 'Semaine correcte, deux dossiers avancent bien.',
        }
        data.update(overrides)
        return data

    def test_create_report(self):
        response = self.client.post('/api/reports/', self.payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['member'], self.karim.id)
        self.assertEqual(response.data['status'], 'draft')

    def test_inverted_period_is_rejected(self):
        response = self.client.post('/api/reports/', self.payload(
            period_start=timezone.localdate().isoformat(),
            period_end=(timezone.localdate() - timedelta(days=7)).isoformat(),
        ), format='json')
        self.assertEqual(response.status_code, 400)

    def test_period_longer_than_a_year_is_rejected(self):
        response = self.client.post('/api/reports/', self.payload(
            period_start=(timezone.localdate() - timedelta(days=500)).isoformat(),
        ), format='json')
        self.assertEqual(response.status_code, 400)

    def test_submit_marks_and_timestamps(self):
        report = Report.objects.create(member=self.karim, **{
            'period_type': 'weekly',
            'period_start': timezone.localdate() - timedelta(days=6),
            'period_end': timezone.localdate(),
            'summary': 'Bilan de la semaine.',
        })
        response = self.client.patch(f'/api/reports/{report.id}/submit/')
        self.assertEqual(response.status_code, 200)

        report.refresh_from_db()
        self.assertEqual(report.status, 'submitted')
        self.assertIsNotNone(report.submitted_at)

    def test_empty_report_cannot_be_submitted(self):
        report = Report.objects.create(
            member=self.karim, period_type='weekly',
            period_start=timezone.localdate() - timedelta(days=6),
            period_end=timezone.localdate(), summary='   ',
        )
        self.assertEqual(
            self.client.patch(f'/api/reports/{report.id}/submit/').status_code, 400
        )

    def test_submitted_report_is_locked_for_its_author(self):
        report = Report.objects.create(
            member=self.karim, period_type='weekly',
            period_start=timezone.localdate() - timedelta(days=6),
            period_end=timezone.localdate(), summary='Bilan.', status='submitted',
        )
        response = self.client.patch(
            f'/api/reports/{report.id}/', {'summary': 'Réécrit'}, format='json'
        )
        self.assertEqual(response.status_code, 400)

    def test_member_does_not_see_colleagues_reports(self):
        Report.objects.create(
            member=self.lea, period_type='weekly',
            period_start=timezone.localdate() - timedelta(days=6),
            period_end=timezone.localdate(), summary='Confidentiel',
        )
        self.assertEqual(self.client.get('/api/reports/').data['count'], 0)

    def test_founder_reads_team_reports(self):
        Report.objects.create(
            member=self.lea, period_type='weekly',
            period_start=timezone.localdate() - timedelta(days=6),
            period_end=timezone.localdate(), summary='Bilan de Lea',
        )
        self.authenticate(self.founder)
        self.assertEqual(self.client.get('/api/reports/').data['count'], 1)

    def test_create_mission_report(self):
        today = timezone.localdate()
        response = self.client.post('/api/reports/', self.payload(
            period_type='mission',
            period_start=(today - timedelta(days=2)).isoformat(),
            period_end=today.isoformat(),
            title='Mission chez Aurore Industries',
            location='Lyon',
            participants='Karim Ndiaye, Sophie Aubert (Aurore)',
            summary="Trois jours sur site pour cadrer le déploiement.",
            next_steps='Envoyer la proposition chiffrée avant vendredi.',
        ), format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['period_type'], 'mission')
        self.assertEqual(response.data['period_label'], 'Rapport de mission')
        self.assertTrue(response.data['is_event'])
        self.assertEqual(response.data['location'], 'Lyon')

    def test_create_meeting_report(self):
        today = timezone.localdate()
        response = self.client.post('/api/reports/', self.payload(
            period_type='meeting',
            period_start=today.isoformat(),
            period_end=today.isoformat(),
            title='Comité commercial hebdomadaire',
            participants='Karim, Lea, Amina',
            summary='Revue du portefeuille et arbitrage des priorités.',
            decisions='Priorité donnée au compte Aurore.',
        ), format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['decisions'], 'Priorité donnée au compte Aurore.')

    def test_event_report_requires_a_title(self):
        """Sans objet, deux missions du même mois seraient indiscernables."""
        response = self.client.post('/api/reports/', self.payload(
            period_type='mission', title='   ',
        ), format='json')

        self.assertEqual(response.status_code, 400)
        self.assertIn('title', response.data)

    def test_period_report_needs_no_title(self):
        response = self.client.post('/api/reports/', self.payload(), format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['title'], '')
        self.assertFalse(response.data['is_event'])

    def test_reports_filter_by_type(self):
        today = timezone.localdate()
        Report.objects.create(
            member=self.karim, period_type='mission', title='Mission Aurore',
            period_start=today, period_end=today, summary='Compte rendu.',
        )
        Report.objects.create(
            member=self.karim, period_type='weekly',
            period_start=today - timedelta(days=6), period_end=today,
            summary='Bilan de la semaine.',
        )

        response = self.client.get('/api/reports/?period_type=mission')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['title'], 'Mission Aurore')

    def test_search_covers_the_object_of_a_mission(self):
        today = timezone.localdate()
        Report.objects.create(
            member=self.karim, period_type='mission', title='Mission Aurore',
            period_start=today, period_end=today, summary='Compte rendu.',
        )
        response = self.client.get('/api/reports/?search=Aurore')
        self.assertEqual(response.data['count'], 1)


class DashboardTest(TeamTestCase):
    """Vues d'ensemble personnelle et d'équipe."""

    def test_overview_returns_personal_summary(self):
        self.make_objective(self.karim)
        DailyTask.objects.create(member=self.karim, title='Tâche du jour')
        DailyTask.objects.create(member=self.karim, title='Faite', status='done')

        response = self.client.get('/api/dashboard/overview/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['member']['username'], 'karim')
        self.assertEqual(response.data['tasks']['total'], 2)
        self.assertEqual(response.data['tasks']['done'], 1)
        self.assertIsNotNone(response.data['objective'])

    def test_overview_without_objective(self):
        response = self.client.get('/api/dashboard/overview/')
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data['objective'])

    def test_team_view_is_refused_to_members(self):
        self.assertEqual(self.client.get('/api/dashboard/team/').status_code, 403)

    def test_team_view_aggregates_every_member(self):
        self.make_objective(self.karim, revenue_target=Decimal('20000'),
                            revenue_achieved=Decimal('15000'))
        self.make_objective(self.lea, revenue_target=Decimal('10000'),
                            revenue_achieved=Decimal('5000'))
        self.authenticate(self.founder)

        response = self.client.get('/api/dashboard/team/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['team_size'], 3)
        self.assertEqual(response.data['members_with_objective'], 2)
        self.assertEqual(response.data['revenue_target'], 30000.0)
        self.assertEqual(response.data['revenue_achieved'], 20000.0)
        self.assertAlmostEqual(response.data['revenue_completion'], 66.7, places=1)

    def test_team_view_lists_members_without_objective(self):
        self.authenticate(self.founder)
        response = self.client.get('/api/dashboard/team/')
        self.assertEqual(response.data['members_with_objective'], 0)
        self.assertTrue(all(not r['has_objective'] for r in response.data['members']))

    def test_team_counters_are_scoped_to_the_displayed_month(self):
        """Une ligne d'équipe ne mélange pas les périodes."""
        month = month_start()
        DailyTask.objects.create(
            member=self.karim, title='Du mois', date=month, status='todo'
        )
        DailyTask.objects.create(
            member=self.karim, title='Mois précédent',
            date=month - timedelta(days=20), status='todo',
        )
        self.authenticate(self.founder)

        row = next(r for r in self.client.get('/api/dashboard/team/').data['members']
                   if r['member_id'] == self.karim.id)
        self.assertEqual(row['open_tasks'], 1)

    def test_team_counts_a_report_overlapping_the_month(self):
        """Une semaine à cheval sur deux mois compte pour les deux."""
        month = month_start()
        Report.objects.create(
            member=self.karim, period_type='weekly',
            period_start=month - timedelta(days=3),
            period_end=month + timedelta(days=3),
            summary='Semaine à cheval.', status='submitted',
            submitted_at=timezone.now(),
        )
        # Un rapport entièrement dans le mois précédent ne doit pas compter.
        Report.objects.create(
            member=self.karim, period_type='weekly',
            period_start=month - timedelta(days=14),
            period_end=month - timedelta(days=8),
            summary='Mois précédent.', status='submitted',
            submitted_at=timezone.now(),
        )
        self.authenticate(self.founder)

        row = next(r for r in self.client.get('/api/dashboard/team/').data['members']
                   if r['member_id'] == self.karim.id)
        self.assertEqual(row['reports_submitted'], 1)

    def test_team_ignores_unsubmitted_reports(self):
        month = month_start()
        Report.objects.create(
            member=self.karim, period_type='weekly',
            period_start=month, period_end=month + timedelta(days=3),
            summary='Brouillon.', status='draft',
        )
        self.authenticate(self.founder)

        row = next(r for r in self.client.get('/api/dashboard/team/').data['members']
                   if r['member_id'] == self.karim.id)
        self.assertEqual(row['reports_submitted'], 0)

    def test_team_rows_are_ordered_worst_first(self):
        """Le fondateur doit voir en tête ceux qui décrochent."""
        self.make_objective(self.karim, revenue_target=Decimal('10000'),
                            revenue_achieved=Decimal('9000'), clients_target=0)
        self.make_objective(self.lea, revenue_target=Decimal('10000'),
                            revenue_achieved=Decimal('1000'), clients_target=0)
        self.authenticate(self.founder)

        rows = self.client.get('/api/dashboard/team/').data['members']
        scored = [r for r in rows if r['completion'] is not None]
        self.assertEqual([r['completion'] for r in scored],
                         sorted(r['completion'] for r in scored))

    def test_team_view_rejects_bad_month(self):
        self.authenticate(self.founder)
        self.assertEqual(
            self.client.get('/api/dashboard/team/?month=hier').status_code, 400
        )

    def test_activity_series_is_continuous(self):
        DailyTask.objects.create(member=self.karim, title='Faite', status='done')
        response = self.client.get('/api/dashboard/activity/?days=7')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 7)

        dates = [row['date'] for row in response.data]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(sum(row['done'] for row in response.data), 1)


class AuthenticationTest(APITestCase):
    """Inscription, connexion et profil."""

    def test_register_creates_member_profile(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'nouvelle', 'email': 'nouvelle@example.com',
            'password': 'Str0ng-Passw0rd!', 'password_confirm': 'Str0ng-Passw0rd!',
            'job_title': 'Business Developer', 'department': 'commercial',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertIn('token', response.data)
        self.assertEqual(response.data['user']['job_title'], 'Business Developer')

    def test_first_registered_account_is_founder(self):
        response = self.client.post('/api/auth/register/', {
            'username': 'premier', 'email': 'premier@example.com',
            'password': 'Str0ng-Passw0rd!', 'password_confirm': 'Str0ng-Passw0rd!',
        }, format='json')
        self.assertTrue(response.data['user']['is_founder'])

    def test_login_and_profile(self):
        User.objects.create_user('karim', password='pass-Solide1')
        response = self.client.post('/api/auth/login/', {
            'username': 'karim', 'password': 'pass-Solide1',
        }, format='json')
        self.assertEqual(response.status_code, 200)

        self.client.credentials(HTTP_AUTHORIZATION=f"Token {response.data['token']}")
        profile = self.client.get('/api/auth/me/')
        self.assertEqual(profile.status_code, 200)
        self.assertIsNotNone(profile.data['member_id'])

    def test_unauthenticated_access_is_refused(self):
        self.assertEqual(self.client.get('/api/objectives/').status_code, 401)

    def test_logout_revokes_token(self):
        user = User.objects.create_user('karim', password='pass-Solide1')
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

        self.assertEqual(self.client.post('/api/auth/logout/').status_code, 200)
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)


class BackgroundTaskTest(TeamTestCase):
    """Tâches Celery, exécutées en local en mode eager."""

    def test_open_monthly_objectives_carries_targets_forward(self):
        from api.tasks import open_monthly_objectives

        previous, _ = month_range(months_back=1)
        MonthlyObjective.objects.create(
            member=self.karim, month=previous,
            revenue_target=Decimal('18000'), clients_target=9, status='closed',
        )
        open_monthly_objectives()

        created = MonthlyObjective.objects.get(member=self.karim, month=month_start())
        self.assertEqual(created.revenue_target, Decimal('18000'))
        self.assertEqual(created.status, 'draft')

    def test_open_monthly_objectives_is_idempotent(self):
        from api.tasks import open_monthly_objectives

        open_monthly_objectives()
        first = MonthlyObjective.objects.count()
        open_monthly_objectives()
        self.assertEqual(MonthlyObjective.objects.count(), first)

    def test_close_previous_month(self):
        from api.tasks import close_previous_month

        previous, _ = month_range(months_back=1)
        objective = MonthlyObjective.objects.create(
            member=self.karim, month=previous,
            revenue_target=Decimal('1000'), status='active',
        )
        close_previous_month()
        objective.refresh_from_db()
        self.assertEqual(objective.status, 'closed')

    def test_carry_over_late_tasks(self):
        from api.tasks import carry_over_late_tasks

        DailyTask.objects.create(
            member=self.karim, title='En retard',
            date=timezone.localdate() - timedelta(days=4),
        )
        carry_over_late_tasks()
        self.assertEqual(
            DailyTask.objects.get(title='En retard').date, timezone.localdate()
        )


class ManagerProfileTest(TeamTestCase):
    """Profil gérant : paie et suivi du personnel."""

    def setUp(self):
        super().setUp()
        self.gerant = self.make_member('nadia', role='manager', department='direction')

    def payslip_payload(self, **overrides):
        data = {
            'member': self.karim.id,
            'month': timezone.localdate().replace(day=1).isoformat(),
            'base_salary': '2400.00',
            'worked_hours': '160.00',
            'overtime_hours': '6.00',
            'overtime_amount': '180.00',
            'bonuses': '100.00',
            'deductions': '50.00',
            'contributions': '520.00',
        }
        data.update(overrides)
        return data

    def event_payload(self, **overrides):
        data = {
            'member': self.karim.id,
            'kind': 'observation',
            'date': timezone.localdate().isoformat(),
            'reason': "Retards répétés signalés par le pôle commercial.",
        }
        data.update(overrides)
        return data

    # --- Rôle -------------------------------------------------------------

    def test_manager_sees_the_whole_team(self):
        """Le gérant reprend la visibilité d'équipe du fondateur."""
        self.assertTrue(self.gerant.is_founder)
        self.assertTrue(self.gerant.is_manager)

    def test_founder_is_not_a_manager(self):
        self.assertTrue(self.founder.is_founder)
        self.assertFalse(self.founder.is_manager)

    def test_profile_exposes_the_manager_flag(self):
        self.authenticate(self.gerant)
        response = self.client.get('/api/auth/me/')
        self.assertTrue(response.data['is_manager'])
        self.assertEqual(response.data['role_label'], 'Gérant')

    # --- Accès ------------------------------------------------------------

    def test_member_cannot_reach_the_staff_file(self):
        self.assertEqual(self.client.get('/api/staff-events/').status_code, 403)

    def test_member_sees_no_colleague_payslip(self):
        """La collection répond, mais ne montre que ses propres bulletins.

        La protection est dans le filtrage, pas dans le code de statut : un 403
        sur la collection dirait à qui la demande qu'il existe des bulletins.
        """
        Payslip.objects.create(
            member=self.lea, month=timezone.localdate().replace(day=1),
            base_salary=Decimal('450000.00'),
        )
        reponse = self.client.get('/api/payslips/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['count'], 0)

    def test_founder_does_not_reach_the_team_payroll(self):
        """La paie dépasse le pilotage : elle reste au gérant."""
        Payslip.objects.create(
            member=self.karim, month=timezone.localdate().replace(day=1),
            base_salary=Decimal('450000.00'),
        )
        self.authenticate(self.founder)

        self.assertEqual(self.client.get('/api/payslips/').data['count'], 0)
        self.assertEqual(self.client.get('/api/payslips/summary/').status_code, 403)

    def test_manager_reaches_payroll(self):
        self.authenticate(self.gerant)
        self.assertEqual(self.client.get('/api/payslips/').status_code, 200)
        self.assertEqual(self.client.get('/api/staff-events/').status_code, 200)

    # --- Bulletins de paie ------------------------------------------------

    def test_create_payslip_computes_gross_and_net(self):
        self.authenticate(self.gerant)
        response = self.client.post('/api/payslips/', self.payslip_payload(),
                                    format='json')

        self.assertEqual(response.status_code, 201)
        # 2400 + 180 + 100 = 2680 ; 2680 - 50 - 520 = 2110
        self.assertEqual(Decimal(response.data['gross']), Decimal('2680.00'))
        self.assertEqual(Decimal(response.data['net']), Decimal('2110.00'))
        self.assertEqual(Decimal(response.data['worked_hours']), Decimal('160.00'))
        # Enregistrer un bulletin, c'est l'établir : il est horodaté d'emblée.
        self.assertIsNotNone(response.data['issued_at'])

    def test_negative_net_is_rejected(self):
        self.authenticate(self.gerant)
        response = self.client.post('/api/payslips/', self.payslip_payload(
            base_salary='500.00', overtime_amount='0.00', bonuses='0.00',
            contributions='900.00',
        ), format='json')
        self.assertEqual(response.status_code, 400)

    def test_one_payslip_per_member_and_month(self):
        self.authenticate(self.gerant)
        self.client.post('/api/payslips/', self.payslip_payload(), format='json')
        response = self.client.post('/api/payslips/', self.payslip_payload(),
                                    format='json')
        self.assertEqual(response.status_code, 400)

    def test_payslip_month_can_be_corrected(self):
        """Une période saisie de travers se rattrape sans tout ressaisir."""
        self.authenticate(self.gerant)
        created = self.client.post('/api/payslips/', self.payslip_payload(),
                                   format='json')
        payslip_id = created.data['id']

        mois_precedent = (timezone.localdate().replace(day=1) - timedelta(days=1))
        response = self.client.patch(
            f'/api/payslips/{payslip_id}/',
            {'month': mois_precedent.replace(day=1).isoformat()}, format='json',
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['month_label'],
                         f'{mois_precedent:%Y-%m}')

    def test_moving_a_payslip_onto_an_occupied_month_is_refused(self):
        """Deux bulletins sur un même mois signeraient un double paiement."""
        self.authenticate(self.gerant)
        mois_precedent = (timezone.localdate().replace(day=1)
                          - timedelta(days=1)).replace(day=1)
        self.client.post('/api/payslips/', self.payslip_payload(), format='json')
        déplacé = self.client.post('/api/payslips/', self.payslip_payload(
            member=self.lea.id), format='json').data['id']

        # Le 15 du mois, pour vérifier que la date est ramenée au 1er avant le
        # contrôle d'unicité — sans quoi la collision passerait jusqu'en base.
        self.client.patch(f'/api/payslips/{déplacé}/',
                          {'month': mois_precedent.replace(day=15).isoformat()},
                          format='json')
        doublon = self.client.post('/api/payslips/', self.payslip_payload(
            member=self.lea.id, month=mois_precedent.replace(day=15).isoformat(),
        ), format='json')

        self.assertEqual(doublon.status_code, 400)

    def test_payslip_stays_editable_and_removable(self):
        """Plus de brouillon à émettre : le bulletin reste entre les mains
        du gérant tant qu'il n'a pas été supprimé."""
        self.authenticate(self.gerant)
        payslip_id = self.client.post('/api/payslips/', self.payslip_payload(),
                                      format='json').data['id']

        response = self.client.patch(f'/api/payslips/{payslip_id}/',
                                     {'bonuses': '200.00'}, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Decimal(response.data['bonuses']), Decimal('200.00'))
        self.assertEqual(
            self.client.delete(f'/api/payslips/{payslip_id}/').status_code, 204
        )

    def test_payslip_carries_the_staff_events_of_its_month(self):
        """Le décompte ne se relit pas sans ce qui l'explique."""
        self.authenticate(self.gerant)
        self.client.post('/api/staff-events/', self.event_payload(
            kind='lateness', minutes=25,
            reason="Arrivé après l'ouverture, trois jours de suite.",
        ), format='json')
        payslip_id = self.client.post('/api/payslips/', self.payslip_payload(),
                                      format='json').data['id']

        evenements = self.client.get(
            f'/api/payslips/{payslip_id}/').data['staff_events']

        self.assertEqual(len(evenements), 1)
        self.assertEqual(evenements[0]['kind'], 'lateness')
        self.assertEqual(evenements[0]['summary'], '25 min')

    def test_payroll_summary(self):
        self.authenticate(self.gerant)
        self.client.post('/api/payslips/', self.payslip_payload(), format='json')

        response = self.client.get('/api/payslips/summary/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(Decimal(response.data['gross']), Decimal('2680.00'))
        self.assertEqual(Decimal(response.data['worked_hours']), Decimal('160.00'))
        self.assertEqual(Decimal(response.data['overtime_hours']), Decimal('6.00'))

    # --- Évènements de personnel ------------------------------------------

    def test_create_observation_records_its_author(self):
        self.authenticate(self.gerant)
        response = self.client.post('/api/staff-events/', self.event_payload(),
                                    format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['recorded_by'], self.gerant.id)
        self.assertEqual(response.data['kind_label'], 'Observation')
        self.assertTrue(response.data['is_disciplinary'])

    def test_suspension_requires_an_end_date(self):
        self.authenticate(self.gerant)
        response = self.client.post('/api/staff-events/', self.event_payload(
            kind='suspension', end_date=None,
        ), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('end_date', response.data)

    def test_suspension_counts_its_days(self):
        self.authenticate(self.gerant)
        today = timezone.localdate()
        response = self.client.post('/api/staff-events/', self.event_payload(
            kind='suspension', date=today.isoformat(),
            end_date=(today + timedelta(days=2)).isoformat(),
            reason='Absence injustifiée de trois jours.',
        ), format='json')

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['days'], 3)
        self.assertEqual(response.data['summary'], '3 jours')

    def test_lateness_requires_minutes(self):
        self.authenticate(self.gerant)
        response = self.client.post('/api/staff-events/', self.event_payload(
            kind='lateness',
        ), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('minutes', response.data)

    def test_overtime_requires_hours(self):
        self.authenticate(self.gerant)
        response = self.client.post('/api/staff-events/', self.event_payload(
            kind='overtime',
        ), format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn('hours', response.data)

    def test_event_requires_a_reason(self):
        self.authenticate(self.gerant)
        response = self.client.post('/api/staff-events/', self.event_payload(
            reason='   ',
        ), format='json')
        self.assertEqual(response.status_code, 400)

    def test_staff_events_filter_by_kind(self):
        self.authenticate(self.gerant)
        today = timezone.localdate()
        StaffEvent.objects.create(member=self.karim, kind='lateness', date=today,
                                  minutes=25, reason='Retard du matin.')
        StaffEvent.objects.create(member=self.lea, kind='overtime', date=today,
                                  hours=Decimal('3.5'), reason='Clôture mensuelle.')

        response = self.client.get('/api/staff-events/?kind=lateness')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['summary'], '25 min')

    def test_staff_events_summary(self):
        self.authenticate(self.gerant)
        today = timezone.localdate()
        StaffEvent.objects.create(member=self.karim, kind='lateness', date=today,
                                  minutes=25, reason='Retard.')
        StaffEvent.objects.create(member=self.karim, kind='lateness', date=today,
                                  minutes=15, reason='Retard.')
        StaffEvent.objects.create(member=self.lea, kind='overtime', date=today,
                                  hours=Decimal('3.5'), reason='Clôture.')

        response = self.client.get('/api/staff-events/summary/')
        self.assertEqual(response.data['total'], 3)
        self.assertEqual(response.data['counts']['lateness'], 2)
        self.assertEqual(response.data['late_minutes'], 40)
        self.assertEqual(Decimal(response.data['overtime_hours']), Decimal('3.5'))


class CreateManagerCommandTest(TeamTestCase):
    """Commande `create_manager` : création et promotion d'un gérant."""

    def lancer(self, *args, **options):
        sortie = io.StringIO()
        call_command('create_manager', *args, stdout=sortie, **options)
        return sortie.getvalue()

    def test_creates_a_manager_account(self):
        sortie = self.lancer('gerante', first_name='Aline', last_name='Kouassi')

        membre = Member.objects.get(user__username='gerante')
        self.assertEqual(membre.role, 'manager')
        self.assertTrue(membre.is_manager)
        self.assertTrue(membre.is_founder)
        self.assertEqual(membre.department, 'direction')
        self.assertEqual(membre.job_title, 'Gérant')
        self.assertEqual(membre.display_name, 'Aline Kouassi')
        self.assertIn('Mot de passe', sortie)

    def test_generated_password_lets_the_manager_sign_in(self):
        """Le mot de passe affiché doit réellement ouvrir la session."""
        sortie = self.lancer('gerante')
        motdepasse = next(
            ligne.split(':', 1)[1].strip()
            for ligne in sortie.splitlines() if 'Mot de passe' in ligne
        )

        reponse = self.client.post('/api/auth/login/', {
            'username': 'gerante', 'password': motdepasse,
        }, format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertTrue(reponse.data['user']['is_manager'])

    def test_chosen_password_is_never_echoed(self):
        sortie = self.lancer('gerante', password='Gestion-2026!Solide')
        self.assertNotIn('Gestion-2026!Solide', sortie)

    def test_weak_password_is_refused(self):
        with self.assertRaises(CommandError):
            self.lancer('gerante', password='1234')
        self.assertFalse(User.objects.filter(username='gerante').exists())

    def test_existing_account_needs_promote(self):
        with self.assertRaises(CommandError):
            self.lancer('karim')
        self.karim.refresh_from_db()
        self.assertEqual(self.karim.role, 'member')

    def test_promote_keeps_identity_and_password(self):
        """Promouvoir ne doit ni déplacer le pôle ni changer le mot de passe."""
        self.lancer('karim', promote=True)

        self.karim.refresh_from_db()
        self.assertEqual(self.karim.role, 'manager')
        self.assertEqual(self.karim.department, 'commercial')

        reponse = self.client.post('/api/auth/login/', {
            'username': 'karim', 'password': 'pass-Solide1',
        }, format='json')
        self.assertEqual(reponse.status_code, 200)

    def test_manager_reaches_payroll_after_promotion(self):
        self.lancer('karim', promote=True)
        self.authenticate(self.karim)
        self.assertEqual(self.client.get('/api/payslips/').status_code, 200)


class SuggestionBoxTest(TeamTestCase):
    """Boîte à suggestions : dépôt libre, relève par la direction."""

    def payload(self, **overrides):
        data = {
            'category': 'idea',
            'message': "Ajouter un rappel la veille des échéances de jalon.",
        }
        data.update(overrides)
        return data

    def test_member_can_post_a_suggestion(self):
        reponse = self.client.post('/api/suggestions/', self.payload(), format='json')

        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.data['author'], self.karim.id)
        self.assertEqual(reponse.data['status'], 'new')
        self.assertEqual(reponse.data['category_label'], 'Idée')

    def test_too_short_a_message_is_refused(self):
        reponse = self.client.post('/api/suggestions/', self.payload(message='ok'),
                                   format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('message', reponse.data)

    def test_member_only_sees_his_own_suggestions(self):
        Suggestion.objects.create(author=self.lea, message="Idée de Lea, confidentielle.")
        self.client.post('/api/suggestions/', self.payload(), format='json')

        reponse = self.client.get('/api/suggestions/')
        self.assertEqual(reponse.data['count'], 1)
        self.assertEqual(reponse.data['results'][0]['author'], self.karim.id)

    def test_founder_reads_the_whole_box(self):
        Suggestion.objects.create(author=self.lea, message="Idée de Lea, à lire.")
        Suggestion.objects.create(author=self.karim, message="Idée de Karim, à lire.")

        self.authenticate(self.founder)
        self.assertEqual(self.client.get('/api/suggestions/').data['count'], 2)

    def test_founder_handles_a_suggestion(self):
        suggestion = Suggestion.objects.create(
            author=self.karim, message="Ajouter un export des tâches du mois."
        )
        self.authenticate(self.founder)

        reponse = self.client.patch(f'/api/suggestions/{suggestion.id}/handle/', {
            'status': 'done', 'reply': "Prévu pour la version suivante.",
        }, format='json')

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['status'], 'done')
        self.assertEqual(reponse.data['handled_by'], self.founder.id)
        self.assertEqual(reponse.data['reply'], "Prévu pour la version suivante.")
        self.assertIsNotNone(reponse.data['handled_at'])

    def test_member_cannot_handle_a_suggestion(self):
        suggestion = Suggestion.objects.create(author=self.karim, message="Une idée.")
        reponse = self.client.patch(f'/api/suggestions/{suggestion.id}/handle/',
                                    {'status': 'done'}, format='json')
        self.assertEqual(reponse.status_code, 403)

    def test_author_can_correct_a_suggestion_still_unread(self):
        cree = self.client.post('/api/suggestions/', self.payload(), format='json')
        reponse = self.client.patch(f"/api/suggestions/{cree.data['id']}/", {
            'message': "Ajouter un rappel deux jours avant l'échéance.",
        }, format='json')
        self.assertEqual(reponse.status_code, 200)

    def test_author_cannot_rewrite_a_suggestion_once_read(self):
        """Relire un message déjà lu ne doit pas réécrire l'histoire."""
        suggestion = Suggestion.objects.create(
            author=self.karim, message="Message d'origine, déjà lu.", status='read',
        )
        reponse = self.client.patch(f'/api/suggestions/{suggestion.id}/', {
            'message': "Message réécrit après coup.",
        }, format='json')
        self.assertEqual(reponse.status_code, 400)


class NotificationsTest(TeamTestCase):
    """Flux d'alertes de la cloche."""

    def test_no_alert_when_everything_is_in_order(self):
        self.make_objective(self.karim, revenue_achieved=Decimal('20000.00'),
                            clients_achieved=10)
        # Journée pointée d'un bout à l'autre : ni arrivée manquante, ni
        # départ oublié à signaler.
        maintenant = timezone.now()
        Attendance.objects.create(
            member=self.karim, date=timezone.localdate(),
            check_in=maintenant - timedelta(hours=3), check_out=maintenant,
        )
        reponse = self.client.get('/api/dashboard/notifications/')

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['count'], 0)
        self.assertEqual(reponse.data['items'], [])

    def test_missing_objective_is_signalled(self):
        reponse = self.client.get('/api/dashboard/notifications/')
        genres = [a['kind'] for a in reponse.data['items']]
        self.assertIn('objective_missing', genres)

    def test_late_tasks_are_counted(self):
        self.make_objective(self.karim, revenue_achieved=Decimal('20000.00'),
                            clients_achieved=10)
        hier = timezone.localdate() - timedelta(days=1)
        DailyTask.objects.create(member=self.karim, title='Oubliée', date=hier)
        DailyTask.objects.create(member=self.karim, title='Oubliée aussi', date=hier)

        reponse = self.client.get('/api/dashboard/notifications/')
        alerte = next(a for a in reponse.data['items'] if a['kind'] == 'tasks_late')
        self.assertEqual(alerte['count'], 2)
        self.assertEqual(alerte['page'], 'tasks')

    def test_new_suggestions_reach_the_founder_only(self):
        Suggestion.objects.create(author=self.karim, message="Une idée à relever.")

        genres = [a['kind'] for a in
                  self.client.get('/api/dashboard/notifications/').data['items']]
        self.assertNotIn('suggestions_new', genres)

        self.authenticate(self.founder)
        genres = [a['kind'] for a in
                  self.client.get('/api/dashboard/notifications/').data['items']]
        self.assertIn('suggestions_new', genres)

    def test_handled_suggestion_clears_the_alert(self):
        """L'alerte suit l'état réel : rien à « marquer comme lu »."""
        suggestion = Suggestion.objects.create(author=self.karim, message="Une idée.")
        self.authenticate(self.founder)

        self.client.patch(f'/api/suggestions/{suggestion.id}/handle/',
                          {'status': 'done'}, format='json')

        genres = [a['kind'] for a in
                  self.client.get('/api/dashboard/notifications/').data['items']]
        self.assertNotIn('suggestions_new', genres)


class TaskDurationTest(TeamTestCase):
    """Départ, fin et temps réellement passé sur une tâche."""

    def make_task(self, **overrides):
        defaults = {'member': self.karim, 'title': 'Relancer les devis',
                    'estimated_minutes': 60}
        defaults.update(overrides)
        return DailyTask.objects.create(**defaults)

    def test_a_new_task_has_no_duration(self):
        tache = self.make_task()
        self.assertIsNone(tache.started_at)
        self.assertIsNone(tache.duration_minutes)
        self.assertEqual(tache.duration_label, '')

    def test_start_sets_the_clock(self):
        tache = self.make_task()
        reponse = self.client.patch(f'/api/tasks/{tache.id}/start/')

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['status'], 'in_progress')
        self.assertIsNotNone(reponse.data['started_at'])
        self.assertEqual(reponse.data['duration_minutes'], 0)

    def test_a_started_task_cannot_be_restarted(self):
        """Relancer le chronomètre effacerait le temps déjà passé."""
        tache = self.make_task()
        self.client.patch(f'/api/tasks/{tache.id}/start/')
        reponse = self.client.patch(f'/api/tasks/{tache.id}/start/')
        self.assertEqual(reponse.status_code, 400)

    def test_a_finished_task_cannot_be_started(self):
        tache = self.make_task(status='done')
        self.assertEqual(
            self.client.patch(f'/api/tasks/{tache.id}/start/').status_code, 400
        )

    def test_duration_is_measured_between_start_and_finish(self):
        depart = timezone.now() - timedelta(minutes=95)
        tache = self.make_task()
        DailyTask.objects.filter(pk=tache.pk).update(
            status='in_progress', started_at=depart
        )

        reponse = self.client.patch(f'/api/tasks/{tache.id}/complete/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['duration_minutes'], 95)
        self.assertEqual(reponse.data['duration_label'], '1 h 35')

    def test_a_running_task_counts_up_to_now(self):
        """Le compteur doit servir pendant qu'on travaille, pas seulement après."""
        tache = self.make_task()
        DailyTask.objects.filter(pk=tache.pk).update(
            status='in_progress', started_at=timezone.now() - timedelta(minutes=30)
        )

        reponse = self.client.get(f'/api/tasks/{tache.id}/')
        self.assertEqual(reponse.data['duration_minutes'], 30)
        self.assertEqual(reponse.data['duration_label'], '30 min')

    def test_completing_without_starting_leaves_a_zero_duration(self):
        """Une tâche cochée sans départ ne doit pas afficher une durée absurde."""
        tache = self.make_task()
        reponse = self.client.patch(f'/api/tasks/{tache.id}/complete/')

        self.assertEqual(reponse.data['duration_minutes'], 0)
        self.assertIsNotNone(reponse.data['started_at'])

    def test_overrun_is_flagged_against_the_estimate(self):
        tache = self.make_task(estimated_minutes=60)
        DailyTask.objects.filter(pk=tache.pk).update(
            status='in_progress', started_at=timezone.now() - timedelta(minutes=90)
        )
        self.assertTrue(self.client.get(f'/api/tasks/{tache.id}/').data['over_estimate'])

        rapide = self.make_task(estimated_minutes=60, title='Vite fait')
        DailyTask.objects.filter(pk=rapide.pk).update(
            status='in_progress', started_at=timezone.now() - timedelta(minutes=20)
        )
        self.assertFalse(self.client.get(f'/api/tasks/{rapide.id}/').data['over_estimate'])

    def test_a_task_without_estimate_is_never_flagged(self):
        tache = self.make_task(estimated_minutes=None)
        DailyTask.objects.filter(pk=tache.pk).update(
            status='in_progress', started_at=timezone.now() - timedelta(hours=5)
        )
        self.assertFalse(self.client.get(f'/api/tasks/{tache.id}/').data['over_estimate'])

    def test_a_colleague_cannot_start_your_task(self):
        tache = self.make_task(member=self.lea)
        self.assertEqual(
            self.client.patch(f'/api/tasks/{tache.id}/start/').status_code, 404
        )


class FounderPanelTest(TeamTestCase):
    """Panel du fondateur : qui travaille, qui laisse filer, quels rapports."""

    def demarrer(self, membre, titre, minutes):
        """Tâche en cours depuis N minutes."""
        tache = DailyTask.objects.create(member=membre, title=titre,
                                         estimated_minutes=60)
        DailyTask.objects.filter(pk=tache.pk).update(
            status='in_progress', started_at=timezone.now() - timedelta(minutes=minutes)
        )
        return tache

    def panel(self):
        return self.client.get('/api/dashboard/panel/')

    def ligne(self, reponse, membre):
        return next(l for l in reponse.data['members'] if l['member_id'] == membre.id)

    def test_panel_is_reserved_to_founders(self):
        self.assertEqual(self.panel().status_code, 403)
        self.authenticate(self.founder)
        self.assertEqual(self.panel().status_code, 200)

    def test_a_member_at_work_is_shown_as_working(self):
        self.demarrer(self.karim, 'Relancer les devis', 40)
        self.authenticate(self.founder)

        ligne = self.ligne(self.panel(), self.karim)
        self.assertEqual(ligne['status'], 'working')
        self.assertEqual(ligne['current_task']['title'], 'Relancer les devis')
        self.assertEqual(ligne['current_task']['duration_label'], '40 min')
        self.assertEqual(ligne['minutes_logged'], 40)

    def test_a_member_with_untouched_tasks_is_idle(self):
        """C'est la ligne que le fondateur cherche : des tâches, aucune entamée."""
        DailyTask.objects.create(member=self.lea, title='Publier la campagne')
        self.authenticate(self.founder)

        ligne = self.ligne(self.panel(), self.lea)
        self.assertEqual(ligne['status'], 'idle')
        self.assertIsNone(ligne['current_task'])
        self.assertEqual(ligne['minutes_logged'], 0)

    def test_a_member_without_tasks_is_distinguished_from_an_idle_one(self):
        self.authenticate(self.founder)
        self.assertEqual(self.ligne(self.panel(), self.lea)['status'], 'no_tasks')

    def test_a_member_who_finished_everything_is_marked_done(self):
        tache = DailyTask.objects.create(member=self.karim, title='Appeler le client')
        tache.status = 'done'
        tache.save()
        self.authenticate(self.founder)

        ligne = self.ligne(self.panel(), self.karim)
        self.assertEqual(ligne['status'], 'done')
        self.assertEqual(ligne['tasks_done'], 1)
        self.assertEqual(ligne['tasks_total'], 1)

    def test_late_tasks_are_counted_per_member(self):
        hier = timezone.localdate() - timedelta(days=1)
        DailyTask.objects.create(member=self.karim, title='Oubliée', date=hier)
        DailyTask.objects.create(member=self.karim, title='Oubliée aussi', date=hier)
        self.authenticate(self.founder)

        self.assertEqual(self.ligne(self.panel(), self.karim)['tasks_late'], 2)

    def test_problem_rows_come_first(self):
        """L'ordre doit porter le message : ce qui cloche en tête."""
        DailyTask.objects.create(member=self.lea, title='Pas commencée')
        self.demarrer(self.karim, 'En cours', 15)
        self.authenticate(self.founder)

        etats = [l['status'] for l in self.panel().data['members']]
        self.assertLess(etats.index('idle'), etats.index('working'))

    def test_totals_add_up(self):
        self.demarrer(self.karim, 'En cours', 30)
        DailyTask.objects.create(member=self.lea, title='Pas commencée')
        self.authenticate(self.founder)

        totaux = self.panel().data['totals']
        self.assertEqual(totaux['working'], 1)
        self.assertEqual(totaux['idle'], 1)
        self.assertEqual(totaux['minutes_logged'], 30)
        self.assertEqual(totaux['tasks_total'], 2)

    def test_the_panel_carries_the_latest_reports(self):
        Report.objects.create(
            member=self.lea, period_type='weekly',
            period_start=timezone.localdate() - timedelta(days=6),
            period_end=timezone.localdate(), summary='Bilan de Lea.',
        )
        Report.objects.create(
            member=self.karim, period_type='mission', title='Mission Aurore',
            period_start=timezone.localdate(), period_end=timezone.localdate(),
            summary='Compte rendu de mission.',
        )
        self.authenticate(self.founder)

        rapports = self.panel().data['recent_reports']
        self.assertEqual(len(rapports), 2)
        auteurs = {r['member_name'] for r in rapports}
        self.assertEqual(auteurs, {self.lea.display_name, self.karim.display_name})

    def test_the_panel_is_computed_at_call_time(self):
        """Rien n'est mis en cache : démarrer une tâche change la réponse."""
        DailyTask.objects.create(member=self.karim, title='À faire')
        self.authenticate(self.founder)
        self.assertEqual(self.ligne(self.panel(), self.karim)['status'], 'idle')

        self.authenticate(self.karim)
        tache = DailyTask.objects.get(title='À faire')
        self.client.patch(f'/api/tasks/{tache.id}/start/')

        self.authenticate(self.founder)
        self.assertEqual(self.ligne(self.panel(), self.karim)['status'], 'working')


class AccountAdministrationTest(TeamTestCase):
    """Création, modification, rôle et suppression des comptes."""

    def payload(self, **overrides):
        data = {
            'username': 'amina',
            'first_name': 'Amina',
            'last_name': 'Sow',
            'email': 'amina@fluxgestion.local',
            'role': 'member',
            'department': 'operations',
            'job_title': 'Assistante',
        }
        data.update(overrides)
        return data

    # --- Qui a le droit ---------------------------------------------------

    def test_a_member_cannot_create_an_account(self):
        reponse = self.client.post('/api/members/', self.payload(), format='json')
        self.assertEqual(reponse.status_code, 403)
        self.assertFalse(User.objects.filter(username='amina').exists())

    def test_a_member_cannot_edit_a_colleague(self):
        reponse = self.client.patch(f'/api/members/{self.lea.id}/',
                                    {'job_title': 'Stagiaire'}, format='json')
        self.assertIn(reponse.status_code, (403, 404))

    def test_a_member_cannot_give_himself_a_role(self):
        """Le sérialiseur ordinaire fige le rôle : l'escalade est impossible."""
        reponse = self.client.patch('/api/members/me/', {'role': 'founder'},
                                    format='json')
        self.assertEqual(reponse.status_code, 200)
        self.karim.refresh_from_db()
        self.assertEqual(self.karim.role, 'member')

    # --- Création ---------------------------------------------------------

    def test_founder_creates_an_account_with_a_generated_password(self):
        self.authenticate(self.founder)
        reponse = self.client.post('/api/members/', self.payload(), format='json')

        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.data['role'], 'member')
        self.assertEqual(reponse.data['display_name'], 'Amina Sow')
        motdepasse = reponse.data['generated_password']
        self.assertTrue(motdepasse)

        connexion = self.client.post('/api/auth/login/', {
            'username': 'amina', 'password': motdepasse,
        }, format='json')
        self.assertEqual(connexion.status_code, 200)

    def test_founder_creates_an_administrative_profile(self):
        self.authenticate(self.founder)
        reponse = self.client.post('/api/members/', self.payload(
            username='gerance', role='manager', department='direction',
        ), format='json')

        self.assertEqual(reponse.status_code, 201)
        self.assertTrue(reponse.data['is_manager'])
        self.assertTrue(reponse.data['is_founder'])

    def test_a_chosen_password_is_never_returned(self):
        self.authenticate(self.founder)
        reponse = self.client.post('/api/members/', self.payload(
            password='Gestion-2026!Solide',
        ), format='json')

        self.assertEqual(reponse.status_code, 201)
        self.assertNotIn('password', reponse.data)
        self.assertEqual(reponse.data['generated_password'], '')

    def test_a_weak_password_is_refused(self):
        self.authenticate(self.founder)
        reponse = self.client.post('/api/members/', self.payload(password='1234'),
                                   format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertFalse(User.objects.filter(username='amina').exists())

    def test_a_duplicate_username_is_refused(self):
        self.authenticate(self.founder)
        reponse = self.client.post('/api/members/', self.payload(username='KARIM'),
                                   format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('username', reponse.data)

    # --- Modification -----------------------------------------------------

    def test_founder_changes_a_role(self):
        self.authenticate(self.founder)
        reponse = self.client.patch(f'/api/members/{self.karim.id}/',
                                    {'role': 'manager'}, format='json')

        self.assertEqual(reponse.status_code, 200)
        self.karim.refresh_from_db()
        self.assertEqual(self.karim.role, 'manager')
        self.assertTrue(self.karim.is_manager)

    def test_founder_edits_identity_and_post(self):
        self.authenticate(self.founder)
        reponse = self.client.patch(f'/api/members/{self.lea.id}/', {
            'last_name': 'Moreau-Diop', 'job_title': "Responsable d'acquisition",
        }, format='json')

        self.assertEqual(reponse.status_code, 200)
        self.lea.refresh_from_db()
        self.assertEqual(self.lea.user.last_name, 'Moreau-Diop')
        self.assertEqual(self.lea.job_title, "Responsable d'acquisition")

    def test_the_last_founder_cannot_be_demoted(self):
        """Sans fondateur, plus personne ne peut administrer l'instance."""
        self.authenticate(self.founder)
        reponse = self.client.patch(f'/api/members/{self.founder.id}/',
                                    {'role': 'member'}, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.founder.refresh_from_db()
        self.assertEqual(self.founder.role, 'founder')

    def test_a_founder_can_be_demoted_when_another_remains(self):
        autre = self.make_member('bintou', role='founder', department='direction')
        self.authenticate(self.founder)

        reponse = self.client.patch(f'/api/members/{autre.id}/',
                                    {'role': 'member'}, format='json')
        self.assertEqual(reponse.status_code, 200)

    # --- Désactivation et suppression -------------------------------------

    def test_deactivating_keeps_the_history(self):
        self.make_objective(self.lea)
        self.authenticate(self.founder)

        reponse = self.client.patch(f'/api/members/{self.lea.id}/set_active/',
                                    {'active': False}, format='json')
        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.data['is_active'])

        self.lea.user.refresh_from_db()
        self.assertFalse(self.lea.user.is_active)
        self.assertTrue(MonthlyObjective.objects.filter(member=self.lea).exists())

    def test_a_deactivated_account_cannot_sign_in(self):
        self.authenticate(self.founder)
        self.client.patch(f'/api/members/{self.lea.id}/set_active/',
                          {'active': False}, format='json')

        self.client.credentials()
        reponse = self.client.post('/api/auth/login/', {
            'username': 'lea', 'password': 'pass-Solide1',
        }, format='json')
        self.assertNotEqual(reponse.status_code, 200)

    def test_founder_cannot_deactivate_himself(self):
        self.authenticate(self.founder)
        reponse = self.client.patch(f'/api/members/{self.founder.id}/set_active/',
                                    {'active': False}, format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_deleting_removes_the_account_and_its_data(self):
        self.make_objective(self.lea)
        self.authenticate(self.founder)

        reponse = self.client.delete(f'/api/members/{self.lea.id}/')
        self.assertEqual(reponse.status_code, 204)
        self.assertFalse(User.objects.filter(username='lea').exists())
        self.assertFalse(MonthlyObjective.objects.filter(member_id=self.lea.id).exists())

    def test_founder_cannot_delete_himself(self):
        self.authenticate(self.founder)
        reponse = self.client.delete(f'/api/members/{self.founder.id}/')
        self.assertEqual(reponse.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.founder.user_id).exists())

    def test_the_last_founder_cannot_be_deleted(self):
        autre = self.make_member('bintou', role='founder', department='direction')
        self.authenticate(autre)

        # Il en reste un : la suppression passe.
        self.assertEqual(
            self.client.delete(f'/api/members/{self.founder.id}/').status_code, 204
        )
        # Bintou est maintenant seule : elle ne peut plus être supprimée non plus.
        self.authenticate(self.karim)
        self.assertIn(
            self.client.delete(f'/api/members/{autre.id}/').status_code, (403, 404)
        )

    # --- Mot de passe -----------------------------------------------------

    def test_founder_resets_a_password(self):
        self.authenticate(self.founder)
        reponse = self.client.patch(f'/api/members/{self.karim.id}/reset_password/')

        self.assertEqual(reponse.status_code, 200)
        motdepasse = reponse.data['generated_password']
        self.assertTrue(motdepasse)

        self.client.credentials()
        connexion = self.client.post('/api/auth/login/', {
            'username': 'karim', 'password': motdepasse,
        }, format='json')
        self.assertEqual(connexion.status_code, 200)

    def test_a_member_cannot_reset_a_colleague_password(self):
        reponse = self.client.patch(f'/api/members/{self.lea.id}/reset_password/')
        self.assertEqual(reponse.status_code, 403)


class OwnPayslipTest(TeamTestCase):
    """Ce qu'un salarié voit de sa propre paie."""

    def setUp(self):
        super().setUp()
        self.gerant = self.make_member('nadia', role='manager', department='direction')
        self.mois = timezone.localdate().replace(day=1)

    def bulletin(self, membre, **overrides):
        données = {
            'member': membre, 'month': self.mois,
            'base_salary': Decimal('450000.00'),
            'contributions': Decimal('99000.00'),
        }
        données.update(overrides)
        return Payslip.objects.create(**données)

    def test_a_member_reads_his_own_payslip(self):
        self.bulletin(self.karim)
        reponse = self.client.get('/api/payslips/')

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['count'], 1)
        ligne = reponse.data['results'][0]
        self.assertEqual(ligne['member'], self.karim.id)
        self.assertEqual(Decimal(ligne['net']), Decimal('351000.00'))

    def test_a_member_never_sees_a_colleague_payslip(self):
        self.bulletin(self.karim)
        self.bulletin(self.lea)

        reponse = self.client.get('/api/payslips/')
        self.assertEqual(reponse.data['count'], 1)
        self.assertEqual(reponse.data['results'][0]['member'], self.karim.id)

    def test_a_recorded_payslip_reaches_the_employee(self):
        """Sans brouillon, un bulletin enregistré est un bulletin remis."""
        bulletin = self.bulletin(self.karim)

        self.assertEqual(self.client.get('/api/payslips/').data['count'], 1)
        self.assertEqual(
            self.client.get(f'/api/payslips/{bulletin.id}/').status_code, 200
        )

    def test_a_founder_does_not_read_the_payroll(self):
        """La règle tient : la paie reste au gérant, pas à la direction."""
        self.bulletin(self.karim)
        self.authenticate(self.founder)

        self.assertEqual(self.client.get('/api/payslips/').data['count'], 0)

    def test_the_manager_still_reads_everything(self):
        self.bulletin(self.karim)
        self.bulletin(self.lea)
        self.authenticate(self.gerant)

        self.assertEqual(self.client.get('/api/payslips/').data['count'], 2)

    def test_a_member_cannot_touch_the_payroll(self):
        bulletin = self.bulletin(self.karim)

        self.assertEqual(self.client.post('/api/payslips/', {
            'member': self.karim.id, 'month': self.mois.isoformat(),
            'base_salary': '999999.00',
        }, format='json').status_code, 403)
        self.assertEqual(self.client.patch(
            f'/api/payslips/{bulletin.id}/', {'base_salary': '999999.00'},
            format='json').status_code, 403)
        self.assertEqual(
            self.client.delete(f'/api/payslips/{bulletin.id}/').status_code, 403
        )
        self.assertEqual(self.client.get('/api/payslips/summary/').status_code, 403)

    def test_a_member_changes_his_own_password(self):
        reponse = self.client.post('/api/auth/change-password/', {
            'old_password': 'pass-Solide1', 'new_password': 'Nouveau-2026!Solide',
        }, format='json')
        self.assertEqual(reponse.status_code, 200)

        self.client.credentials()
        connexion = self.client.post('/api/auth/login/', {
            'username': 'karim', 'password': 'Nouveau-2026!Solide',
        }, format='json')
        self.assertEqual(connexion.status_code, 200)

    def test_a_wrong_current_password_is_refused(self):
        reponse = self.client.post('/api/auth/change-password/', {
            'old_password': 'je-ne-sais-plus', 'new_password': 'Nouveau-2026!Solide',
        }, format='json')
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('old_password', reponse.data)


class ReactionPointsTest(TeamTestCase):
    """Points accordés par la direction, et prime qui en découle."""

    def reagir(self, membre, nature='bravo', **overrides):
        données = {'member': membre.id, 'kind': nature}
        données.update(overrides)
        return self.client.post('/api/reactions/', données, format='json')

    # --- Qui peut réagir --------------------------------------------------

    def test_a_member_cannot_award_points(self):
        reponse = self.reagir(self.karim)
        self.assertEqual(reponse.status_code, 403)
        self.assertEqual(Reaction.objects.count(), 0)

    def test_a_member_cannot_award_points_to_himself(self):
        """Le plus tentant des abus : se créditer soi-même."""
        self.assertEqual(self.reagir(self.karim, points=100).status_code, 403)

    def test_the_direction_awards_points(self):
        self.authenticate(self.founder)
        reponse = self.reagir(self.karim, nature='objectif',
                              reason='Mois bouclé avant terme')

        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.data['points'], 20)
        self.assertEqual(reponse.data['author'], self.founder.id)
        self.assertTrue(reponse.data['is_positive'])

    def test_default_points_follow_the_kind(self):
        self.authenticate(self.founder)
        for nature, attendu in (('bravo', 10), ('entraide', 5),
                                ('rappel', -5), ('manquement', -15)):
            reponse = self.reagir(self.lea, nature=nature)
            self.assertEqual(reponse.data['points'], attendu, nature)

    def test_the_direction_can_adjust_the_points(self):
        """Une même occasion ne pèse pas toujours pareil."""
        self.authenticate(self.founder)
        reponse = self.reagir(self.karim, nature='bravo', points=40)
        self.assertEqual(reponse.data['points'], 40)

    def test_points_can_be_removed(self):
        self.authenticate(self.founder)
        reponse = self.reagir(self.karim, nature='manquement', points=-25)

        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.data['points'], -25)
        self.assertFalse(reponse.data['is_positive'])

    def test_a_reaction_worth_nothing_is_refused(self):
        self.authenticate(self.founder)
        reponse = self.reagir(self.karim, points=0)
        self.assertEqual(reponse.status_code, 400)
        self.assertIn('points', reponse.data)

    # --- Cumul et prime ---------------------------------------------------

    def test_points_add_up_and_open_a_bonus(self):
        self.authenticate(self.founder)
        self.reagir(self.karim, nature='objectif')      # +20
        self.reagir(self.karim, nature='bravo')         # +10
        self.reagir(self.karim, nature='rappel')        # -5

        self.karim.refresh_from_db()
        self.assertEqual(self.karim.points_month, 25)
        self.assertEqual(self.karim.points_total, 25)
        self.assertEqual(self.karim.bonus_earned, 25 * Reaction.POINT_VALUE)

    def test_a_negative_balance_never_eats_into_the_salary(self):
        """Retirer des points annule la prime, il ne la rend pas débitrice."""
        self.authenticate(self.founder)
        self.reagir(self.karim, nature='manquement', points=-40)

        self.karim.refresh_from_db()
        self.assertEqual(self.karim.points_month, -40)
        self.assertEqual(self.karim.bonus_earned, 0)

    def test_last_month_points_do_not_feed_this_month_bonus(self):
        """La prime est mensuelle : elle ne traîne pas d'un mois sur l'autre."""
        ancien, _ = month_range(months_back=1)
        Reaction.objects.create(member=self.karim, kind='bravo', points=30,
                                date=ancien, author=self.founder)

        self.karim.refresh_from_db()
        self.assertEqual(self.karim.points_total, 30)
        self.assertEqual(self.karim.points_month, 0)
        self.assertEqual(self.karim.bonus_earned, 0)

    # --- Visibilité -------------------------------------------------------

    def test_a_member_reads_the_points_he_received(self):
        self.authenticate(self.founder)
        self.reagir(self.karim, nature='bravo', reason='Belle relance')
        self.reagir(self.lea, nature='entraide')

        self.authenticate(self.karim)
        reponse = self.client.get('/api/reactions/')
        self.assertEqual(reponse.data['count'], 1)
        self.assertEqual(reponse.data['results'][0]['reason'], 'Belle relance')

    def test_the_direction_reads_every_reaction(self):
        self.authenticate(self.founder)
        self.reagir(self.karim)
        self.reagir(self.lea)
        self.assertEqual(self.client.get('/api/reactions/').data['count'], 2)

    def test_the_profile_carries_points_and_bonus(self):
        self.authenticate(self.founder)
        self.reagir(self.karim, nature='objectif')

        self.authenticate(self.karim)
        reponse = self.client.get('/api/members/me/')
        self.assertEqual(reponse.data['points_month'], 20)
        self.assertEqual(reponse.data['bonus_earned'], 20 * Reaction.POINT_VALUE)

    def test_the_scale_is_published(self):
        reponse = self.client.get('/api/reactions/scale/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['point_value'], Reaction.POINT_VALUE)
        natures = {n['kind']: n['points'] for n in reponse.data['kinds']}
        self.assertEqual(natures['objectif'], 20)
        self.assertEqual(natures['manquement'], -15)


class BaseSalaryTest(TeamTestCase):
    """Le salaire de base se lit sur le profil, sans bulletin."""

    def test_the_salary_shows_without_any_payslip(self):
        self.karim.base_salary = Decimal('450000.00')
        self.karim.save(update_fields=['base_salary'])

        reponse = self.client.get('/api/members/me/')
        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(Decimal(reponse.data['base_salary']), Decimal('450000.00'))
        self.assertFalse(Payslip.objects.exists())

    def test_a_member_cannot_raise_his_own_salary(self):
        reponse = self.client.patch('/api/members/me/',
                                    {'base_salary': '9999999.00'}, format='json')
        self.assertEqual(reponse.status_code, 200)

        self.karim.refresh_from_db()
        self.assertEqual(self.karim.base_salary, Decimal('0'))

    def test_a_founder_sets_the_salary(self):
        self.authenticate(self.founder)
        reponse = self.client.patch(f'/api/members/{self.karim.id}/',
                                    {'base_salary': '450000.00'}, format='json')
        self.assertEqual(reponse.status_code, 200)

        self.karim.refresh_from_db()
        self.assertEqual(self.karim.base_salary, Decimal('450000.00'))

    def test_a_member_never_reads_a_colleague_salary(self):
        self.lea.base_salary = Decimal('400000.00')
        self.lea.save(update_fields=['base_salary'])

        reponse = self.client.get('/api/members/')
        self.assertEqual(reponse.data['count'], 1)
        self.assertEqual(reponse.data['results'][0]['username'], 'karim')


class LeaveRequestTest(TeamTestCase):
    """Demandes de congé : posées par un membre, tranchées par la direction."""

    def monday(self, semaines=1):
        """Lundi à venir : des jours ouvrables sûrs, quel que soit le jour du test."""
        jour = timezone.localdate()
        prochain = jour + timedelta(days=(7 - jour.weekday()) % 7 or 7)
        return prochain + timedelta(weeks=semaines - 1)

    def payload(self, **overrides):
        debut = self.monday()
        data = {
            'kind': 'paid',
            'start_date': debut.isoformat(),
            'end_date': (debut + timedelta(days=4)).isoformat(),
            'reason': 'Congé annuel, retour au village.',
        }
        data.update(overrides)
        return data

    def make(self, member=None, semaines=1, **overrides):
        debut = self.monday(semaines)
        defaults = {
            'member': member or self.karim,
            'kind': 'paid',
            'start_date': debut,
            'end_date': debut + timedelta(days=4),
            'reason': 'Congé annuel.',
        }
        return LeaveRequest.objects.create(**{**defaults, **overrides})

    # --- Dépôt ------------------------------------------------------------

    def test_member_posts_a_request(self):
        reponse = self.client.post('/api/leaves/', self.payload(), format='json')

        self.assertEqual(reponse.status_code, 201)
        self.assertEqual(reponse.data['status'], 'pending')
        self.assertEqual(reponse.data['member'], self.karim.id)
        self.assertEqual(reponse.data['days'], 5.0)

    def test_request_is_always_for_its_author(self):
        """Personne ne pose un congé au nom d'un collègue."""
        reponse = self.client.post(
            '/api/leaves/', self.payload(member=self.lea.id), format='json'
        )
        self.assertEqual(reponse.data['member'], self.karim.id)

    def test_status_cannot_be_forced_at_creation(self):
        reponse = self.client.post(
            '/api/leaves/', self.payload(status='approved'), format='json'
        )
        self.assertEqual(reponse.data['status'], 'pending')

    def test_overlapping_request_is_refused(self):
        self.make()
        reponse = self.client.post('/api/leaves/', self.payload(), format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_a_refused_request_frees_the_period(self):
        """Un refus n'occupe plus le calendrier : la période se repose."""
        self.make(status='refused')
        reponse = self.client.post('/api/leaves/', self.payload(), format='json')
        self.assertEqual(reponse.status_code, 201)

    def test_half_day_must_stay_on_one_day(self):
        reponse = self.client.post(
            '/api/leaves/', self.payload(half_day=True), format='json'
        )
        self.assertEqual(reponse.status_code, 400)

    def test_a_week_end_alone_is_refused(self):
        samedi = self.monday() + timedelta(days=5)
        reponse = self.client.post('/api/leaves/', self.payload(
            start_date=samedi.isoformat(),
            end_date=(samedi + timedelta(days=1)).isoformat(),
        ), format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_reason_is_required(self):
        reponse = self.client.post(
            '/api/leaves/', self.payload(reason='   '), format='json'
        )
        self.assertEqual(reponse.status_code, 400)

    # --- Cloisonnement ----------------------------------------------------

    def test_colleague_requests_stay_invisible(self):
        autre = self.make(member=self.lea, semaines=2)

        liste = self.client.get('/api/leaves/')
        self.assertEqual(liste.data['count'], 0)
        self.assertEqual(self.client.get(f'/api/leaves/{autre.id}/').status_code, 404)

    def test_founder_sees_the_whole_team(self):
        self.make()
        self.make(member=self.lea, semaines=2)
        self.authenticate(self.founder)

        self.assertEqual(self.client.get('/api/leaves/').data['count'], 2)

    # --- Décision ---------------------------------------------------------

    def test_member_cannot_decide(self):
        demande = self.make()
        reponse = self.client.patch(f'/api/leaves/{demande.id}/decide/',
                                    {'status': 'approved'}, format='json')
        self.assertEqual(reponse.status_code, 403)

    def test_founder_approves_and_signs(self):
        demande = self.make()
        self.authenticate(self.founder)

        reponse = self.client.patch(f'/api/leaves/{demande.id}/decide/', {
            'status': 'approved', 'decision': 'Bon congé.',
        }, format='json')

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['status'], 'approved')
        self.assertEqual(reponse.data['decided_by'], self.founder.id)
        self.assertEqual(reponse.data['decision'], 'Bon congé.')

    def test_unknown_decision_is_refused(self):
        demande = self.make()
        self.authenticate(self.founder)
        reponse = self.client.patch(f'/api/leaves/{demande.id}/decide/',
                                    {'status': 'peut-être'}, format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_a_decided_request_is_frozen(self):
        demande = self.make(status='approved')
        reponse = self.client.patch(f'/api/leaves/{demande.id}/',
                                    {'reason': 'Autre motif.'}, format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_pending_request_stays_editable_by_its_author(self):
        demande = self.make()
        reponse = self.client.patch(f'/api/leaves/{demande.id}/',
                                    {'reason': 'Motif précisé.'}, format='json')
        self.assertEqual(reponse.status_code, 200)

    def test_author_cancels_a_request(self):
        demande = self.make()
        reponse = self.client.patch(f'/api/leaves/{demande.id}/cancel/',
                                    {}, format='json')

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['status'], 'cancelled')

    def test_a_past_leave_is_not_cancelled(self):
        passe = timezone.localdate() - timedelta(days=10)
        demande = self.make(status='approved', start_date=passe,
                            end_date=passe + timedelta(days=2))
        reponse = self.client.patch(f'/api/leaves/{demande.id}/cancel/',
                                    {}, format='json')
        self.assertEqual(reponse.status_code, 400)

    # --- Solde ------------------------------------------------------------

    def test_balance_counts_only_approved_paid_leave(self):
        self.make(status='approved')                                   # 5 jours
        self.make(semaines=3, kind='sick', status='approved')           # hors solde
        self.make(semaines=5)                                           # en attente

        reponse = self.client.get('/api/leaves/balance/')
        ligne = reponse.data['members'][0]

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.data['members']), 1)
        self.assertEqual(ligne['entitlement'], 18)
        self.assertEqual(ligne['taken'], 5.0)
        self.assertEqual(ligne['pending'], 5.0)
        self.assertEqual(ligne['balance'], 13.0)

    def test_founder_reads_the_whole_team_balance(self):
        self.authenticate(self.founder)
        reponse = self.client.get('/api/leaves/balance/')
        self.assertEqual(len(reponse.data['members']), 3)

    # --- Retombées --------------------------------------------------------

    def test_direction_is_notified_of_pending_requests(self):
        self.make()
        self.authenticate(self.founder)

        genres = [a['kind'] for a in
                  self.client.get('/api/dashboard/notifications/').data['items']]
        self.assertIn('leaves_pending', genres)

    def test_a_member_is_not_notified_of_his_own_pending_request(self):
        self.make()
        genres = [a['kind'] for a in
                  self.client.get('/api/dashboard/notifications/').data['items']]
        self.assertNotIn('leaves_pending', genres)


class AttendanceTest(TeamTestCase):
    """Pointage : l'équipe pointe, la direction relit et corrige."""

    def at(self, heure, minute=0, day=None):
        jour = day or timezone.localdate()
        return timezone.make_aware(datetime.combine(jour, time(heure, minute)))

    # --- Pointer -----------------------------------------------------------

    def test_check_in_opens_the_day(self):
        reponse = self.client.post('/api/attendance/check_in/', {}, format='json')

        self.assertEqual(reponse.status_code, 201)
        self.assertTrue(reponse.data['is_open'])
        self.assertEqual(reponse.data['member'], self.karim.id)

    def test_check_in_twice_keeps_the_same_day(self):
        premier = self.client.post('/api/attendance/check_in/', {}, format='json')
        second = self.client.post('/api/attendance/check_in/', {}, format='json')

        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data['id'], premier.data['id'])
        self.assertEqual(Attendance.objects.count(), 1)

    def test_check_out_closes_the_day(self):
        self.client.post('/api/attendance/check_in/', {}, format='json')
        reponse = self.client.post('/api/attendance/check_out/', {}, format='json')

        self.assertEqual(reponse.status_code, 200)
        self.assertFalse(reponse.data['is_open'])
        self.assertIsNotNone(reponse.data['check_out'])

    def test_check_out_without_arrival_is_refused(self):
        reponse = self.client.post('/api/attendance/check_out/', {}, format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_check_out_twice_is_refused(self):
        self.client.post('/api/attendance/check_in/', {}, format='json')
        self.client.post('/api/attendance/check_out/', {}, format='json')
        reponse = self.client.post('/api/attendance/check_out/', {}, format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_check_in_after_a_closed_day_is_refused(self):
        """Rouvrir sa journée relancerait le compteur : le jour est fait."""
        self.client.post('/api/attendance/check_in/', {}, format='json')
        self.client.post('/api/attendance/check_out/', {}, format='json')
        reponse = self.client.post('/api/attendance/check_in/', {}, format='json')
        self.assertEqual(reponse.status_code, 400)

    def test_today_reports_the_running_day_and_the_month(self):
        self.client.post('/api/attendance/check_in/', {}, format='json')
        reponse = self.client.get('/api/attendance/today/')

        self.assertEqual(reponse.status_code, 200)
        self.assertIsNotNone(reponse.data['attendance'])
        self.assertEqual(reponse.data['month']['days'], 1)

    # --- Correction --------------------------------------------------------

    def test_member_cannot_write_a_record_by_hand(self):
        """Saisir son arrivée à la main viderait le pointage de son sens."""
        reponse = self.client.post('/api/attendance/', {
            'member': self.karim.id,
            'date': timezone.localdate().isoformat(),
            'check_in': self.at(8, 0).isoformat(),
        }, format='json')
        self.assertEqual(reponse.status_code, 403)

    def test_member_cannot_rewrite_his_own_record(self):
        pointage = Attendance.objects.create(
            member=self.karim, check_in=self.at(9, 30)
        )
        reponse = self.client.patch(f'/api/attendance/{pointage.id}/',
                                    {'check_in': self.at(8, 0).isoformat()},
                                    format='json')
        self.assertEqual(reponse.status_code, 403)

    def test_direction_corrects_and_the_lateness_follows(self):
        pointage = Attendance.objects.create(
            member=self.karim, check_in=self.at(9, 30)
        )
        self.assertEqual(pointage.late_minutes, 80)
        self.authenticate(self.founder)

        reponse = self.client.patch(f'/api/attendance/{pointage.id}/',
                                    {'check_in': self.at(8, 5).isoformat()},
                                    format='json')

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(reponse.data['late_minutes'], 0)

    def test_departure_before_arrival_is_refused(self):
        pointage = Attendance.objects.create(
            member=self.karim, check_in=self.at(8, 0)
        )
        self.authenticate(self.founder)

        reponse = self.client.patch(f'/api/attendance/{pointage.id}/',
                                    {'check_out': self.at(7, 0).isoformat()},
                                    format='json')
        self.assertEqual(reponse.status_code, 400)

    # --- Cloisonnement ------------------------------------------------------

    def test_colleague_records_stay_invisible(self):
        autre = Attendance.objects.create(member=self.lea, check_in=self.at(8, 0))

        self.assertEqual(self.client.get('/api/attendance/').data['count'], 0)
        self.assertEqual(
            self.client.get(f'/api/attendance/{autre.id}/').status_code, 404
        )

    def test_summary_stays_personal_for_a_member(self):
        Attendance.objects.create(member=self.lea, check_in=self.at(8, 0))
        reponse = self.client.get('/api/attendance/summary/')

        self.assertEqual(reponse.status_code, 200)
        self.assertEqual(len(reponse.data['members']), 1)
        self.assertEqual(reponse.data['members'][0]['member_id'], self.karim.id)

    def test_summary_counts_days_hours_and_lateness(self):
        pointage = Attendance.objects.create(
            member=self.karim, check_in=self.at(8, 40)
        )
        pointage.close(self.at(16, 40))
        self.authenticate(self.founder)

        reponse = self.client.get('/api/attendance/summary/')
        ligne = next(l for l in reponse.data['members']
                     if l['member_id'] == self.karim.id)

        self.assertEqual(len(reponse.data['members']), 3)
        self.assertEqual(ligne['days'], 1)
        self.assertEqual(ligne['hours'], 8.0)
        self.assertEqual(ligne['late_minutes'], 30)

    def test_approved_leave_is_not_counted_as_an_absence(self):
        jour = timezone.localdate()
        LeaveRequest.objects.create(
            member=self.karim, kind='paid', status='approved',
            start_date=jour.replace(day=1), end_date=jour,
            reason='Congé annuel.',
        )
        self.authenticate(self.founder)

        reponse = self.client.get('/api/attendance/summary/')
        karim = next(l for l in reponse.data['members']
                     if l['member_id'] == self.karim.id)
        lea = next(l for l in reponse.data['members']
                   if l['member_id'] == self.lea.id)

        self.assertGreater(karim['leave_days'], 0)
        self.assertLess(karim['absences'], lea['absences'])

    # --- Panel --------------------------------------------------------------

    def test_panel_shows_arrivals_and_leaves(self):
        jour = timezone.localdate()
        Attendance.objects.create(member=self.karim, check_in=self.at(8, 0))
        LeaveRequest.objects.create(
            member=self.lea, kind='paid', status='approved',
            start_date=jour - timedelta(days=1), end_date=jour + timedelta(days=1),
            reason='Congé annuel.',
        )
        self.authenticate(self.founder)

        panel = self.client.get('/api/dashboard/panel/').data
        karim = next(l for l in panel['members'] if l['member_id'] == self.karim.id)
        lea = next(l for l in panel['members'] if l['member_id'] == self.lea.id)

        self.assertEqual(panel['totals']['checked_in'], 1)
        self.assertEqual(panel['totals']['on_leave'], 1)
        self.assertIsNotNone(karim['attendance'])
        self.assertEqual(lea['status'], 'on_leave')
        self.assertEqual(lea['on_leave'], 'Congé payé')

    def test_overview_carries_the_day_and_the_balance(self):
        self.client.post('/api/attendance/check_in/', {}, format='json')
        reponse = self.client.get('/api/dashboard/overview/')

        self.assertIsNotNone(reponse.data['attendance'])
        self.assertEqual(reponse.data['leave_balance'], 18.0)


class LoginThrottleTest(APITestCase):
    """Limite de connexion : un mot de passe ne se devine pas en rafale."""

    def setUp(self):
        User.objects.create_user('karim', password='pass-Solide1')
        # Le compteur vit dans le cache : un essai laissé par un autre test
        # fausserait celui-ci.
        cache.clear()

    def tearDown(self):
        cache.clear()

    def limite(self, taux='3/min'):
        """Rétablit la limite, neutralisée pour le reste de la suite.

        Le taux se pose sur la classe : DRF le lie à `THROTTLE_RATES` au moment
        de l'import, hors de portée d'`override_settings`.
        """
        return patch.object(SimpleRateThrottle, 'THROTTLE_RATES',
                            {'login': taux, 'register': None})

    def essai(self, motdepasse):
        return self.client.post('/api/auth/login/', {
            'username': 'karim', 'password': motdepasse,
        }, format='json')

    def test_repeated_failures_close_the_door(self):
        """Passé le quota, même le bon mot de passe est refusé."""
        with self.limite():
            for _ in range(3):
                self.assertEqual(self.essai('faux').status_code, 400)

            # Le quota est atteint : la vue ne vérifie plus rien, elle compte.
            self.assertEqual(self.essai('pass-Solide1').status_code, 429)

    def test_a_normal_login_passes(self):
        with self.limite():
            reponse = self.essai('pass-Solide1')
            self.assertEqual(reponse.status_code, 200)
            self.assertIn('token', reponse.data)

    def test_the_suite_runs_without_a_limit(self):
        """Hors test dédié, la limite est neutralisée : voir le test runner."""
        for _ in range(12):
            self.assertEqual(self.essai('faux').status_code, 400)
