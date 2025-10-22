"""
Custom OAuth pipeline to prevent account merging/linking.

This pipeline ensures that OAuth accounts and password-based accounts
remain completely separate and never automatically link, even if they
share the same email address.
"""

from django.contrib.auth.models import User
from social_core.exceptions import AuthFailed
from social_core.pipeline.social_auth import associate_user as default_associate_user


def prevent_account_linking(strategy, backend, details, user=None, *args, **kwargs):
    """
    Validates before allowing account association.
    
    Replaces the default 'associate_user' step with security checks.
    Only allows linking if:
    1. It's a new OAuth-only user (user is None)
    2. It's linking to a user that has NO password (pure OAuth user)
    
    Blocks:
    - Creating new OAuth account with email that belongs to password account
    - Linking OAuth to existing password account
    """
    
    email = details.get('email', '')
    
    if not email:
        # No email, let default behavior handle it
        return default_associate_user(strategy, backend, details, user, *args, **kwargs)
    
    # If user already exists and is being linked/associated
    if user:
        # Check if this is a password account
        if user.has_usable_password():
            raise AuthFailed(
                backend,
                'This email is already registered with a password. '
                'Please log in with your email and password instead.'
            )
        # Safe to associate - it's a pure OAuth account
        return default_associate_user(strategy, backend, details, user, *args, **kwargs)
    
    # User is None - about to create new account
    # Check if email already belongs to a password account
    try:
        existing_user = User.objects.get(email=email)
        if existing_user.has_usable_password():
            # Email belongs to password account, block OAuth creation
            raise AuthFailed(
                backend,
                'This email is already registered with a password. '
                'Please log in with your email and password instead.'
            )
    except User.DoesNotExist:
        # Email is unique, safe to proceed
        pass
    
    # No conflicts, use default associate behavior
    return default_associate_user(strategy, backend, details, user, *args, **kwargs)
