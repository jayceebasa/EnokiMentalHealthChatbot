import os, httpx
import json
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from .gemini_client import generate_reply

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
        
        if not user_message:
            return JsonResponse({'error': 'Message is required'}, status=400)

        # Step 1: classify emotions with RoBERTa
        payload = {"text": user_message}
        response = httpx.post(f"{AI_SERVICE_URL}/predict_all", json=payload, timeout=30)
        roberta_data = response.json()
        emotions = roberta_data.get("emotions", [])

        # Step 2: hardcoded preferences for now
        preferences = {"tone": "empathetic", "language": "en"}

        # Step 3: generate a reply with Gemini
        reply = generate_reply(user_message, emotions, preferences)

        return JsonResponse({
            'user_message': user_message,
            'emotions': emotions[:5],  # Top 5 emotions
            'sarcasm': roberta_data.get('sarcasm'),
            'sarcasm_score': roberta_data.get('sarcasm_score'),
            'reply': reply,
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def chat(request):
    reply, emotions, sarcasm, sarcasm_score = None, [], None, None
    user_message = ""

    if request.method == "POST":
        user_message = request.POST.get("message")

        # Step 1: classify emotions with RoBERTa
        payload = {"text": user_message}
        response = httpx.post(f"{AI_SERVICE_URL}/predict_all", json=payload)
        roberta_data = response.json()
        emotions = roberta_data.get("emotions", [])
        sarcasm = roberta_data.get("sarcasm", "not_sarcastic")
        sarcasm_score = roberta_data.get("sarcasm_score", 0.0)

        # Step 2: hardcoded preferences for now (later we’ll use User/session)
        preferences = {"tone": "empathetic", "language": "en"}

        # Step 3: generate a reply with Gemini
        reply = generate_reply(user_message, emotions, preferences)

    return render(request, "chat.html", {
        "user_message": user_message,
        "emotions": emotions,
        "reply": reply,
        "sarcasm": sarcasm,
        "sarcasm_score": sarcasm_score,
    })
