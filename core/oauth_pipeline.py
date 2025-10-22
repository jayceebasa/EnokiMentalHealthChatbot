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


def extract_username_from_email(strategy, backend, details, user=None, *args, **kwargs):
    """
    Extract a better username from email if no real name is provided.
    
    Priority:
    1. Use first_name + last_name if both exist
    2. Use fullname if it exists
    3. Use the part before @ in email
    4. Fall back to default behavior (random hash)
    """
    
    email = details.get('email', '')
    first_name = details.get('first_name', '').strip()
    last_name = details.get('last_name', '').strip()
    fullname = details.get('fullname', '').strip()
    
    # Check if we have a real name
    if first_name and last_name:
        # Combine first and last name
        username = f"{first_name.lower()}.{last_name.lower()}"
    elif fullname:
        # Use fullname, replace spaces with dots
        username = fullname.lower().replace(' ', '.')
    elif email:
        # Extract username from email (part before @)
        username = email.split('@')[0].lower()
    else:
        # No name or email, let default behavior handle it
        return None
    
    # Make sure it's a valid Django username (max 150 chars, alphanumeric + . _ -)
    # Remove invalid characters
    import re
    username = re.sub(r'[^a-z0-9._-]', '', username)
    # Limit to 150 characters
    username = username[:150]
    
    # If username is empty after cleanup, fall back to default
    if not username:
        return None
    
    # Update details so Django uses this username
    details['username'] = username
    
    return None
