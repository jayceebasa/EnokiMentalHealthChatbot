"""
Custom OAuth pipeline to prevent account merging/linking.

This pipeline ensures that OAuth accounts and password-based accounts
remain completely separate and never automatically link, even if they
share the same email address.
"""

from django.contrib.auth.models import User
from social_core.exceptions import AuthFailed


def prevent_account_linking(backend, uid, user=None, *args, **kwargs):
    """
    Prevent automatic account linking/merging between OAuth and password accounts.
    
    This pipeline step ensures that:
    1. OAuth accounts never get linked to existing password accounts
    2. OAuth accounts never get linked to existing password accounts by email
    3. Each authentication method gets its own user account
    
    If a user tries to authenticate with OAuth using an email that already exists
    in the system as a password account, they will be denied access and shown an error.
    
    This is the safest approach: it prevents any accidental or malicious account merging.
    """
    
    # Get the email from social auth details
    details = kwargs.get('details', {})
    email = details.get('email', '')
    
    if not email:
        # No email provided, allow to continue
        return None
    
    # Check if this email already exists as a password-based account
    # (accounts created with username/password, not OAuth)
    try:
        existing_user = User.objects.get(email=email)
        
        # Email exists in database. Check if this is a password account or OAuth account
        # If it's a password account (has usable password) AND we're trying to OAuth login,
        # we block it to prevent account merging
        
        if existing_user.has_usable_password():
            # This is a password-based account, don't link OAuth to it
            raise AuthFailed(
                backend,
                'An account with this email already exists. '
                'Please log in with your email and password instead. '
                'If you forgot your password, use the password reset option.'
            )
        
        # If account exists but has no usable password (pure OAuth account),
        # the normal pipeline will handle re-authentication to same account
        
    except User.DoesNotExist:
        # Email doesn't exist, safe to proceed
        pass
    
    return None


def prevent_new_user_from_oauth_duplicate_email(strategy, details, user=None, *args, **kwargs):
    """
    Additional safeguard: if somehow a new user creation is attempted with an email
    that belongs to a password account, block it.
    
    This is a second layer of protection.
    """
    
    email = details.get('email', '')
    
    if not email:
        return None
    
    # Only check if no user is currently being created/logged in
    if user is None:
        try:
            existing_user = User.objects.get(email=email)
            
            if existing_user.has_usable_password():
                raise AuthFailed(
                    'oauth',
                    'This email is already registered. Please use your password to log in.'
                )
        except User.DoesNotExist:
            pass
    
    return None
