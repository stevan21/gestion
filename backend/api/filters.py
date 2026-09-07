"""
FilterSets exposés en query string.
"""

from django_filters import rest_framework as filters

from .models import (
    Attendance, DailyTask, LeaveRequest, Member, MonthlyObjective, Payslip,
    Reaction, Report, RoadmapItem, StaffEvent, Suggestion,
)


class MemberFilter(filters.FilterSet):
    """Filtres des profils d'équipe."""

    department = filters.ChoiceFilter(choices=Member.DEPARTMENT_CHOICES)
    role = filters.ChoiceFilter(choices=Member.ROLE_CHOICES)
    name = filters.CharFilter(field_name='user__last_name', lookup_expr='icontains')
    is_active = filters.BooleanFilter(field_name='user__is_active')

    class Meta:
        model = Member
        fields = ['department', 'role']


class MonthlyObjectiveFilter(filters.FilterSet):
    """Filtres des objectifs mensuels."""

    month = filters.DateFilter(field_name='month')
    month_from = filters.DateFilter(field_name='month', lookup_expr='gte')
    month_to = filters.DateFilter(field_name='month', lookup_expr='lte')
    status = filters.ChoiceFilter(choices=MonthlyObjective.STATUS_CHOICES)
    department = filters.ChoiceFilter(
        field_name='member__department', choices=Member.DEPARTMENT_CHOICES
    )
    revenue_min = filters.NumberFilter(field_name='revenue_achieved', lookup_expr='gte')
    revenue_max = filters.NumberFilter(field_name='revenue_achieved', lookup_expr='lte')

    class Meta:
        model = MonthlyObjective
        fields = ['member', 'month', 'status']


class RoadmapItemFilter(filters.FilterSet):
    """Filtres des jalons de feuille de route."""

    status = filters.ChoiceFilter(choices=RoadmapItem.STATUS_CHOICES)
    month = filters.DateFilter(field_name='objective__month')
    member = filters.NumberFilter(field_name='objective__member_id')
    due_before = filters.DateFilter(field_name='due_date', lookup_expr='lte')
    due_after = filters.DateFilter(field_name='due_date', lookup_expr='gte')
    has_due_date = filters.BooleanFilter(field_name='due_date', lookup_expr='isnull',
                                         exclude=True)

    class Meta:
        model = RoadmapItem
        fields = ['objective', 'status']


class DailyTaskFilter(filters.FilterSet):
    """Filtres des tâches quotidiennes."""

    status = filters.ChoiceFilter(choices=DailyTask.STATUS_CHOICES)
    priority = filters.ChoiceFilter(choices=DailyTask.PRIORITY_CHOICES)
    date = filters.DateFilter(field_name='date')
    date_from = filters.DateFilter(field_name='date', lookup_expr='gte')
    date_to = filters.DateFilter(field_name='date', lookup_expr='lte')
    department = filters.ChoiceFilter(
        field_name='member__department', choices=Member.DEPARTMENT_CHOICES
    )
    linked = filters.BooleanFilter(field_name='roadmap_item', lookup_expr='isnull',
                                   exclude=True)

    class Meta:
        model = DailyTask
        fields = ['member', 'date', 'status', 'priority', 'roadmap_item']


class PayslipFilter(filters.FilterSet):
    """Filtres des bulletins de paie."""

    month = filters.CharFilter(method='filter_month')
    department = filters.ChoiceFilter(
        field_name='member__department', choices=Member.DEPARTMENT_CHOICES
    )

    class Meta:
        model = Payslip
        fields = ['member']

    def filter_month(self, queryset, name, value):
        """Filtre sur un mois `AAAA-MM`."""
        try:
            year, month = value.split('-')
            return queryset.filter(month__year=int(year), month__month=int(month))
        except (ValueError, AttributeError):
            return queryset.none()


class StaffEventFilter(filters.FilterSet):
    """Filtres des évènements de personnel."""

    kind = filters.ChoiceFilter(choices=StaffEvent.KIND_CHOICES)
    from_date = filters.DateFilter(field_name='date', lookup_expr='gte')
    to_date = filters.DateFilter(field_name='date', lookup_expr='lte')
    department = filters.ChoiceFilter(
        field_name='member__department', choices=Member.DEPARTMENT_CHOICES
    )

    class Meta:
        model = StaffEvent
        fields = ['member', 'kind']


class ReactionFilter(filters.FilterSet):
    """Filtres des réactions."""

    kind = filters.ChoiceFilter(choices=Reaction.KIND_CHOICES)
    from_date = filters.DateFilter(field_name='date', lookup_expr='gte')
    to_date = filters.DateFilter(field_name='date', lookup_expr='lte')

    class Meta:
        model = Reaction
        fields = ['member', 'kind']


class SuggestionFilter(filters.FilterSet):
    """Filtres de la boîte à suggestions."""

    category = filters.ChoiceFilter(choices=Suggestion.CATEGORY_CHOICES)
    status = filters.ChoiceFilter(choices=Suggestion.STATUS_CHOICES)

    class Meta:
        model = Suggestion
        fields = ['author', 'category', 'status']


class ReportFilter(filters.FilterSet):
    """Filtres des rapports."""

    period_type = filters.ChoiceFilter(choices=Report.PERIOD_CHOICES)
    status = filters.ChoiceFilter(choices=Report.STATUS_CHOICES)
    from_date = filters.DateFilter(field_name='period_end', lookup_expr='gte')
    to_date = filters.DateFilter(field_name='period_end', lookup_expr='lte')
    department = filters.ChoiceFilter(
        field_name='member__department', choices=Member.DEPARTMENT_CHOICES
    )

    class Meta:
        model = Report
        fields = ['member', 'period_type', 'status']


class LeaveRequestFilter(filters.FilterSet):
    """Filtres des demandes de congé.

    Les bornes retiennent tout ce qui chevauche la période : un congé à cheval
    sur deux mois appartient aux deux.
    """

    kind = filters.ChoiceFilter(choices=LeaveRequest.KIND_CHOICES)
    status = filters.ChoiceFilter(choices=LeaveRequest.STATUS_CHOICES)
    from_date = filters.DateFilter(field_name='end_date', lookup_expr='gte')
    to_date = filters.DateFilter(field_name='start_date', lookup_expr='lte')
    year = filters.NumberFilter(field_name='start_date', lookup_expr='year')
    department = filters.ChoiceFilter(
        field_name='member__department', choices=Member.DEPARTMENT_CHOICES
    )

    class Meta:
        model = LeaveRequest
        fields = ['member', 'kind', 'status']


class AttendanceFilter(filters.FilterSet):
    """Filtres des pointages."""

    date = filters.DateFilter(field_name='date')
    from_date = filters.DateFilter(field_name='date', lookup_expr='gte')
    to_date = filters.DateFilter(field_name='date', lookup_expr='lte')
    late = filters.BooleanFilter(method='filter_late')
    open = filters.BooleanFilter(field_name='check_out', lookup_expr='isnull')
    department = filters.ChoiceFilter(
        field_name='member__department', choices=Member.DEPARTMENT_CHOICES
    )

    class Meta:
        model = Attendance
        fields = ['member', 'date']

    def filter_late(self, queryset, name, value):
        """Ne garde que les arrivées en retard, ou seulement celles à l'heure."""
        if value is None:
            return queryset
        return queryset.filter(late_minutes__gt=0) if value else queryset.filter(
            late_minutes=0
        )
