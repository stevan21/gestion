"""
Tests unitaires des modèles et des managers.
"""

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from api.managers import month_range, month_start
from api.models import (
    Attendance, DailyTask, LeaveRequest, Member, MonthlyObjective, Report,
    RoadmapItem, working_days,
)
from api.tasks import close_stale_attendance


class MemberModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            'karim', password='pass-Solide1', first_name='Karim', last_name='Benali'
        )
        self.member = Member.objects.for_user(self.user)

    def test_display_name_uses_full_name(self):
        self.assertEqual(self.member.display_name, 'Karim Benali')

    def test_display_name_falls_back_to_username(self):
        self.user.first_name = self.user.last_name = ''
        self.user.save()
        self.assertEqual(Member.objects.for_user(self.user).display_name, 'karim')

    def test_staff_account_is_treated_as_founder(self):
        """Un compte d'administration doit voir l'équipe sans rôle explicite."""
        self.user.is_staff = True
        self.user.save()
        self.assertTrue(Member.objects.for_user(self.user).is_founder)

    def test_for_user_returns_none_for_anonymous(self):
        from django.contrib.auth.models import AnonymousUser
        self.assertIsNone(Member.objects.for_user(AnonymousUser()))


class MonthlyObjectiveModelTest(TestCase):
    def setUp(self):
        self.member = Member.objects.for_user(
            User.objects.create_user('karim', password='pass-Solide1')
        )
        self.other = Member.objects.for_user(
            User.objects.create_user('lea', password='pass-Solide1')
        )

    def make(self, **overrides):
        defaults = {
            'member': self.member,
            'month': month_start(),
            'revenue_target': Decimal('20000'),
            'revenue_achieved': Decimal('12000'),
            'clients_target': 10,
            'clients_achieved': 6,
        }
        defaults.update(overrides)
        return MonthlyObjective.objects.create(**defaults)

    def test_month_normalised_on_save(self):
        objective = self.make(month=date(2026, 5, 23))
        self.assertEqual(objective.month, date(2026, 5, 1))

    def test_unique_per_member_and_month(self):
        self.make()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.make()

    def test_same_month_allowed_for_another_member(self):
        self.make()
        self.make(member=self.other)
        self.assertEqual(MonthlyObjective.objects.count(), 2)

    def test_completion_averages_defined_targets(self):
        objective = self.make(clients_achieved=10)  # 60 % CA, 100 % clients
        self.assertEqual(objective.revenue_completion, 60.0)
        self.assertEqual(objective.clients_completion, 100.0)
        self.assertEqual(objective.completion, 80.0)

    def test_completion_is_none_without_any_target(self):
        objective = self.make(revenue_target=Decimal('0'), clients_target=0)
        self.assertIsNone(objective.completion)

    def test_revenue_gap_never_negative(self):
        objective = self.make(revenue_achieved=Decimal('25000'))
        self.assertEqual(objective.revenue_gap, Decimal('0'))

    def test_elapsed_ratio_is_full_for_past_month(self):
        previous, _ = month_range(months_back=1)
        self.assertEqual(self.make(month=previous).elapsed_ratio, 100.0)

    def test_next_month_start_crosses_the_year(self):
        objective = self.make(month=date(2026, 12, 1))
        self.assertEqual(objective.next_month_start(), date(2027, 1, 1))

    def test_str_is_readable(self):
        objective = self.make(month=date(2026, 3, 1))
        self.assertIn('03/2026', str(objective))


class RoadmapItemModelTest(TestCase):
    def setUp(self):
        self.member = Member.objects.for_user(
            User.objects.create_user('karim', password='pass-Solide1')
        )
        self.objective = MonthlyObjective.objects.create(
            member=self.member, month=month_start(),
            revenue_target=Decimal('1000'), clients_target=1,
        )

    def test_done_forces_full_progress(self):
        item = RoadmapItem.objects.create(
            objective=self.objective, title='Jalon', status='done', progress=10
        )
        self.assertEqual(item.progress, 100)
        self.assertIsNotNone(item.completed_at)

    def test_reopening_caps_progress_below_full(self):
        item = RoadmapItem.objects.create(
            objective=self.objective, title='Jalon', status='done'
        )
        item.status = 'todo'
        item.save()
        self.assertEqual(item.progress, 99)
        self.assertIsNone(item.completed_at)

    def test_overdue_only_when_unfinished(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        late = RoadmapItem.objects.create(
            objective=self.objective, title='Retard', due_date=yesterday
        )
        done = RoadmapItem.objects.create(
            objective=self.objective, title='Fait', due_date=yesterday, status='done'
        )
        self.assertTrue(late.is_overdue)
        self.assertFalse(done.is_overdue)

    def test_no_due_date_is_never_overdue(self):
        item = RoadmapItem.objects.create(objective=self.objective, title='Sans date')
        self.assertFalse(item.is_overdue)

    def test_ordering_follows_position(self):
        RoadmapItem.objects.create(objective=self.objective, title='B', position=2)
        RoadmapItem.objects.create(objective=self.objective, title='A', position=1)
        self.assertEqual(
            list(RoadmapItem.objects.values_list('title', flat=True)), ['A', 'B']
        )


class DailyTaskModelTest(TestCase):
    def setUp(self):
        self.member = Member.objects.for_user(
            User.objects.create_user('karim', password='pass-Solide1')
        )

    def test_completion_timestamp_set_and_cleared(self):
        task = DailyTask.objects.create(member=self.member, title='Tâche', status='done')
        self.assertIsNotNone(task.completed_at)

        task.status = 'todo'
        task.save()
        self.assertIsNone(task.completed_at)

    def test_defaults_to_today(self):
        task = DailyTask.objects.create(member=self.member, title='Tâche')
        self.assertEqual(task.date, timezone.localdate())

    def test_late_excludes_finished_tasks(self):
        yesterday = timezone.localdate() - timedelta(days=1)
        DailyTask.objects.create(member=self.member, title='Ouverte', date=yesterday)
        DailyTask.objects.create(
            member=self.member, title='Terminée', date=yesterday, status='done'
        )
        self.assertEqual(DailyTask.objects.late().count(), 1)

    def test_completion_rate(self):
        DailyTask.objects.create(member=self.member, title='A', status='done')
        DailyTask.objects.create(member=self.member, title='B')
        self.assertEqual(DailyTask.objects.completion_rate(), 50.0)

    def test_completion_rate_is_none_without_tasks(self):
        self.assertIsNone(DailyTask.objects.completion_rate())

    def test_ordering_puts_urgent_first(self):
        DailyTask.objects.create(member=self.member, title='Normale', priority=2)
        DailyTask.objects.create(member=self.member, title='Urgente', priority=4)
        self.assertEqual(DailyTask.objects.first().title, 'Urgente')


class ReportModelTest(TestCase):
    def setUp(self):
        self.member = Member.objects.for_user(
            User.objects.create_user('karim', password='pass-Solide1')
        )

    def test_submit_sets_status_and_timestamp(self):
        report = Report.objects.create(
            member=self.member, period_type='weekly',
            period_start=timezone.localdate() - timedelta(days=6),
            period_end=timezone.localdate(), summary='Bilan.',
        )
        report.submit()
        self.assertEqual(report.status, 'submitted')
        self.assertIsNotNone(report.submitted_at)

    def test_covering_finds_the_right_period(self):
        today = timezone.localdate()
        Report.objects.create(
            member=self.member, period_type='weekly',
            period_start=today - timedelta(days=6), period_end=today, summary='Bilan.',
        )
        self.assertEqual(Report.objects.covering(today).count(), 1)
        self.assertEqual(
            Report.objects.covering(today - timedelta(days=30)).count(), 0
        )


class VisibilityTest(TestCase):
    """Règle de visibilité appliquée au niveau des QuerySets."""

    def setUp(self):
        self.founder = Member.objects.for_user(
            User.objects.create_user('awa', password='pass-Solide1')
        )
        self.founder.role = 'founder'
        self.founder.save()

        self.karim = Member.objects.for_user(
            User.objects.create_user('karim', password='pass-Solide1')
        )
        self.lea = Member.objects.for_user(
            User.objects.create_user('lea', password='pass-Solide1')
        )

        for member in (self.karim, self.lea):
            objective = MonthlyObjective.objects.create(
                member=member, month=month_start(),
                revenue_target=Decimal('1000'), clients_target=1,
            )
            RoadmapItem.objects.create(objective=objective, title=f'Jalon {member}')
            DailyTask.objects.create(member=member, title=f'Tâche {member}')
            Report.objects.create(
                member=member, period_type='weekly',
                period_start=timezone.localdate() - timedelta(days=6),
                period_end=timezone.localdate(), summary='Bilan.',
            )

    def test_member_scope_is_limited_to_own_rows(self):
        self.assertEqual(MonthlyObjective.objects.visible_to(self.karim).count(), 1)
        self.assertEqual(RoadmapItem.objects.visible_to(self.karim).count(), 1)
        self.assertEqual(DailyTask.objects.visible_to(self.karim).count(), 1)
        self.assertEqual(Report.objects.visible_to(self.karim).count(), 1)

    def test_founder_scope_covers_the_team(self):
        self.assertEqual(MonthlyObjective.objects.visible_to(self.founder).count(), 2)
        self.assertEqual(RoadmapItem.objects.visible_to(self.founder).count(), 2)
        self.assertEqual(DailyTask.objects.visible_to(self.founder).count(), 2)
        self.assertEqual(Report.objects.visible_to(self.founder).count(), 2)

    def test_no_member_sees_nothing(self):
        """Sans profil, aucune donnée ne doit remonter."""
        self.assertEqual(MonthlyObjective.objects.visible_to(None).count(), 0)
        self.assertEqual(DailyTask.objects.visible_to(None).count(), 0)


class MonthHelperTest(TestCase):
    def test_month_start_normalises(self):
        self.assertEqual(month_start(date(2026, 7, 19)), date(2026, 7, 1))

    def test_month_range_walks_back_over_the_year(self):
        start, end = month_range(months_back=2, reference=date(2026, 1, 15))
        self.assertEqual(start, date(2025, 11, 1))
        self.assertEqual(end, date(2025, 11, 30))

    def test_month_range_end_is_last_day(self):
        start, end = month_range(months_back=0, reference=date(2026, 2, 10))
        self.assertEqual(start, date(2026, 2, 1))
        self.assertEqual(end, date(2026, 2, 28))


class WorkingDaysTest(TestCase):
    """Décompte des jours ouvrables, base du solde de congés."""

    def test_week_end_is_not_counted(self):
        # Du vendredi 3 juillet 2026 au lundi 6 : deux jours ouvrables.
        self.assertEqual(working_days(date(2026, 7, 3), date(2026, 7, 6)), 2)

    def test_single_working_day(self):
        self.assertEqual(working_days(date(2026, 7, 7), date(2026, 7, 7)), 1)

    def test_inverted_range_counts_nothing(self):
        self.assertEqual(working_days(date(2026, 7, 8), date(2026, 7, 1)), 0)


class LeaveRequestModelTest(TestCase):
    def setUp(self):
        self.member = Member.objects.for_user(
            User.objects.create_user('karim', password='pass-Solide1')
        )
        self.founder = Member.objects.for_user(
            User.objects.create_user('awa', password='pass-Solide1')
        )

    def make(self, **overrides):
        defaults = {
            'member': self.member,
            'kind': 'paid',
            'start_date': date(2026, 7, 6),
            'end_date': date(2026, 7, 10),
            'reason': 'Congé annuel.',
        }
        return LeaveRequest.objects.create(**{**defaults, **overrides})

    def test_days_counts_working_days_only(self):
        self.assertEqual(self.make().days, 5.0)

    def test_half_day_counts_for_half(self):
        demande = self.make(start_date=date(2026, 7, 6), end_date=date(2026, 7, 6),
                            half_day=True)
        self.assertEqual(demande.days, 0.5)
        self.assertEqual(demande.days_label, '0,5 jour')

    def test_decision_records_its_author(self):
        demande = self.make()
        demande.decide('approved', member=self.founder, decision="Bon congé.")

        demande.refresh_from_db()
        self.assertEqual(demande.status, 'approved')
        self.assertEqual(demande.decided_by, self.founder)
        self.assertIsNotNone(demande.decided_at)

    def test_only_approved_paid_leave_eats_the_balance(self):
        """Une maladie ou une demande en attente n'entame pas le droit annuel."""
        self.make(status='approved')                       # 5 jours décomptés
        self.make(start_date=date(2026, 8, 3), end_date=date(2026, 8, 7),
                  kind='sick', status='approved')          # hors décompte
        self.make(start_date=date(2026, 9, 7), end_date=date(2026, 9, 11))  # en attente

        with patch('api.managers.timezone.localdate', return_value=date(2026, 12, 31)):
            self.assertEqual(self.member.leave_days_taken, 5.0)
            self.assertEqual(self.member.leave_balance, 13.0)

    def test_covers_ignores_a_refused_request(self):
        demande = self.make(status='refused')
        self.assertFalse(demande.covers(date(2026, 7, 7)))


class AttendanceModelTest(TestCase):
    def setUp(self):
        self.member = Member.objects.for_user(
            User.objects.create_user('karim', password='pass-Solide1')
        )

    def at(self, heure, minute=0, day=None):
        """Instant local du jour donné, ramené au fuseau du projet."""
        jour = day or timezone.localdate()
        return timezone.make_aware(
            datetime.combine(jour, time(heure, minute))
        )

    def test_arrival_within_the_grace_period_is_not_late(self):
        pointage = Attendance.objects.create(
            member=self.member, check_in=self.at(8, 10)
        )
        self.assertEqual(pointage.late_minutes, 0)

    def test_lateness_deducts_the_grace_period(self):
        pointage = Attendance.objects.create(
            member=self.member, check_in=self.at(8, 40)
        )
        self.assertEqual(pointage.late_minutes, 30)
        self.assertTrue(pointage.is_late)

    def test_lateness_follows_the_member_schedule(self):
        self.member.work_starts_at = time(9, 0)
        self.member.save(update_fields=['work_starts_at'])

        pointage = Attendance.objects.create(
            member=self.member, check_in=self.at(8, 40)
        )
        self.assertEqual(pointage.late_minutes, 0)

    def test_closing_computes_the_duration(self):
        pointage = Attendance.objects.create(
            member=self.member, check_in=self.at(8, 0)
        )
        pointage.close(self.at(16, 30))

        self.assertEqual(pointage.minutes, 510)
        self.assertEqual(pointage.duration_label, '8 h 30')
        self.assertEqual(pointage.hours, Decimal('8.50'))
        self.assertFalse(pointage.is_open)

    def test_closing_twice_keeps_the_first_departure(self):
        pointage = Attendance.objects.create(
            member=self.member, check_in=self.at(8, 0)
        )
        pointage.close(self.at(16, 0))
        pointage.close(self.at(18, 0))
        self.assertEqual(pointage.minutes, 480)

    def test_a_forgotten_departure_stops_at_the_end_of_that_day(self):
        """Sans cette borne, un départ oublié compterait la nuit entière."""
        hier = timezone.localdate() - timedelta(days=1)
        pointage = Attendance.objects.create(
            member=self.member, date=hier, check_in=self.at(8, 0, day=hier)
        )
        # 8 h → 17 h, l'heure de fin du profil, et pas jusqu'à maintenant.
        self.assertEqual(pointage.minutes, 540)

    def test_one_record_per_member_and_day(self):
        Attendance.objects.create(member=self.member, check_in=self.at(8, 0))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Attendance.objects.create(member=self.member, check_in=self.at(9, 0))

    def test_open_for_returns_the_running_day(self):
        premier, cree = Attendance.open_for(self.member)
        second, encore = Attendance.open_for(self.member)

        self.assertTrue(cree)
        self.assertFalse(encore)
        self.assertEqual(premier.pk, second.pk)


class CloseStaleAttendanceTest(TestCase):
    """La tâche qui referme les départs oubliés."""

    def setUp(self):
        self.member = Member.objects.for_user(
            User.objects.create_user('karim', password='pass-Solide1')
        )

    def test_yesterday_is_closed_on_the_expected_end_time(self):
        hier = timezone.localdate() - timedelta(days=1)
        pointage = Attendance.objects.create(
            member=self.member, date=hier,
            check_in=timezone.make_aware(datetime.combine(hier, time(8, 0))),
        )

        close_stale_attendance()

        pointage.refresh_from_db()
        self.assertEqual(timezone.localtime(pointage.check_out).hour, 17)

    def test_today_is_left_running(self):
        pointage = Attendance.objects.create(
            member=self.member,
            check_in=timezone.now() - timedelta(hours=1),
        )
        close_stale_attendance()

        pointage.refresh_from_db()
        self.assertTrue(pointage.is_open)
