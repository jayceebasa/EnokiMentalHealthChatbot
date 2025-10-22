"""
Custom OAuth pipeline to prevent account merging/linking.

This pipeline ensures that OAuth accounts and password-based accounts
remain completely separate and never automatically link, even if they
share the same email address.
"""

from django.contrib.auth.models import User
from social_core.exceptions import AuthFailed


def prevent_account_linking(strategy, backend, details, user=None, new_user=False, *args, **kwargs):
    """
    Prevent automatic account linking/merging between OAuth and password accounts.
    
    This function runs AFTER social_user lookup, so we can check if we're about to
    create a new user or link to an existing one.
    
    This pipeline step ensures that OAuth accounts never get linked to existing 
    password accounts, even if they share the same email.
    
    If a user tries to authenticate with OAuth using an email that already exists
    in the system as a password account, they will be denied access with an error.
    """
    
    email = details.get('email', '')
    
    if not email:
        # No email provided, allow to continue
        return None
    
    # If we're creating a new user (new_user=True), check if this email
    # already belongs to a password account
    if new_user:
        try:
            existing_user = User.objects.get(email=email)
            
            # If it's a password-based account (has usable password),
            # block the OAuth login to prevent account merging
            if existing_user.has_usable_password():
                raise AuthFailed(
                    backend,
                    'An account with this email already exists. '
                    'Please log in with your email and password instead.'
                )
        except User.DoesNotExist:
            # Email doesn't exist, safe to proceed with new user creation
            pass
    
    return None
