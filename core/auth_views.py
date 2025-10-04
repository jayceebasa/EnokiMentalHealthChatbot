from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib import messages
from django import forms
from django.contrib.auth.models import User


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
            # Automatically log the user in after registration
            login(request, user)
            messages.success(request, f'Welcome, {user.username}! Your account has been created.')
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
            login(request, user)
            messages.success(request, f'Welcome back, {user.username}!')
            # Redirect to next page if specified, otherwise to chat
            next_page = request.GET.get('next', 'chat')
            return redirect(next_page)
        else:
            messages.error(request, 'Invalid username or password.')
    
    return render(request, 'login.html')


def logout_view(request):
    """Handle user logout"""
    logout(request)
    messages.success(request, 'You have been logged out successfully.')
    return redirect('login')


def anonymous_chat_view(request):
    """Redirect to chat in anonymous mode"""
    # Clear any existing authentication
    if request.user.is_authenticated:
        logout(request)
    
    # Set anonymous flag in session
    request.session['is_anonymous'] = True
    # Note: The chat page has its own ephemeral warning banner
    return redirect('chat')
