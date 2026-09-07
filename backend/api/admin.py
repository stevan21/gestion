"""
Administration Django de Flux Gestion.
"""

from django.contrib import admin
from django.utils.html import format_html

from .formatting import format_fcfa
from .models import (
    Attendance, DailyTask, LeaveRequest, Member, MonthlyObjective, Payslip,
    Reaction, Report, RoadmapItem, StaffEvent, Suggestion,
)


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    list_display = ('display_name', 'role', 'job_title', 'department', 'joined_on')
    list_filter = ('role', 'department', 'joined_on')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'job_title')
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ('user',)
    fieldsets = (
        ('Compte', {'fields': ('user', 'role')}),
        ('Poste', {'fields': ('job_title', 'department', 'joined_on', 'phone')}),
        ('Journée et congés', {
            'fields': ('work_starts_at', 'work_ends_at', 'leave_entitlement'),
            'description': "L'heure de début sert de repère au pointage ; le "
                           "droit annuel s'exprime en jours ouvrables.",
        }),
        ('Suivi', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Membre', ordering='user__first_name')
    def display_name(self, obj):
        return obj.display_name


class RoadmapItemInline(admin.TabularInline):
    """La feuille de route se saisit dans le contexte de son objectif."""
    model = RoadmapItem
    extra = 0
    fields = ('position', 'title', 'due_date', 'status', 'progress')
    ordering = ('position',)


@admin.register(MonthlyObjective)
class MonthlyObjectiveAdmin(admin.ModelAdmin):
    list_display = ('month_label', 'member', 'revenue_summary', 'clients_summary',
                    'completion_badge', 'status')
    list_filter = ('status', 'month', 'member__department')
    search_fields = ('member__user__first_name', 'member__user__last_name', 'focus')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'month'
    inlines = [RoadmapItemInline]
    fieldsets = (
        ('Période', {'fields': ('member', 'month', 'status')}),
        ('Chiffre d\'affaires', {'fields': ('revenue_target', 'revenue_achieved')}),
        ('Clients', {'fields': ('clients_target', 'clients_achieved')}),
        ('Contexte', {'fields': ('focus', 'notes')}),
        ('Suivi', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Mois', ordering='month')
    def month_label(self, obj):
        return obj.month_label

    @admin.display(description='CA')
    def revenue_summary(self, obj):
        return f"{format_fcfa(obj.revenue_achieved)} / {format_fcfa(obj.revenue_target)}"

    @admin.display(description='Clients')
    def clients_summary(self, obj):
        return f"{obj.clients_achieved} / {obj.clients_target}"

    @admin.display(description='Avancement')
    def completion_badge(self, obj):
        value = obj.completion
        if value is None:
            return '—'
        color = '#16a34a' if value >= 100 else ('#f59e0b' if value >= 70 else '#dc2626')
        return format_html('<b style="color:{}">{:.0f} %</b>', color, value)


@admin.register(RoadmapItem)
class RoadmapItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'objective', 'due_date', 'status', 'progress')
    list_filter = ('status', 'due_date', 'objective__member__department')
    search_fields = ('title', 'description')
    readonly_fields = ('created_at', 'updated_at', 'completed_at')
    autocomplete_fields = ('objective',)


@admin.register(DailyTask)
class DailyTaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'member', 'date', 'status', 'priority', 'duration_label')
    list_filter = ('status', 'priority', 'date', 'member__department')
    search_fields = ('title', 'description', 'member__user__first_name')
    readonly_fields = ('created_at', 'updated_at', 'started_at', 'completed_at')
    date_hierarchy = 'date'
    autocomplete_fields = ('member', 'roadmap_item')


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ('member', 'period_type', 'title', 'period_start', 'period_end',
                    'status')
    list_filter = ('period_type', 'status', 'period_end', 'member__department')
    search_fields = ('title', 'summary', 'achievements', 'blockers', 'decisions',
                     'member__user__first_name', 'member__user__last_name')
    readonly_fields = ('created_at', 'updated_at', 'submitted_at')
    date_hierarchy = 'period_end'
    autocomplete_fields = ('member',)
    fieldsets = (
        ('Auteur et période', {
            'fields': ('member', 'period_type', 'period_start', 'period_end')
        }),
        ('Mission ou réunion', {
            'fields': ('title', 'location', 'participants'),
            'description': "Renseignés pour un rapport de mission ou de réunion.",
        }),
        ('Contenu', {
            'fields': ('summary', 'achievements', 'blockers', 'decisions', 'next_steps')
        }),
        ('État', {'fields': ('status', 'submitted_at', 'created_at', 'updated_at')}),
    )


@admin.register(Payslip)
class PayslipAdmin(admin.ModelAdmin):
    list_display = ('member', 'month', 'base_salary', 'net_display', 'issued_at')
    list_filter = ('month', 'member__department')
    search_fields = ('member__user__first_name', 'member__user__last_name', 'notes')
    readonly_fields = ('created_at', 'updated_at', 'issued_at')
    date_hierarchy = 'month'
    autocomplete_fields = ('member',)
    fieldsets = (
        ('Bulletin', {'fields': ('member', 'month')}),
        ('Rémunération', {
            'fields': ('base_salary', 'worked_hours', 'overtime_hours',
                       'overtime_amount', 'bonuses')
        }),
        ('Retenues', {'fields': ('deductions', 'contributions')}),
        ('État', {'fields': ('notes', 'issued_at', 'created_at', 'updated_at')}),
    )

    @admin.display(description='Net à payer')
    def net_display(self, obj):
        return format_fcfa(obj.net)


@admin.register(StaffEvent)
class StaffEventAdmin(admin.ModelAdmin):
    list_display = ('member', 'kind', 'date', 'summary', 'recorded_by')
    list_filter = ('kind', 'date', 'is_paid', 'member__department')
    search_fields = ('reason', 'decision', 'member__user__first_name',
                     'member__user__last_name')
    readonly_fields = ('created_at', 'updated_at')
    date_hierarchy = 'date'
    autocomplete_fields = ('member', 'recorded_by')
    fieldsets = (
        ('Évènement', {'fields': ('member', 'kind', 'date', 'end_date')}),
        ('Mesure', {
            'fields': ('minutes', 'hours', 'is_paid'),
            'description': "Minutes pour un retard, heures pour des heures "
                           "supplémentaires, solde pour une mise à pied.",
        }),
        ('Dossier', {'fields': ('reason', 'decision', 'recorded_by')}),
        ('Suivi', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(Suggestion)
class SuggestionAdmin(admin.ModelAdmin):
    list_display = ('author', 'category', 'excerpt', 'status', 'created_at')
    list_filter = ('status', 'category', 'created_at', 'author__department')
    search_fields = ('message', 'reply', 'author__user__first_name',
                     'author__user__last_name')
    readonly_fields = ('created_at', 'updated_at', 'handled_at')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('author', 'handled_by')
    fieldsets = (
        ('Message', {'fields': ('author', 'category', 'message')}),
        ('Suite donnée', {'fields': ('status', 'reply', 'handled_by', 'handled_at')}),
        ('Suivi', {'fields': ('created_at', 'updated_at')}),
    )


@admin.register(Reaction)
class ReactionAdmin(admin.ModelAdmin):
    list_display = ('member', 'kind', 'points', 'date', 'author')
    list_filter = ('kind', 'date', 'member__department')
    search_fields = ('reason', 'member__user__first_name', 'member__user__last_name')
    readonly_fields = ('created_at',)
    date_hierarchy = 'date'
    autocomplete_fields = ('member', 'author')


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('member', 'kind', 'start_date', 'end_date', 'days_label',
                    'status', 'decided_by')
    list_filter = ('status', 'kind', 'start_date', 'member__department')
    search_fields = ('reason', 'decision', 'member__user__first_name',
                     'member__user__last_name')
    readonly_fields = ('created_at', 'updated_at', 'decided_at')
    date_hierarchy = 'start_date'
    autocomplete_fields = ('member', 'decided_by')
    fieldsets = (
        ('Demande', {
            'fields': ('member', 'kind', 'start_date', 'end_date', 'half_day',
                       'reason')
        }),
        ('Décision', {'fields': ('status', 'decision', 'decided_by', 'decided_at')}),
        ('Suivi', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Durée')
    def days_label(self, obj):
        return obj.days_label


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('member', 'date', 'check_in', 'check_out', 'duration_label',
                    'late_minutes')
    list_filter = ('date', 'member__department')
    search_fields = ('note', 'member__user__first_name', 'member__user__last_name')
    # Le retard se recalcule à l'enregistrement : le saisir n'aurait pas de sens.
    readonly_fields = ('late_minutes', 'created_at', 'updated_at')
    date_hierarchy = 'date'
    autocomplete_fields = ('member',)
    fieldsets = (
        ('Journée', {'fields': ('member', 'date', 'check_in', 'check_out')}),
        ('Mesure', {'fields': ('late_minutes', 'note')}),
        ('Suivi', {'fields': ('created_at', 'updated_at')}),
    )

    @admin.display(description='Présence')
    def duration_label(self, obj):
        return obj.duration_label
