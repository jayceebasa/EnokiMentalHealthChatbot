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
    Validates before allowing account association.
    
    This runs BEFORE the standard 'associate_user' step to validate that
    we're not linking OAuth to a password account.
    
    Returns None to continue the pipeline (next step is associate_user).
    Raises AuthFailed if validation fails.
    """
    
    email = details.get('email', '')
    
    if not email:
        # No email, allow to continue
        return None
    
    # If user already exists and is being linked/associated
    if user:
        # Check if this is a password account
        if user.has_usable_password():
            raise AuthFailed(
                backend,
                'This email is already registered with a password. '
                'Please log in with your email and password instead.'
            )
    else:
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
    
    # Validation passed, continue to next pipeline step (associate_user)
    return None
