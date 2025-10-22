import os
import httpx
import json
import uuid
import logging
import time
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.core.cache import cache
from .gemini_client import generate_reply, update_summary, update_memory
from .models import ChatSession, Message, UserPreference
from django.db import transaction

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001")

# Set up audit logging
audit_logger = logging.getLogger('audit')

# Rate limiting configuration
RATE_LIMIT_SECONDS = 5  # 5 seconds between messages
RATE_LIMIT_CACHE_PREFIX = "rate_limit_"


def _get_user_identifier(request):
    """Get a unique identifier for rate limiting (user ID or session key)"""
    if request.user.is_authenticated:
        return f"user_{request.user.id}"
    else:
        # Use session key for anonymous users
        if not request.session.session_key:
            request.session.create()
        return f"session_{request.session.session_key}"


def _check_consent(prefs):
    """Check if user has given data consent"""
    return getattr(prefs, 'data_consent', False)


def home(request):
    return render(request, "home.html")


@csrf_exempt
@require_http_methods(["POST"])
def api_chat(request):
    """API endpoint for testing Gemini + RoBERTa integration with curl"""
    try:
        # Rate limiting check - backend protection
        user_identifier = _get_user_identifier(request)
        rate_limit_key = f"{RATE_LIMIT_CACHE_PREFIX}{user_identifier}"
        
        last_request_time = cache.get(rate_limit_key)
        current_time = time.time()
        
        if last_request_time:
            time_since_last_request = current_time - last_request_time
            if time_since_last_request < RATE_LIMIT_SECONDS:
                remaining_time = RATE_LIMIT_SECONDS - time_since_last_request
                return JsonResponse({
                    'error': f'Rate limit exceeded. Please wait {int(remaining_time) + 1} more seconds.',
                    'retry_after': int(remaining_time) + 1
                }, status=429)
        
        # Set new rate limit timestamp
        cache.set(rate_limit_key, current_time, timeout=RATE_LIMIT_SECONDS + 1)
        
        data = json.loads(request.body)
        user_message = data.get('message', '')
        tone = data.get('tone')
        language = data.get('language')
        # Allow consent to be provided in request
        consent_given = data.get('consent')

        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)

        # Get preferences (but don't create session yet - depends on consent)
        prefs = _get_or_create_preferences(request)

        # Handle consent update if provided
        if consent_given is not None:
            prefs.data_consent = bool(consent_given)
            if consent_given:
                prefs.consent_timestamp = timezone.now()
            prefs.save()
            audit_logger.info(
                f"Consent updated: user_id={getattr(request.user, 'id', 'anon')}, consent={consent_given}")

        # Update preferences if provided
        updated = False
        if tone:
            prefs.tone = tone[:32]
            updated = True
        if language:
            prefs.language = language[:8]
            updated = True
        if updated:
            prefs.save()

        # Step 1: classify emotions with RoBERTa (no personal data stored here)
        payload = {"text": user_message}
        response = httpx.post(
            f"{AI_SERVICE_URL}/predict_all", json=payload, timeout=30)
        roberta_data = response.json()
        emotions = roberta_data.get("emotions", [])

        preferences = {"tone": prefs.tone, "language": prefs.language}

        # CONSENT CHECK - This determines everything
        if not _check_consent(prefs):
            # NO CONSENT: Use session-only history (temporary, browser-only)
            session_history = request.session.get('temp_chat_history', [])

            # Add current message to session (temporary storage)
            session_history.append({"role": "user", "text": user_message})

            # Keep only last 10 messages in session to prevent bloat
            if len(session_history) > 10:
                session_history = session_history[-10:]

            # Generate reply with session-only context
            reply = generate_reply(
                user_message,
                emotions,
                preferences,
                history=session_history,  # From browser session, not database
                summary=None,  # No stored summary
                memory=None,   # No stored memory
            )

            # Add bot reply to session
            session_history.append({"role": "bot", "text": reply})
            request.session['temp_chat_history'] = session_history

            audit_logger.info(
                f"Ephemeral chat - no consent: message_length={len(user_message)}")

            return JsonResponse({
                'user_message': user_message,
                'emotions': emotions[:5],
                'reply': reply,
                'session_id': None,  # No database session
                'preferences': preferences,
                'summary': None,
                'memory': None,
                'consent_required': True,
                'message': 'Conversation stored in browser only - enable data storage for full continuity across sessions.'
            })

        # CONSENT GIVEN: Full database functionality
        session = _get_or_create_session(request)
        
        # Validate session ownership for security
        _validate_session_ownership(session, request)

        # Check if we need to migrate session history to database
        session_history = request.session.get('temp_chat_history', [])
        if session_history:
            # Migrate previous ephemeral conversation to database
            with transaction.atomic():
                for msg in session_history:
                    m = Message(session=session,
                                sender=msg['role'], text=msg['text'])
                    m.set_plaintext(msg['text'])
                    m.save()
                # Clear session history after migration
                del request.session['temp_chat_history']
                audit_logger.info(
                    f"Migrated ephemeral history to database: session_id={session.id}, messages={len(session_history)}")

        # Build prior history for continuity (last 12 messages from THIS SESSION ONLY)
        # Double-check session ownership for security
        if request.user.is_authenticated:
            prior = list(session.messages.filter(
                session__user=request.user
            ).order_by('-created_at')[:12])
        else:
            anon_id = _get_or_create_anon_id(request)
            prior = list(session.messages.filter(
                session__anon_id=anon_id
            ).order_by('-created_at')[:12])
        
        prior_serialized = [
            {"role": m.sender if m.sender in (
                "user", "bot") else "bot", "text": getattr(m, 'plaintext', m.text)}
            for m in reversed(prior)
        ]

        # Generate reply with full context - ONLY from current session
        reply = generate_reply(
            user_message,
            emotions,
            preferences,
            history=prior_serialized,  # Guaranteed to be from current session only
            summary=session.summary,   # Session-specific summary
            memory=session.memory,     # Session-specific memory
        )

        # Persist to database
        with transaction.atomic():
            m_user = Message(session=session, sender="user",
                             text=user_message, emotions=emotions)
            m_user.set_plaintext(user_message)
            m_user.save()

            audit_logger.info(
                f"Message stored: user_id={getattr(request.user, 'id', None)}, session_id={session.id}, action=create_user_message")

            m_bot = Message(session=session, sender="bot", text=reply)
            m_bot.set_plaintext(reply)
            m_bot.save()

            audit_logger.info(
                f"Message stored: user_id={getattr(request.user, 'id', None)}, session_id={session.id}, action=create_bot_message")

            # Update summary every 3 user messages (approx)
            user_msg_count = session.messages.filter(sender="user").count()
            # Update summary more frequently early on (first 6 user msgs), then every 3
            if user_msg_count <= 6 or user_msg_count % 3 == 0:
                session.summary = update_summary(
                    session.summary,
                    prior_serialized +
                    [{"role": "user", "text": user_message},
                        {"role": "bot", "text": reply}],
                    user_message,
                    reply,
                )
            # Always evolve structured memory
            session.memory = update_memory(
                session.memory,
                prior_serialized +
                [{"role": "user", "text": user_message},
                    {"role": "bot", "text": reply}],
                user_message,
                reply,
            )
            session.save(update_fields=["summary", "memory"])

        return JsonResponse({
            'user_message': user_message,
            'emotions': emotions[:5],
            'reply': reply,
            'session_id': session.id,
            'preferences': preferences,
            'summary': session.summary,
            'memory': session.memory,
            'consent_required': False,
        })

    except Exception as e:
        audit_logger.error(f"Chat error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_chat_history(request):
    """Return the last N messages (default 50) for the current session ONLY.
    Works for both authenticated and anonymous users.
    """
    try:
        limit = int(request.GET.get("limit", 50))
        limit = max(1, min(limit, 200))  # clamp
        prefs = _get_or_create_preferences(request)
        session = _get_or_create_session(request)
        
        # Validate session ownership for security
        _validate_session_ownership(session, request)
        
        # Ensure we only get messages from THIS session and user/anon_id
        if request.user.is_authenticated:
            msgs = session.messages.filter(
                session__user=request.user
            ).order_by('-created_at')[:limit]
        else:
            anon_id = _get_or_create_anon_id(request)
            msgs = session.messages.filter(
                session__anon_id=anon_id
            ).order_by('-created_at')[:limit]
        
        serialized = [
            {
                'id': m.id,
                'sender': m.sender,
                'text': getattr(m, 'plaintext', m.text),
                'emotions': m.emotions,
                'created_at': m.created_at.isoformat(),
            } for m in msgs
        ]
        return JsonResponse({
            'session_id': session.id,
            'preferences': {'tone': prefs.tone, 'language': prefs.language},
            'messages': list(reversed(serialized)),  # chronological
            'summary': session.summary,
            'memory': session.memory,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_chat_context(request):
    """Return context and chat history - works for both consent/ephemeral modes."""
    try:
        prefs = _get_or_create_preferences(request)
        
        # Check consent status to determine what to return
        if not _check_consent(prefs):
            # NO CONSENT: Return ephemeral session history
            session_history = request.session.get('temp_chat_history', [])
            return JsonResponse({
                'session_id': None,
                'summary': None,
                'memory': None,
                'preferences': {'tone': prefs.tone, 'language': prefs.language},
                'ephemeral_history': session_history,  # Return ephemeral chat history
                'consent_required': True,
            })
        
        # CONSENT GIVEN: Return full database context
        session = _get_or_create_session(request)
        _validate_session_ownership(session, request)
        
        return JsonResponse({
            'session_id': session.id,
            'summary': session.summary,
            'memory': session.memory,
            'preferences': {'tone': prefs.tone, 'language': prefs.language},
            'consent_required': False,
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt  
@require_http_methods(["POST"])
def api_clear_ephemeral_chat(request):
    """Clear ephemeral chat history stored in session."""
    try:
        if 'temp_chat_history' in request.session:
            del request.session['temp_chat_history']
            audit_logger.info("Ephemeral chat history cleared")
        
        return JsonResponse({
            'success': True,
            'message': 'Ephemeral chat history cleared'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def _get_or_create_anon_id(request):
    if not request.session.get("anon_id"):
        request.session["anon_id"] = uuid.uuid4().hex[:32]
    return request.session["anon_id"]


def _validate_session_ownership(session, request):
    """Validate that the session belongs to the current user/anon_id.
    This ensures session isolation and prevents cross-session data leakage.
    """
    if request.user.is_authenticated:
        if session.user != request.user:
            raise ValueError(f"Session {session.id} does not belong to authenticated user {request.user.id}")
    else:
        anon_id = _get_or_create_anon_id(request)
        if session.anon_id != anon_id:
            raise ValueError(f"Session {session.id} does not belong to anonymous user {anon_id}")
    return True


def _get_or_create_preferences(request):
    if request.user.is_authenticated:
        prefs, created = UserPreference.objects.get_or_create(user=request.user)
        # Automatically enable storage consent for authenticated users if not already set
        if created and not prefs.data_consent:
            prefs.data_consent = True
            prefs.consent_timestamp = timezone.now()
            prefs.save()
            audit_logger.info(f"Auto-enabled data storage for authenticated user: {request.user.id}")
        return prefs
    anon_id = _get_or_create_anon_id(request)
    prefs, _ = UserPreference.objects.get_or_create(anon_id=anon_id, user=None)
    return prefs


def _get_or_create_session(request):
    """Get or create a chat session for the current user, ensuring proper isolation."""
    # Check if there's a current active session ID stored in the session
    current_session_id = request.session.get('current_chat_session_id')

    if current_session_id:
        try:
            if request.user.is_authenticated:
                session = ChatSession.objects.get(
                    id=current_session_id, user=request.user)
            else:
                anon_id = _get_or_create_anon_id(request)
                session = ChatSession.objects.get(
                    id=current_session_id, anon_id=anon_id)
            
            # Validate session ownership for extra security
            _validate_session_ownership(session, request)
            return session
        except (ChatSession.DoesNotExist, ValueError):
            # Current session doesn't exist or doesn't belong to user, remove from session
            if 'current_chat_session_id' in request.session:
                del request.session['current_chat_session_id']

    # No current session or it doesn't exist, get or create the most recent one
    if request.user.is_authenticated:
        session = ChatSession.objects.filter(
            user=request.user).order_by("-created_at").first()
        if not session:
            session = ChatSession.objects.create(user=request.user)
    else:
        anon_id = _get_or_create_anon_id(request)
        session = ChatSession.objects.filter(
            anon_id=anon_id).order_by("-created_at").first()
        if not session:
            session = ChatSession.objects.create(anon_id=anon_id)

    # Validate session ownership before returning
    _validate_session_ownership(session, request)
    
    # Store this session as the current active session
    request.session['current_chat_session_id'] = session.id
    return session


def chat(request):
    prefs = _get_or_create_preferences(request)
    session = _get_or_create_session(request)
    
    # Validate session ownership for security
    _validate_session_ownership(session, request)

    # Allow updating preferences (tone / language) via form
    if request.method == "POST" and request.POST.get("update_prefs"):
        prefs.tone = request.POST.get("tone", prefs.tone)[:32]
        prefs.language = request.POST.get("language", prefs.language)[:8]
        prefs.save()
        return redirect("chat")

    reply, emotions = None, []
    user_message = ""

    if request.method == "POST" and request.POST.get("message"):
        user_message = request.POST.get("message")

        # Step 1: classify emotions with RoBERTa
        payload = {"text": user_message}
        response = httpx.post(f"{AI_SERVICE_URL}/predict_all", json=payload)
        roberta_data = response.json()
        emotions = roberta_data.get("emotions", [])

        preferences = {"tone": prefs.tone, "language": prefs.language}

        # Prepare lightweight history (exclude current). Use last 12 stored messages from THIS SESSION ONLY
        # Ensure session ownership for security
        if request.user.is_authenticated:
            prior = list(session.messages.filter(
                session__user=request.user
            ).order_by('-created_at')[:12])
        else:
            anon_id = _get_or_create_anon_id(request)
            prior = list(session.messages.filter(
                session__anon_id=anon_id
            ).order_by('-created_at')[:12])
        
        prior_serialized = [
            {"role": m.sender if m.sender in (
                "user", "bot") else "bot", "text": getattr(m, 'plaintext', m.text)}
            for m in reversed(prior)
        ]

        # Step 3: generate a reply with Gemini using history + summary - ONLY from current session
        reply = generate_reply(
            user_message,
            emotions,
            preferences,
            history=prior_serialized,  # Guaranteed to be from current session only
            summary=session.summary,   # Session-specific summary
            memory=session.memory,
        )

        # Persist messages atomically
        with transaction.atomic():
            m_user = Message(session=session, sender="user",
                             text=user_message, emotions=emotions)
            m_user.set_plaintext(user_message)
            m_user.save()
            m_bot = Message(session=session, sender="bot",
                            text=reply, emotions=None)
            m_bot.set_plaintext(reply)
            m_bot.save()
            user_msg_count = session.messages.filter(sender="user").count()
            if user_msg_count <= 6 or user_msg_count % 3 == 0:
                session.summary = update_summary(
                    session.summary,
                    prior_serialized +
                    [{"role": "user", "text": user_message},
                        {"role": "bot", "text": reply}],
                    user_message,
                    reply,
                )
            session.memory = update_memory(
                session.memory,
                prior_serialized +
                [{"role": "user", "text": user_message},
                    {"role": "bot", "text": reply}],
                user_message,
                reply,
            )
            session.save(update_fields=["summary", "memory"])

    recent_messages = session.messages.all().select_related("session")[:50]

    return render(request, "chat.html", {
        "user_message": user_message,
        "emotions": emotions,
        "reply": reply,
        "messages": recent_messages,
        "preferences": prefs,
        "session": session,
        "is_authenticated": request.user.is_authenticated,
                "tones": ["empathetic", "supportive", "professional", "gentle", "casual", "batman"],
        "summary": session.summary,
        "memory": session.memory,
    })


@csrf_exempt
@require_http_methods(["POST"])
def api_new_chat(request):
    """Create a new chat session, preserving the current one in history."""
    try:
        prefs = _get_or_create_preferences(request)

        # Check consent status to handle ephemeral vs persistent sessions
        if not _check_consent(prefs):
            # NO CONSENT: Clear ephemeral history for new chat
            if 'temp_chat_history' in request.session:
                del request.session['temp_chat_history']
                audit_logger.info("Ephemeral chat history cleared for new chat")
            
            return JsonResponse({
                'session_id': None,
                'message': 'New ephemeral chat started - previous conversation cleared',
                'ephemeral_mode': True
            })
        
        # CONSENT GIVEN: Create new database session
        if request.user.is_authenticated:
            new_session = ChatSession.objects.create(user=request.user)
        else:
            anon_id = _get_or_create_anon_id(request)
            new_session = ChatSession.objects.create(anon_id=anon_id)

        # Set this new session as the current active session
        request.session['current_chat_session_id'] = new_session.id

        return JsonResponse({
            'session_id': new_session.id,
            'message': 'New chat session created successfully',
            'ephemeral_mode': False
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_chat_sessions(request):
    """Get all chat sessions for the current user/anonymous user."""
    try:
        if request.user.is_authenticated:
            sessions = ChatSession.objects.filter(
                user=request.user).order_by('-updated_at')
        else:
            anon_id = _get_or_create_anon_id(request)
            sessions = ChatSession.objects.filter(
                anon_id=anon_id).order_by('-updated_at')

        current_session = _get_or_create_session(request)

        session_list = []
        for session in sessions:
            # Get first user message for preview
            first_message = session.messages.filter(sender='user').first()
            preview = first_message.plaintext[:
                                              100] if first_message else "No messages yet"

            # Generate title from first message or use default
            title = first_message.plaintext[:50] + "..." if first_message and len(
                first_message.plaintext) > 50 else (first_message.plaintext if first_message else "New Chat")

            session_list.append({
                'id': session.id,
                'title': title,
                'preview': preview,
                'message_count': session.messages.count(),
                'created_at': session.created_at.isoformat(),
                'updated_at': session.updated_at.isoformat(),
                'is_current': session.id == current_session.id
            })

        return JsonResponse({
            'sessions': session_list,
            'current_session_id': current_session.id
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_chat_session_detail(request, session_id):
    """Get details of a specific chat session."""
    try:
        if request.user.is_authenticated:
            session = ChatSession.objects.get(id=session_id, user=request.user)
        else:
            anon_id = _get_or_create_anon_id(request)
            session = ChatSession.objects.get(id=session_id, anon_id=anon_id)

        messages = session.messages.order_by('created_at')
        message_list = []
        for msg in messages:
            message_list.append({
                'sender': msg.sender,
                'text': getattr(msg, 'plaintext', msg.text),
                'emotions': msg.emotions,
                'created_at': msg.created_at.isoformat(),

            })

        return JsonResponse({
            'session_id': session.id,
            'messages': message_list,
            'summary': session.summary,
            'memory': session.memory,
            'created_at': session.created_at.isoformat(),
            'updated_at': session.updated_at.isoformat()
        })
    except ChatSession.DoesNotExist:
        return JsonResponse({'error': 'Chat session not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_switch_session(request, session_id):
    """Switch to a specific chat session as the active session."""
    try:
        if request.user.is_authenticated:
            session = ChatSession.objects.get(id=session_id, user=request.user)
        else:
            anon_id = _get_or_create_anon_id(request)
            session = ChatSession.objects.get(id=session_id, anon_id=anon_id)

        # Set this session as the current active session
        request.session['current_chat_session_id'] = session.id

        return JsonResponse({
            'session_id': session.id,
            'message': 'Successfully switched to chat session'
        })
    except ChatSession.DoesNotExist:
        return JsonResponse({'error': 'Chat session not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["DELETE"])
def api_delete_session(request, session_id):
    """Delete a specific chat session."""
    try:
        # Get the session to delete, ensuring ownership
        if request.user.is_authenticated:
            session = ChatSession.objects.get(id=session_id, user=request.user)
        else:
            anon_id = _get_or_create_anon_id(request)
            session = ChatSession.objects.get(id=session_id, anon_id=anon_id)

        # Check if this is the current session
        current_session_id = request.session.get('current_chat_session_id')
        was_current = (session.id == current_session_id)

        # Delete the session (this will cascade delete all messages)
        session.delete()

        # If we deleted the current session, clear it from the session
        if was_current:
            if 'current_chat_session_id' in request.session:
                del request.session['current_chat_session_id']

        return JsonResponse({
            'message': 'Chat session deleted successfully',
            'was_current_session': was_current
        })
    except ChatSession.DoesNotExist:
        return JsonResponse({'error': 'Chat session not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_current_session(request):
    """Get the current active session ID for debugging."""
    try:
        session = _get_or_create_session(request)
        return JsonResponse({
            'current_session_id': session.id,
            'stored_session_id': request.session.get('current_chat_session_id'),
            'is_authenticated': request.user.is_authenticated
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_consent(request):
    """Handle consent management"""
    try:
        data = json.loads(request.body)
        consent_given = data.get('consent', False)

        # Prevent anonymous users from enabling secure storage
        if consent_given and not request.user.is_authenticated:
            return JsonResponse({
                'error': 'Authentication required',
                'message': 'You must be logged in to enable secure storage. Please create an account or log in.'
            }, status=403)

        prefs = _get_or_create_preferences(request)
        old_consent = prefs.data_consent
        prefs.data_consent = bool(consent_given)

        if consent_given:
            prefs.consent_timestamp = timezone.now()
        prefs.save()

        audit_logger.info(
            f"Consent managed: user_id={getattr(request.user, 'id', 'anon')}, old_consent={old_consent}, new_consent={consent_given}")

        # If consent was revoked, optionally clear ephemeral session data
        if old_consent and not consent_given:
            if 'temp_chat_history' in request.session:
                del request.session['temp_chat_history']
            audit_logger.info(
                f"Consent revoked - cleared ephemeral session data")

        return JsonResponse({
            'message': 'Consent updated successfully',
            'consent_status': prefs.data_consent,
            'consent_timestamp': prefs.consent_timestamp.isoformat() if prefs.consent_timestamp else None,
            'has_ephemeral_data': 'temp_chat_history' in request.session
        })

    except Exception as e:
        audit_logger.error(f"Consent management error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_consent_status(request):
    """Get current consent status"""
    try:
        prefs = _get_or_create_preferences(request)

        return JsonResponse({
            'consent_status': getattr(prefs, 'data_consent', False),
            'consent_timestamp': prefs.consent_timestamp.isoformat() if getattr(prefs, 'consent_timestamp', None) else None,
            'consent_version': getattr(prefs, 'consent_version', '1.0'),
            'has_ephemeral_data': 'temp_chat_history' in request.session,
            'ephemeral_message_count': len(request.session.get('temp_chat_history', []))
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
