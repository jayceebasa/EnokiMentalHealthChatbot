import os, httpx
import json
import uuid
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .gemini_client import generate_reply, update_summary, update_memory
from .models import ChatSession, Message, UserPreference
from django.db import transaction

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8001")

def home(request):
    return render(request, "home.html")

@csrf_exempt
@require_http_methods(["POST"])
def api_chat(request):
    """API endpoint for testing Gemini + RoBERTa integration with curl"""
    try:
        data = json.loads(request.body)
        user_message = data.get('message', '')
        tone = data.get('tone')
        language = data.get('language')
        
        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)

        # Get session & prefs (anonymous if not authenticated)
        prefs = _get_or_create_preferences(request)
        session = _get_or_create_session(request)

        # Update preferences if provided
        updated = False
        if tone:
            prefs.tone = tone[:32]; updated = True
        if language:
            prefs.language = language[:8]; updated = True
        if updated:
            prefs.save()

        # Step 1: classify emotions with RoBERTa
        payload = {"text": user_message}
        response = httpx.post(f"{AI_SERVICE_URL}/predict_all", json=payload, timeout=30)
        roberta_data = response.json()
        emotions = roberta_data.get("emotions", [])

        # Step 2: use stored preferences
        preferences = {"tone": prefs.tone, "language": prefs.language}

        # Build prior history for continuity (last 12 messages)
        prior = list(session.messages.order_by('-created_at')[:12])
        prior_serialized = [
            {"role": m.sender if m.sender in ("user", "bot") else "bot", "text": getattr(m, 'plaintext', m.text)}
            for m in reversed(prior)
        ]

        # Step 3: generate a reply with Gemini (with prior context + summary)
        reply = generate_reply(
            user_message,
            emotions,
            preferences,
            history=prior_serialized,
            summary=session.summary,
            memory=session.memory,
        )

        # Persist
        with transaction.atomic():
            m_user = Message(session=session, sender="user", text=user_message, emotions=emotions)
            m_user.set_plaintext(user_message); m_user.save()
            m_bot = Message(session=session, sender="bot", text=reply)
            m_bot.set_plaintext(reply); m_bot.save()
            # Update summary every 3 user messages (approx)
            user_msg_count = session.messages.filter(sender="user").count()
            # Update summary more frequently early on (first 6 user msgs), then every 3
            if user_msg_count <= 6 or user_msg_count % 3 == 0:
                session.summary = update_summary(
                    session.summary,
                    prior_serialized + [{"role":"user","text":user_message},{"role":"bot","text":reply}],
                    user_message,
                    reply,
                )
            # Always evolve structured memory
            session.memory = update_memory(
                session.memory,
                prior_serialized + [{"role":"user","text":user_message},{"role":"bot","text":reply}],
                user_message,
                reply,
            )
            session.save(update_fields=["summary", "memory"])

        return JsonResponse({
            'user_message': user_message,
            'emotions': emotions[:5],  # Top 5 emotions
            'reply': reply,
            'session_id': session.id,
            'preferences': {"tone": prefs.tone, "language": prefs.language},
            'summary': session.summary,
            'memory': session.memory,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


@csrf_exempt
@require_http_methods(["GET"])
def api_chat_history(request):
    """Return the last N messages (default 50) for the current session.
    Works for both authenticated and anonymous users.
    """
    try:
        limit = int(request.GET.get("limit", 50))
        limit = max(1, min(limit, 200))  # clamp
        prefs = _get_or_create_preferences(request)
        session = _get_or_create_session(request)
        msgs = session.messages.order_by('-created_at')[:limit]
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
    """Return just summary + memory + preferences for current session (debug / lightweight)."""
    try:
        prefs = _get_or_create_preferences(request)
        session = _get_or_create_session(request)
        return JsonResponse({
            'session_id': session.id,
            'summary': session.summary,
            'memory': session.memory,
            'preferences': {'tone': prefs.tone, 'language': prefs.language},
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def _get_or_create_anon_id(request):
    if not request.session.get("anon_id"):
        request.session["anon_id"] = uuid.uuid4().hex[:32]
    return request.session["anon_id"]


def _get_or_create_preferences(request):
    if request.user.is_authenticated:
        prefs, _ = UserPreference.objects.get_or_create(user=request.user)
        return prefs
    anon_id = _get_or_create_anon_id(request)
    prefs, _ = UserPreference.objects.get_or_create(anon_id=anon_id, user=None)
    return prefs


def _get_or_create_session(request):
    if request.user.is_authenticated:
        session = ChatSession.objects.filter(user=request.user).order_by("-created_at").first()
        if not session:
            session = ChatSession.objects.create(user=request.user)
        return session
    anon_id = _get_or_create_anon_id(request)
    session = ChatSession.objects.filter(anon_id=anon_id).order_by("-created_at").first()
    if not session:
        session = ChatSession.objects.create(anon_id=anon_id)
    return session


def chat(request):
    prefs = _get_or_create_preferences(request)
    session = _get_or_create_session(request)

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

        # Prepare lightweight history (exclude current). Use last 12 stored messages.
        prior = list(session.messages.order_by('-created_at')[:12])
        prior_serialized = [
            {"role": m.sender if m.sender in ("user", "bot") else "bot", "text": getattr(m, 'plaintext', m.text)}
            for m in reversed(prior)
        ]

        # Step 3: generate a reply with Gemini using history + summary
        reply = generate_reply(
            user_message,
            emotions,
            preferences,
            history=prior_serialized,
            summary=session.summary,
            memory=session.memory,
        )

        # Persist messages atomically
        with transaction.atomic():
            m_user = Message(session=session, sender="user", text=user_message, emotions=emotions)
            m_user.set_plaintext(user_message); m_user.save()
            m_bot = Message(session=session, sender="bot", text=reply, emotions=None)
            m_bot.set_plaintext(reply); m_bot.save()
            user_msg_count = session.messages.filter(sender="user").count()
            if user_msg_count <= 6 or user_msg_count % 3 == 0:
                session.summary = update_summary(
                    session.summary,
                    prior_serialized + [{"role":"user","text":user_message},{"role":"bot","text":reply}],
                    user_message,
                    reply,
                )
            session.memory = update_memory(
                session.memory,
                prior_serialized + [{"role":"user","text":user_message},{"role":"bot","text":reply}],
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
        "tones": ["empathetic", "supportive", "neutral", "concise"],
        "summary": session.summary,
        "memory": session.memory,
    })
