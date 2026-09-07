from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .auth_views import (
    ChangePasswordView, LoginView, LogoutView, ProfileView, RegisterView,
)
from .views import (
    AttendanceViewSet, DailyTaskViewSet, DashboardViewSet, LeaveRequestViewSet,
    MemberViewSet, MonthlyObjectiveViewSet, PayslipViewSet, ReportViewSet,
    RoadmapItemViewSet, StaffEventViewSet, ReactionViewSet, SuggestionViewSet,
)

router = DefaultRouter()
router.register(r'members', MemberViewSet, basename='member')
router.register(r'objectives', MonthlyObjectiveViewSet, basename='objective')
router.register(r'roadmap', RoadmapItemViewSet, basename='roadmap')
router.register(r'tasks', DailyTaskViewSet, basename='task')
router.register(r'reports', ReportViewSet, basename='report')
router.register(r'payslips', PayslipViewSet, basename='payslip')
router.register(r'staff-events', StaffEventViewSet, basename='staff-event')
router.register(r'leaves', LeaveRequestViewSet, basename='leave')
router.register(r'attendance', AttendanceViewSet, basename='attendance')
router.register(r'suggestions', SuggestionViewSet, basename='suggestion')
router.register(r'reactions', ReactionViewSet, basename='reaction')
router.register(r'dashboard', DashboardViewSet, basename='dashboard')

auth_patterns = [
    path('register/', RegisterView.as_view(), name='auth-register'),
    path('login/', LoginView.as_view(), name='auth-login'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('me/', ProfileView.as_view(), name='auth-profile'),
    path('change-password/', ChangePasswordView.as_view(), name='auth-change-password'),
]

urlpatterns = [
    path('auth/', include(auth_patterns)),
    path('', include(router.urls)),
]
