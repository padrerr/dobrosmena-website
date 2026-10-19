from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from core import views
from core.api import (
    RegisterView, LoginView, RecoverAccountView, LogoutView, MeView, BootstrapV1View, AdminUserDetailV1View,
    CreateOrderV1View, AssignOrderV1View, CaregiverAcceptV1View,
    StartShiftV1View, CompleteShiftV1View, ReportShiftV1View,
    ReplaceOrderV1View, ResolveIncidentV1View, ProfileView, AdminSearchView,
)

urlpatterns = [
    path('', views.index),
    path('api/v1/auth/register/', RegisterView.as_view()),
    path('api/v1/auth/login/', LoginView.as_view()),
    path('api/v1/auth/recover/', RecoverAccountView.as_view()),
    path('api/v1/auth/logout/', LogoutView.as_view()),
    path('api/v1/auth/me/', MeView.as_view()),
    path('api/v1/profile/', ProfileView.as_view()),
    path('api/v1/admin/search/', AdminSearchView.as_view()),
    path('api/v1/bootstrap/', BootstrapV1View.as_view()),
    path('api/v1/admin/users/<int:user_id>/', AdminUserDetailV1View.as_view()),
    path('api/v1/orders/', CreateOrderV1View.as_view()),
    path('api/v1/orders/<int:order_id>/assign/', AssignOrderV1View.as_view()),
    path('api/v1/orders/<int:order_id>/accept/', CaregiverAcceptV1View.as_view()),
    path('api/v1/orders/<int:order_id>/start/', StartShiftV1View.as_view()),
    path('api/v1/orders/<int:order_id>/complete/', CompleteShiftV1View.as_view()),
    path('api/v1/orders/<int:order_id>/report/', ReportShiftV1View.as_view()),
    path('api/v1/orders/<int:order_id>/replace/', ReplaceOrderV1View.as_view()),
    path('api/v1/incidents/<int:incident_id>/resolve/', ResolveIncidentV1View.as_view()),
    # Legacy demo endpoints are kept temporarily so the old UI does not break during migration.
    path('api/bootstrap/', views.bootstrap),
    path('api/order/create/', views.create_order),
    path('api/order/<int:order_id>/assign/', views.assign_order),
    path('api/order/<int:order_id>/start/', views.start_shift),
    path('api/order/<int:order_id>/complete/', views.complete_shift),
    path('api/order/<int:order_id>/report/', views.report_shift),
    path('api/order/<int:order_id>/replace/', views.replace_order),
    path('api/incident/<int:incident_id>/resolve/', views.resolve_incident),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
