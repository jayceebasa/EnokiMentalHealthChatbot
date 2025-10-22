"""
URL configuration for enoki project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from core.views import (
    home, chat, api_chat, api_chat_history, api_chat_context,
    api_new_chat, api_chat_sessions, api_chat_session_detail, api_switch_session, api_current_session,
    api_consent, api_consent_status, api_clear_anonymous_chat, api_delete_session
)
from core.auth_views import register_view, login_view, logout_view, anonymous_chat_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', login_view, name='home'),  # Redirect home to login
    path('login/', login_view, name='login'),
    path('register/', register_view, name='register'),
    path('logout/', logout_view, name='logout'),
    path('anonymous/', anonymous_chat_view, name='anonymous_chat'),
    path('oauth/', include('social_django.urls', namespace='social')),  # OAuth URLs
    path('chat/', chat, name='chat'),
    path('api/chat/', api_chat, name='api_chat'),
    path('api/chat/history/', api_chat_sessions, name='api_chat_sessions'),  # Updated to use new function
    path('api/chat/context/', api_chat_context, name='api_chat_context'),
    path('api/chat/new/', api_new_chat, name='api_new_chat'),
    path('api/chat/session/<int:session_id>/', api_chat_session_detail, name='api_chat_session_detail'),
    path('api/chat/switch/<int:session_id>/', api_switch_session, name='api_switch_session'),
    path('api/chat/delete/<int:session_id>/', api_delete_session, name='api_delete_session'),
    path('api/chat/current/', api_current_session, name='api_current_session'),
    path('api/consent/', api_consent, name='api_consent'),
    path('api/consent/status/', api_consent_status, name='api_consent_status'),
    path('api/chat/clear-anonymous/', api_clear_anonymous_chat, name='api_clear_anonymous_chat'),
    path('api/clear/anonymous/', api_clear_anonymous_chat, name='api_clear_anonymous_chat_alt'),  # Alternative path for frontend compatibility
]
