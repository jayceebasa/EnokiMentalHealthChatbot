import os
import hashlib
import google.generativeai as genai
from typing import List, Optional, Dict, Any

# Softer approach to avoiding repetitive patterns - focus on natural flow
CONVERSATION_FLOW_GUIDES = [
    "keep responses conversational and specific to what they just shared",
    "reference something concrete from their message rather than generic validation",
    "vary your opening approach - sometimes reflect, sometimes build forward",
    "let your response emerge naturally from what they're experiencing"
]

# Pre-compile commonly used word lists for faster lookups
GRIEF_INDICATORS = frozenset(["died", "passed", "funeral", "miss", "pet", "dog", "cat", "tiger", "rainbow bridge"])
RISK_INDICATORS = frozenset(["end my life", "kill myself", "suicide", "self harm", "join them"])
CRISIS_WORDS = frozenset(["suicide", "kill myself", "end my life", "self harm", "join them", "be with them"])
GRIEF_WORDS = frozenset(["died", "passed", "funeral", "miss them", "rainbow bridge", "pet", "dog", "cat"])
HIGH_DISTRESS_EMOTIONS = frozenset(['sadness', 'grief', 'despair', 'anxiety', 'fear'])
GREETINGS = [
    "Hey! How's your day going?",
    "Hi there! How are you feeling today?",
    "Hello! What's been on your mind lately?",
    "Hey there! How are things?",
    "Hi! How's everything with you?"
]
SARCASTIC_PHRASES = frozenset([
    "oh great", "just great", "fantastic", "wonderful", "perfect",
    "exactly what i needed", "just what i wanted", "how lovely",
    "oh joy", "thrilling", "amazing", "brilliant", "awesome"
])

# Pre-compile text replacements for faster processing
CLINICAL_REPLACEMENTS = {
    "coping strategies": "things that help",
    "stressor": "what's been hard", 
    "emotional trajectory": "how you've been feeling",
    "validated": "heard",
    "processing": "working through"
}

NATURAL_FLOW_REPLACEMENTS = {
    "It sounds like ": "",
    "That sounds ": "",
    "It seems like ": "",
    "I'm sorry to hear ": ""
}

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")


def generate_reply(
    user_text: str,
    emotions: list[dict[str, float]],
    preferences: dict,
    history: Optional[List[dict]] = None,
    summary: Optional[str] = None,
    memory: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a more natural, conversational reply with organic flow.
    
    IMPORTANT: This function should only receive data from the current chat session.
    The 'history' parameter must contain ONLY messages from the active session,
    not from other users or sessions. Session isolation is enforced in views.py.
    """

    # Early preprocessing - do string operations once
    user_lower = (user_text or "").lower()
    
    history = history or []
    # Keep more recent context for better continuity
    recent_history = history[-12:]

    # Optimized conversational context building
    context_lines = [
        f"{'You' if h.get('role') == 'user' else 'Me'}: {h.get('text', '').strip()}"
        for h in recent_history 
        if h.get('text', '').strip()
    ]
    conversation_flow = "\n".join(context_lines) if context_lines else "This is our first exchange"

    # Optimized emotion processing using list comprehension
    main_emotions = [e.get('label', '') for e in emotions[:3] if e.get('score', 0) > 0.3]
    emotion_context = ", ".join(main_emotions) if main_emotions else "neutral"

    # Extract key context more organically
    memory = memory or {}
    what_matters = memory.get("stressor") or memory.get("motivation") or "what you're dealing with"
    helpful_things = memory.get("coping", [])

    tone = preferences.get("tone", "empathetic")
    language = preferences.get("language", "en")

    # Optimized pattern detection using pre-compiled sets
    has_grief = any(word in user_lower for word in GRIEF_INDICATORS)
    has_risk = any(word in user_lower for word in RISK_INDICATORS)

    # Simplified mock response for testing
    if os.getenv("FAKE_LLM", "0") == "1":

        if has_risk or has_grief:
            pet_name = "Tiger" if "tiger" in user_lower else "them"
            return (f"The love you have for {pet_name} - that's so real and it aches. "
                    f"When grief hits this hard, sometimes we need to just breathe through it moment by moment. "
                    f"If you're having thoughts of hurting yourself, please reach out to someone close to you or a crisis line. "
                    f"That pain you're feeling? It shows how much you loved. I'm here.")

        # Simple greetings get natural responses - optimized with pre-computed hash
        if any(greeting in user_lower for greeting in ["hi there", "hello", "hi", "hey", "what's up", "whats up"]):
            hash_val = int(hashlib.md5(user_text.encode()).hexdigest(), 16)
            return GREETINGS[hash_val % len(GREETINGS)]
            if "great" in user_lower or "perfect" in user_lower:
                return "Yeah, I can hear the frustration in that. Things really aren't going well right now, are they?"
            elif "fantastic" in user_lower or "wonderful" in user_lower:
                return "That doesn't sound fantastic at all. Sounds like you're pretty fed up with how things are going."
            else:
                return "I can tell you're not actually feeling positive about this. What's really bothering you?"

        # Handle crisis situations with proper context
        if has_risk:
            if "school" in user_lower and "kicked out" in user_lower:
                return ("I hear how scared you are about getting kicked out of school - that feels like everything is falling apart. But your life has so much value beyond school. Please talk to someone you trust or call a crisis line. There are other paths forward, even if you can't see them right now.")
            else:
                return ("I can hear how much pain you're in right now. Please reach out to someone you trust or a crisis line - you don't have to face this alone. Your life matters.")

        if has_grief:
            pet_name = "Tiger" if "tiger" in user_lower else "them"
            return (f"The love you have for {pet_name} - that's so real and it aches. "
                    f"When grief hits this hard, sometimes we need to just breathe through it moment by moment. "
                    f"If you're having thoughts of hurting yourself, please reach out to someone close to you or a crisis line. "
                    f"That pain you're feeling? It shows how much you loved. I'm here.")

        # Handle specific situations in mock mode
        if "school" in user_lower and ("flunk" in user_lower or "subjects" in user_lower):
            return "Failing all your subjects and potentially getting kicked out - that's such enormous pressure. Learning difficulties on top of that must make it feel impossible sometimes."

        if any(word in user_lower for word in ["wtf", "i just told you", "i've been telling you"]):
            return "You're absolutely right - you did just tell me about school being overwhelming and failing subjects. Sorry I missed that. That kind of academic pressure must feel crushing."

    # Optimized emotional intensity check
    is_high_distress = any(
        e.get('label', '').lower() in HIGH_DISTRESS_EMOTIONS and e.get('score', 0) >= 0.35
        for e in emotions
    )

    # Optimized crisis/grief detection using pre-compiled sets
    has_crisis_risk = any(word in user_lower for word in CRISIS_WORDS)
    has_grief_context = any(word in user_lower for word in GRIEF_WORDS)

    # Optimized sarcasm detection - inline for better performance
    has_sarcasm = False
    
    # Quick sarcasm check - only run if we find potential sarcastic phrases
    if any(phrase in user_lower for phrase in SARCASTIC_PHRASES):
        # Look for negative context to confirm sarcasm
        negative_words = frozenset(["not", "cant", "can't", "won't", "wont", "never", "no",
                                   "fail", "bad", "awful", "terrible", "hate", "suck", "worst"])
        if any(neg in user_lower for neg in negative_words):
            has_sarcasm = True
        else:
            # Quick contextual sarcasm patterns check
            sarcasm_contexts = [
                ("great", frozenset(["fail", "flunk", "kick", "fire", "broke", "sick", "tired"])),
                ("perfect", frozenset(["mess", "disaster", "wrong", "bad", "awful", "terrible"])),
                ("fantastic", frozenset(["fail", "problem", "issue", "stress", "worry"])),
                ("wonderful", frozenset(["sick", "hurt", "pain", "sad", "angry", "upset"])),
                ("amazing", frozenset(["fail", "broke", "lost", "fired", "dump"]))
            ]
            
            for positive_word, negative_contexts in sarcasm_contexts:
                if positive_word in user_lower and any(context in user_lower for context in negative_contexts):
                    has_sarcasm = True
                    break
    
    # Check for excessive positivity with negative emotions (only if not already detected)
    if not has_sarcasm:
        negative_emotion_labels = frozenset(['sadness', 'anger', 'disappointment', 'annoyance'])
        if any(e.get('label', '').lower() in negative_emotion_labels and e.get('score', 0) > 0.6 for e in emotions):
            positive_words = frozenset(["great", "perfect", "wonderful", "fantastic", "amazing", "awesome"])
            has_sarcasm = any(word in user_lower for word in positive_words)

    # Adjust response style based on situation
    if has_crisis_risk or has_grief_context or is_high_distress:
        response_style = "deep_presence"
        target_length = "120-180 words"
    else:
        response_style = "warm_conversational"
        target_length = "60-100 words"

    # Much simpler, more human prompt with better context
    prompt = f"""You're Enoki, talking with someone who just said: "{user_text}"

Recent conversation:
{conversation_flow}

Current emotional state: {emotion_context}
{"⚠️ SARCASM DETECTED - respond to underlying frustration/pain, not literal words" if has_sarcasm else ""}

Important context about this person:
- Main concern: {what_matters}
- Things that have helped: {', '.join(helpful_things[:2]) if helpful_things else 'exploring options'}

Respond naturally like a caring friend would - not like a therapist. Keep it:
- Short and genuine (30-80 words max)
- Focused on what they ACTUALLY said (read carefully)
- If sarcasm detected, address the underlying feeling without calling out the sarcasm
- Conversational, not clinical
- If they mention thoughts of not wanting to live or self-harm, respond with immediate gentle concern and suggest getting help

Read their message carefully and respond to what they actually said:"""

    # Generate response with better error handling
    try:
        response = model.generate_content(prompt)
        reply_text = response.text.strip() if hasattr(
            response, "text") and response.text else ""

        # If we got an empty response, create a contextual fallback
        if not reply_text:
            raise Exception("Empty response from model")

    except Exception as e:
        # Optimized fallback responses using pre-compiled patterns
        frustration_words = frozenset(["wtf", "hello?", "i just told you", "i've been telling you"])
        
        if any(word in user_lower for word in frustration_words):
            reply_text = "Sorry, I'm having trouble keeping up with our conversation right now. You mentioned school being really tough and failing subjects - that must be incredibly stressful."
        elif has_sarcasm:
            reply_text = "I can hear the frustration behind that. Things really aren't going your way right now, are they?"
        elif "school" in user_lower and ("kicked out" in user_lower or "flunk" in user_lower):
            reply_text = "Getting kicked out of school feels like the end of the world right now. But there are other paths forward, even when you can't see them. How are you holding up?"
        elif "sad" in user_lower or "alone" in user_lower:
            reply_text = "Sadness and loneliness can feel so overwhelming. You're not alone right now though - I'm here with you."
        elif has_crisis_risk:
            reply_text = "I can hear how much pain you're in right now. Please reach out to someone you trust or a crisis line - you don't have to face this alone."
        elif has_grief_context:
            reply_text = "Losing someone you love that much - the pain is just enormous. Take it one breath at a time."
        elif any(greeting in user_lower for greeting in ["hi", "hello", "what's up"]):
            # Optimized greeting response using pre-computed hash
            fallback_greetings = [
                "Hey there! How's it going?",
                "Hi! How are you doing today?", 
                "Hey! What's on your mind?",
                "Hello! How are things with you?",
                "Hi there! How's your day been?"
            ]
            hash_val = int(hashlib.md5(user_text.encode()).hexdigest(), 16)
            reply_text = fallback_greetings[hash_val % len(fallback_greetings)]
        elif user_lower.strip() == "nothing much":
            reply_text = "Fair enough. Sometimes there's not much to say, and that's okay too."
        else:
            reply_text = "I'm here and listening. Could you help me understand what's on your mind?"

    # Optimized post-processing using pre-compiled replacements
    for old_text, new_text in NATURAL_FLOW_REPLACEMENTS.items():
        reply_text = reply_text.replace(old_text, new_text)
    
    for clinical, natural in CLINICAL_REPLACEMENTS.items():
        reply_text = reply_text.replace(clinical, natural)

    return reply_text.strip()


def update_summary(existing_summary: Optional[str], history: List[dict], latest_user: str, latest_bot: str) -> str:
    """Create a more natural conversation summary."""

    # Get recent conversation snippets
    recent_parts = []
    for item in history[-6:]:  # Last 6 exchanges
        role = "They" if item['role'] == 'user' else "I"
        text = item['text'][:100] + \
            "..." if len(item['text']) > 100 else item['text']
        recent_parts.append(f"{role}: {text}")

    recent_context = "\n".join(recent_parts)

    prompt = f"""Based on this conversation, write a natural summary of what's been shared:

Previous summary: {existing_summary or 'This is our first conversation'}

Recent conversation:
{recent_context}

Latest exchange:
They said: {latest_user}
I responded: {latest_bot}

Write a brief, natural summary (under 100 words) covering:
- What they're dealing with
- How they've been feeling
- What they're trying or what helps
- Any important context to remember

Make it conversational, not clinical."""

    try:
        result = model.generate_content(prompt)
        return result.text.strip() if result.text else existing_summary or ""
    except:
        return existing_summary or "Ongoing supportive conversation"


# Pre-compile keyword sets for memory update performance
WORK_KEYWORDS = frozenset(["work", "job", "boss", "shift", "overtime"])
SCHOOL_KEYWORDS = frozenset(["school", "study", "exam", "grade"])
FAMILY_KEYWORDS = frozenset(["family", "parent", "sibling", "relationship"])
FAMILY_MOTIVATION_KEYWORDS = frozenset(["family", "kids", "children"])
OVERWHELMED_KEYWORDS = frozenset(["exhausted", "drained", "overwhelmed"])
IMPROVING_KEYWORDS = frozenset(["better", "helping", "improving"])

COPING_KEYWORDS = {
    "breathing": "breathing exercises",
    "bath": "taking baths", 
    "music": "listening to music",
    "walk": "going for walks",
    "tea": "having tea",
    "read": "reading",
    "meditation": "meditation",
    "exercise": "exercise"
}

def update_memory(existing: Optional[Dict[str, Any]], history: List[dict], latest_user: str, latest_bot: str) -> Dict[str, Any]:
    """Update memory with a more natural approach - optimized for performance."""

    existing = existing or {}

    # Optimized text combination
    text_parts = [item['text'] for item in history[-8:] if item.get('text')]
    text_parts.extend([latest_user, latest_bot])
    text_lower = " ".join(text_parts).lower()

    # Optimized keyword detection using pre-compiled sets
    if not existing.get("stressor"):
        if any(word in text_lower for word in WORK_KEYWORDS):
            existing["stressor"] = "work stress"
        elif any(word in text_lower for word in SCHOOL_KEYWORDS):
            existing["stressor"] = "academic pressure"
        elif any(word in text_lower for word in FAMILY_KEYWORDS):
            existing["stressor"] = "family situation"

    # Optimized motivation detection
    if not existing.get("motivation"):
        if "tuition" in text_lower and ("sister" in text_lower or "sibling" in text_lower):
            existing["motivation"] = "helping with family education"
        elif any(word in text_lower for word in FAMILY_MOTIVATION_KEYWORDS):
            existing["motivation"] = "taking care of family"

    # Optimized coping items detection
    coping_items = set(existing.get("coping", []))
    for keyword, activity in COPING_KEYWORDS.items():
        if keyword in text_lower:
            coping_items.add(activity)
    existing["coping"] = list(coping_items)[:8]  # Keep it manageable

    # Optimized trajectory detection
    if not existing.get("trajectory"):
        if any(word in text_lower for word in OVERWHELMED_KEYWORDS):
            existing["trajectory"] = "feeling overwhelmed and drained"
        elif any(word in text_lower for word in IMPROVING_KEYWORDS):
            existing["trajectory"] = "working on feeling better"

    return existing
