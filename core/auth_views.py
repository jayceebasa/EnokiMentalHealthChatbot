from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django import forms
from django.contrib.auth.models import User
from django.contrib.messages import constants as messages_constants
from .models import UserPreference, ChatSession


def _transfer_anonymous_consent(request, user):
    """Transfer consent from anonymous session to authenticated user"""
    try:
        # Get or create user preferences FIRST to ensure it exists
        user_prefs, created = UserPreference.objects.get_or_create(user=user)
        
        # Check for pending anonymous migration first (comes from the save flow)
        pending_migration = request.session.get('pending_anon_migration')
        if pending_migration:
            anon_id = pending_migration.get('anon_id')
            # Clear the pending migration flag
            del request.session['pending_anon_migration']
        else:
            # Fall back to regular anon_id from session
            anon_id = request.session.get('anon_id')
        
        if not anon_id:
            return
        
        # Get anonymous preferences
        anon_prefs = UserPreference.objects.filter(anon_id=anon_id, user=None).first()
        if anon_prefs:
            # Transfer all preferences from anonymous to authenticated
            # Always transfer tone and language
            user_prefs.tone = anon_prefs.tone
            user_prefs.language = anon_prefs.language
            
            # Transfer consent if it was set (True or False, but not default)
            if anon_prefs.data_consent or anon_prefs.consent_timestamp:
                user_prefs.data_consent = anon_prefs.data_consent
                user_prefs.consent_timestamp = anon_prefs.consent_timestamp
                user_prefs.consent_version = anon_prefs.consent_version
            
            user_prefs.save()
            
            # Optionally delete the anonymous preferences
            # anon_prefs.delete()
        
        # Transfer anonymous chat sessions to the authenticated user
        _transfer_anonymous_chat_sessions(anon_id, user)
    except Exception as e:
        # Log error but don't break the login flow
        pass


def _transfer_anonymous_chat_sessions(anon_id, user):
    """Transfer all anonymous chat sessions to the authenticated user"""
    try:
        # Find all chat sessions with this anon_id
        anonymous_sessions = ChatSession.objects.filter(anon_id=anon_id, user=None)
        
        if anonymous_sessions.exists():
            # Transfer all anonymous sessions to the user
            anonymous_sessions.update(user=user, anon_id=None)
            print(f"Transferred {anonymous_sessions.count()} anonymous chat sessions to user {user.id}")
    except Exception as e:
        print(f"Error transferring chat sessions: {e}")
        pass


class CustomUserCreationForm(UserCreationForm):
    """Custom registration form with optional first name field"""
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'first_name',
            'placeholder': 'Enter your name (optional)'
        })
    )
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'id': 'username',
                'placeholder': 'Choose a username'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'form-control',
            'id': 'password1',
            'placeholder': 'Create a password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'form-control',
            'id': 'password2',
            'placeholder': 'Confirm your password'
        })


def register_view(request):
    """Handle user registration"""
    if request.user.is_authenticated:
        return redirect('chat')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            
            # Transfer anonymous consent if it exists
            _transfer_anonymous_consent(request, user)
            
            # Automatically log the user in after registration with explicit backend
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome, {user.username}! Your account has been created.', extra_tags='success')
            return redirect('chat')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'register.html', {'form': form})


def login_view(request):
    """Handle user login"""
    if request.user.is_authenticated:
        return redirect('chat')
    
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Transfer anonymous consent if it exists
            _transfer_anonymous_consent(request, user)
            
            # Log in with explicit backend
            login(request, user, backend='django.contrib.auth.backends.ModelBackend')
            messages.success(request, f'Welcome back, {user.username}!', extra_tags='success')
            # Redirect to next page if specified, otherwise to chat
            next_page = request.GET.get('next', 'chat')
            return redirect(next_page)
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')


def logout_view(request):
    """Handle user logout"""
    logout(request)
    # Clear the session to remove any cached user data
    request.session.flush()
    # Clear all messages from storage
    storage = messages.get_messages(request)
    storage.used = True
    # Add fresh logout message
    messages.success(request, 'You have been logged out successfully.', extra_tags='success')
    return redirect('login')


def anonymous_chat_view(request):
    """Redirect to chat in anonymous mode"""
    # Clear any existing authentication
    if request.user.is_authenticated:
        logout(request)
    
    # Set anonymous flag in session
    request.session['is_anonymous'] = True
    # Note: The chat page has its own anonymous warning banner
    return redirect('chat')
