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
from django.urls import path
from core.views import (
    home, chat, api_chat, api_chat_history, api_chat_context,
    api_new_chat, api_chat_sessions, api_chat_session_detail, api_switch_session, api_current_session
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home, name='home'),
    path('chat/', chat, name='chat'),
    path('api/chat/', api_chat, name='api_chat'),
    path('api/chat/history/', api_chat_sessions, name='api_chat_sessions'),  # Updated to use new function
    path('api/chat/context/', api_chat_context, name='api_chat_context'),
    path('api/chat/new/', api_new_chat, name='api_new_chat'),
    path('api/chat/session/<int:session_id>/', api_chat_session_detail, name='api_chat_session_detail'),
    path('api/chat/switch/<int:session_id>/', api_switch_session, name='api_switch_session'),
    path('api/chat/current/', api_current_session, name='api_current_session'),
]
