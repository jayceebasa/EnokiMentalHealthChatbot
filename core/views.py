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
from django.db.models import Prefetch
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
                f"Anonymous chat - no consent: message_length={len(user_message)}")

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
            # Migrate previous anonymous conversation to database
            with transaction.atomic():
                for msg in session_history:
                    m = Message(session=session,
                                sender=msg['role'], text=msg['text'])
                    m.set_plaintext(msg['text'])
                    m.save()
                # Clear session history after migration
                del request.session['temp_chat_history']
                audit_logger.info(
                    f"Migrated anonymous history to database: session_id={session.id}, messages={len(session_history)}")

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
            
            # Invalidate chat sessions cache after saving messages
            if request.user.is_authenticated:
                cache.delete(f"chat_sessions_{request.user.id}")
            else:
                anon_id = _get_or_create_anon_id(request)
                cache.delete(f"chat_sessions_anon_{anon_id}")

            # Update summary every 3 user messages (approx)
            # Use count in memory instead of database query for efficiency
            user_msg_count = len([m for m in session.messages.all() if m.sender == "user"])
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
    """Return context and chat history - works for both consent/anonymous modes."""
    try:
        prefs = _get_or_create_preferences(request)
        
        # Check consent status to determine what to return
        if not _check_consent(prefs):
            # NO CONSENT: Return anonymous session history
            session_history = request.session.get('temp_chat_history', [])
            return JsonResponse({
                'session_id': None,
                'summary': None,
                'memory': None,
                'preferences': {'tone': prefs.tone, 'language': prefs.language},
                'anonymous_history': session_history,  # Return anonymous chat history
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
def api_clear_anonymous_chat(request):
    """Clear anonymous chat history stored in session."""
    try:
        if 'temp_chat_history' in request.session:
            del request.session['temp_chat_history']
            audit_logger.info("Anonymous chat history cleared")
        
        return JsonResponse({
            'success': True,
            'message': 'Anonymous chat history cleared'
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
    # Try cache first
    if request.user.is_authenticated:
        cache_key = f"user_prefs_{request.user.id}"
        prefs = cache.get(cache_key)
        if prefs:
            return prefs
        
        prefs, created = UserPreference.objects.get_or_create(user=request.user)
        # Automatically enable storage consent for authenticated users if not already set
        if created and not prefs.data_consent:
            prefs.data_consent = True
            prefs.consent_timestamp = timezone.now()
            prefs.save()
            audit_logger.info(f"Auto-enabled data storage for authenticated user: {request.user.id}")
        
        # Cache for 1 hour
        cache.set(cache_key, prefs, timeout=3600)
        return prefs
    
    # For anonymous users, use session-based caching
    anon_id = _get_or_create_anon_id(request)  # Get once, use twice
    cache_key = f"anon_prefs_{anon_id}"
    prefs = cache.get(cache_key)
    if prefs:
        return prefs
    
    prefs, _ = UserPreference.objects.get_or_create(anon_id=anon_id, user=None)
    
    # Cache for 1 hour
    cache.set(cache_key, prefs, timeout=3600)
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
        try:
            prefs.tone = request.POST.get("tone", prefs.tone)[:32]
            prefs.language = request.POST.get("language", prefs.language)[:8]
            prefs.save()
            
            # Clear cache to ensure fresh preferences are loaded
            if request.user.is_authenticated:
                cache_key = f"user_prefs_{request.user.id}"
                cache.delete(cache_key)
            else:
                anon_id = request.session.get('anon_id')
                if anon_id:
                    cache_key = f"anon_prefs_{anon_id}"
                    cache.delete(cache_key)
            
            # Check if this is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'success': True, 'message': 'Preferences updated'})
            else:
                return redirect("chat")
        except Exception as e:
            audit_logger.error(f"Error updating preferences: {str(e)}")
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({'error': 'Failed to update preferences'}, status=500)
            else:
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
            # Use count in memory instead of database query for efficiency
            user_msg_count = len([m for m in session.messages.all() if m.sender == "user"])
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
    
    # In anonymous mode (no consent), don't show database messages server-side
    # Messages are stored in browser session instead and managed client-side
    if not _check_consent(prefs):
        recent_messages = []

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

        # Check consent status to handle anonymous vs persistent sessions
        if not _check_consent(prefs):
            # NO CONSENT: Clear anonymous history for new chat
            if 'temp_chat_history' in request.session:
                del request.session['temp_chat_history']
                audit_logger.info("Anonymous chat history cleared for new chat")
            
            return JsonResponse({
                'session_id': None,
                'message': 'New anonymous chat started - previous conversation cleared',
                'anonymous_mode': True
            })
        
        # CONSENT GIVEN: Create new database session
        if request.user.is_authenticated:
            new_session = ChatSession.objects.create(user=request.user)
            # Invalidate chat sessions cache
            cache.delete(f"chat_sessions_{request.user.id}")
        else:
            anon_id = _get_or_create_anon_id(request)
            new_session = ChatSession.objects.create(anon_id=anon_id)
            # Invalidate chat sessions cache
            cache.delete(f"chat_sessions_anon_{anon_id}")

        # Set this new session as the current active session
        request.session['current_chat_session_id'] = new_session.id

        return JsonResponse({
            'session_id': new_session.id,
            'message': 'New chat session created successfully',
            'anonymous_mode': False
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_chat_sessions(request):
    """Get all chat sessions for the current user/anonymous user - with caching"""
    try:
        # Try cache first for performance
        if request.user.is_authenticated:
            cache_key = f"chat_sessions_{request.user.id}"
        else:
            cache_key = f"chat_sessions_anon_{_get_or_create_anon_id(request)}"
        
        cached_sessions = cache.get(cache_key)
        if cached_sessions:
            return JsonResponse(cached_sessions)
        
        # Use prefetch_related to batch fetch all messages in one query
        messages_prefetch = Prefetch('messages')
        
        if request.user.is_authenticated:
            sessions = ChatSession.objects.filter(
                user=request.user).prefetch_related(
                messages_prefetch).order_by('-updated_at')
        else:
            anon_id = _get_or_create_anon_id(request)
            sessions = ChatSession.objects.filter(
                anon_id=anon_id).prefetch_related(
                messages_prefetch).order_by('-updated_at')

        try:
            current_session = _get_or_create_session(request)
            current_session_id = current_session.id if current_session else None
        except Exception as e:
            audit_logger.error(f"Error getting current session in api_chat_sessions: {e}")
            current_session_id = None

        session_list = []
        for idx, session in enumerate(sessions):
            try:
                # Get first user message for preview from prefetched data (no database hit)
                all_messages = list(session.messages.all())
                first_user_message = next(
                    (m for m in all_messages if m.sender == 'user'), None
                )
                
                # LAZY DECRYPTION: Only decrypt first 10 sessions for performance
                # Others will be decrypted on-demand when user clicks them
                if first_user_message:
                    if idx < 10:  # Decrypt first 10 immediately
                        try:
                            plaintext = first_user_message.plaintext
                        except Exception as e:
                            plaintext = first_user_message.text[:100]  # Fallback to encrypted text
                            audit_logger.warning(f"Error decrypting message {first_user_message.id}: {e}")
                        
                        preview = plaintext[:100]
                        title = plaintext[:50] + "..." if len(plaintext) > 50 else plaintext
                    else:
                        # For sessions beyond 10, use encrypted text for now, decrypt on-demand
                        preview = first_user_message.text[:100] if first_user_message.text else "[Encrypted Message]"
                        title = "[Click to load preview]"
                else:
                    preview = "No messages yet"
                    title = "New Chat"

                session_list.append({
                    'id': session.id,
                    'title': title,
                    'preview': preview,
                    'message_count': len(all_messages),  # Use prefetched data instead of count()
                    'created_at': session.created_at.isoformat(),
                    'updated_at': session.updated_at.isoformat(),
                    'is_current': session.id == current_session_id if current_session_id else False,
                    'needs_decryption': idx >= 10 and first_user_message is not None  # Flag for frontend
                })
            except Exception as e:
                audit_logger.error(f"Error processing session {session.id}: {e}")
                continue

        response_data = {
            'sessions': session_list,
            'current_session_id': current_session_id
        }
        
        # Cache for 10 seconds to handle rapid page opens but stay fresh for new messages
        cache.set(cache_key, response_data, timeout=10)
        
        return JsonResponse(response_data)
    except Exception as e:
        audit_logger.error(f"Error in api_chat_sessions: {e}", exc_info=True)
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

        # Invalidate caches when consent changes
        if request.user.is_authenticated:
            cache.delete(f"user_prefs_{request.user.id}")
            cache.delete(f"consent_status_{request.user.id}")
        else:
            anon_id = _get_or_create_anon_id(request)
            cache.delete(f"anon_prefs_{anon_id}")
            cache.delete(f"consent_status_anon_{anon_id}")

        audit_logger.info(
            f"Consent managed: user_id={getattr(request.user, 'id', 'anon')}, old_consent={old_consent}, new_consent={consent_given}")

        # If consent was revoked, optionally clear anonymous session data
        if old_consent and not consent_given:
            if 'temp_chat_history' in request.session:
                del request.session['temp_chat_history']
            audit_logger.info(
                f"Consent revoked - cleared anonymous session data")

        return JsonResponse({
            'message': 'Consent updated successfully',
            'consent_status': prefs.data_consent,
            'consent_timestamp': prefs.consent_timestamp.isoformat() if prefs.consent_timestamp else None,
            'has_anonymous_data': 'temp_chat_history' in request.session
        })

    except Exception as e:
        audit_logger.error(f"Consent management error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_consent_status(request):
    """Get current consent status - cached for 30 minutes"""
    try:
        # Try cache first for performance
        if request.user.is_authenticated:
            cache_key = f"consent_status_{request.user.id}"
        else:
            cache_key = f"consent_status_anon_{_get_or_create_anon_id(request)}"
        
        cached_response = cache.get(cache_key)
        if cached_response:
            return JsonResponse(cached_response)
        
        prefs = _get_or_create_preferences(request)

        response_data = {
            'consent_status': getattr(prefs, 'data_consent', False),
            'consent_timestamp': prefs.consent_timestamp.isoformat() if getattr(prefs, 'consent_timestamp', None) else None,
            'consent_version': getattr(prefs, 'consent_version', '1.0'),
            'has_anonymous_data': 'temp_chat_history' in request.session,
            'anonymous_message_count': len(request.session.get('temp_chat_history', []))
        }
        
        # Cache for 30 minutes
        cache.set(cache_key, response_data, timeout=1800)
        
        return JsonResponse(response_data)

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
