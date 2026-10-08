from django.urls import path

from . import views

urlpatterns = [
    path('auth/register', views.RegisterView.as_view(), name='auth-register'),
    path('auth/confirm-email', views.ConfirmEmailView.as_view(), name='auth-confirm-email'),
    path('auth/resend-confirmation', views.ResendConfirmationView.as_view(), name='auth-resend-confirmation'),
    path('auth/login', views.LoginView.as_view(), name='auth-login'),
    path('auth/refresh', views.RefreshView.as_view(), name='auth-refresh'),
    path('auth/logout', views.LogoutView.as_view(), name='auth-logout'),
    path('auth/confirm-email-change', views.ConfirmEmailChangeView.as_view(), name='auth-confirm-email-change'),
    path('me', views.MeView.as_view(), name='me'),
    path('me/email', views.ChangeEmailView.as_view(), name='me-email'),
    path('me/password', views.ChangePasswordView.as_view(), name='me-password'),
]
