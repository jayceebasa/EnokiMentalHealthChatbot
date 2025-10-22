"""
Custom OAuth pipeline to prevent account merging/linking.

This pipeline ensures that OAuth accounts and password-based accounts
remain completely separate and never automatically link, even if they
share the same email address.
"""

from django.contrib.auth.models import User
from social_core.exceptions import AuthFailed


def prevent_account_linking(strategy, backend, details, user=None, *args, **kwargs):
    """
    Prevent automatic account linking/merging between OAuth and password accounts.
    
    This replaces the default 'associate_user' step which would automatically link
    OAuth and password accounts if they share the same email.
    
    Security checks:
    1. If 'user' already exists and is being linked, block if it has a password
    2. If 'user' is None (new OAuth user), check if the email belongs to a password account
    """
    
    email = details.get('email', '')
    
    if not email:
        # No email provided, allow to continue
        return {}
    
    # Case 1: User already exists and is being linked
    if user:
        if user.has_usable_password():
            # This user has a password set, don't link OAuth to it
            raise AuthFailed(
                backend,
                'This email is already registered with a password. '
                'Please log in with your email and password instead.'
            )
    else:
        # Case 2: New OAuth user being created - check if email belongs to password account
        try:
            existing_user = User.objects.get(email=email)
            if existing_user.has_usable_password():
                # Email belongs to a password account, block OAuth creation
                raise AuthFailed(
                    backend,
                    'This email is already registered with a password. '
                    'Please log in with your email and password instead.'
                )
        except User.DoesNotExist:
            # Email is unique, safe to proceed
            pass
    
    # Return empty dict to continue pipeline (mimics associate_user behavior)
    return {}
