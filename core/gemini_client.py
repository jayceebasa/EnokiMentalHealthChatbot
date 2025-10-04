import os
import re
import random
import hashlib
import google.generativeai as genai
from typing import List, Optional, Dict, Any

FLOW_GUIDES = [
    "keep things casual and focused on what they just said",
    "pick out something real from their message — avoid generic stuff",
    "mix up how you start — sometimes reflect, sometimes build on what they said",
    "let your response grow naturally from their feelings"
]

GRIEF_KEYWORDS = frozenset(["died", "passed", "funeral", "miss", "pet", "dog", "cat", "tiger", "rainbow bridge"])
RISK_KEYWORDS = frozenset(["end my life", "kill myself", "suicide", "self harm", "join them"])
CRISIS_WORDS = frozenset(["suicide", "kill myself", "end my life", "self harm", "join them", "be with them"])
GRIEF_WORDS = frozenset(["died", "passed", "funeral", "miss them", "rainbow bridge", "pet", "dog", "cat"])
HIGH_DISTRESS = frozenset(["sadness", "grief", "despair", "anxiety", "fear"])
PANIC_KEYWORDS = frozenset([
    "hyperventilating", "can't breathe", "cannot breathe", "panic attack",
    "closing in", "overwhelmed", "terrified", "tight chest", "shortness of breath"
])
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
NATURAL_REPHRASES = {
    "It sounds like ": "",
    "That sounds ": "",
    "It seems like ": "",
    "I'm sorry to hear ": ""
}
FRIENDLY_REPLACEMENTS = {
    "coping strategies": "things that help",
    "stressor": "what's been tough",
    "emotional trajectory": "how you've been feeling",
    "validated": "heard",
    "processing": "working through"
}

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

def add_breaks(text: str, max_sentences=2) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = [' '.join(sentences[i:i+max_sentences]) for i in range(0, len(sentences), max_sentences)]
    return '\n\n'.join(paragraphs)

def generate_reply(
    user_text: str,
    emotions: List[Dict[str, float]],
    preferences: Dict,
    history: Optional[List[Dict]] = None,
    summary: Optional[str] = None,
    memory: Optional[Dict[str, Any]] = None,
) -> str:
    user_lower = (user_text or "").lower()
    history = history or []
    recent_history = history[-12:]
    convo_snippets = [
        f"{'You' if h.get('role') == 'user' else 'Me'}: {h.get('text','').strip()}"
        for h in recent_history if h.get('text', '').strip()
    ]
    convo_context = "\n".join(convo_snippets) if convo_snippets else "Just getting our convo going!"
    main_emotions = [e.get('label', '') for e in emotions[:3] if e.get('score', 0) > 0.3]
    emotion_context = ", ".join(main_emotions) if main_emotions else "just feeling regular"
    memory = memory or {}
    main_focus = memory.get("stressor") or memory.get("motivation") or "whatever's up right now"
    helpful_things = memory.get("coping", [])
    friendly_greets = [
        "Hey, good to hear from you!",
        "Hi! Been up to anything interesting today?",
        "Heyy! What's new or just the same old same old?"
    ]

    # Severity checks
    grief_present = any(word in user_lower for word in GRIEF_KEYWORDS)
    risk_present = any(word in user_lower for word in RISK_KEYWORDS)
    crisis_risk = any(word in user_lower for word in CRISIS_WORDS)
    grief_context = any(word in user_lower for word in GRIEF_WORDS)
    panic_present = any(word in user_lower for word in PANIC_KEYWORDS)
    severe_panic = any(kw in user_lower for kw in PANIC_KEYWORDS) or (
        "fear" in emotion_context and any(e.get('score', 0) > 0.6 for e in emotions if e.get('label') == 'fear')
    )

    sarcasm_flag = False
    if any(phrase in user_lower for phrase in SARCASTIC_PHRASES):
        negative_words = frozenset([
            "not", "cant", "can't", "won't", "wont", "never", "no",
            "fail", "bad", "awful", "terrible", "hate", "suck", "worst"
        ])
        if any(n in user_lower for n in negative_words):
            sarcasm_flag = True

    high_distress = any(
        e.get('label', '').lower() in HIGH_DISTRESS and e.get('score', 0) >= 0.35
        for e in emotions
    )

    # Immediate return for crisis/panic
    if severe_panic or panic_present or "can't breathe" in user_lower:
        return add_breaks(
            "You're not alone. I'm here with you. Try this:\n\nBreathe in slowly—1, 2, 3, 4. Hold—1, 2, 3, 4. Out—1, 2, 3, 4.\n\nYou're safe. This moment will pass. I'm with you—no need to reply, just focus on breathing and know I'm right here for you."
        )

    if risk_present or crisis_risk:
        return add_breaks(
            "I can see you're in deep pain right now. Please reach out to someone you trust, or a crisis line, as soon as you can. You really matter, and you're not alone."
        )

    if grief_present or grief_context:
        pet_name = "Tiger" if "tiger" in user_lower else "them"
        return add_breaks(
            f"It's so hard to lose someone who means so much. The love you have for {pet_name} is real and precious. Grief can feel like too much sometimes. I'm here and holding space for you."
        )

    # Normal greetings
    if any(greet in user_lower for greet in ["hi", "hello", "hey", "what's up", "hi there"]):
        return add_breaks(random.choice(friendly_greets))

    # Conversation logic for gentle/casual
    smalltalk_examples = [
        "I've been thinking way too much about what to eat for dinner.",
        "Honestly, my brain's been bouncing around random memories today.",
        "Kept humming a song all morning for some reason. Earworms, right?",
        "Just the usual—trying to not nap in the middle of the afternoon, haha.",
        "Trying and failing to keep my plants alive. Oops."
    ]
    helpful_things_str = ', '.join(helpful_things[:2]) if helpful_things else "just finding what works and what doesn't"

    if high_distress or grief_context:
        prompt = f'''
You're Enoki, giving gentle support: "{user_text}"

Recent convo:
{convo_context}

State: {emotion_context}
Main focus: {main_focus}

Reply with gentle warmth:
- Validate their feeling
- Offer comfort/presence
- No long personal tangents
- Ask what (if anything) helps right now
'''
    else:
        prompt = f'''
You're Enoki, chatting like a close friend.

Example opening: "{random.choice(smalltalk_examples)}"
Follow-up: "What about you? Been up to anything fun or just normal stuff today?"

Recent convo:
{convo_context}

They just said: "{user_text}"

Their vibe: {emotion_context}
Main focus: {main_focus}
Trying: {helpful_things_str}

Respond:
- Keep it casual, gentle, and easy to read
- Break replies into short, warm paragraphs
- End naturally—a gentle question or comforting thought
'''

    try:
        response = model.generate_content(prompt)
        reply = response.text.strip() if hasattr(response, "text") and response.text else ""
        for old, new in NATURAL_REPHRASES.items():
            reply = reply.replace(old, new)
        for clinical, natural in FRIENDLY_REPLACEMENTS.items():
            reply = reply.replace(clinical, natural)
        return add_breaks(reply)
    except Exception:
        if severe_panic or panic_present:
            return add_breaks(
                "I'm right here with you. Don't worry about talking—just focus on breathing, nice and slow. This feeling will pass."
            )
        else:
            return add_breaks(
                random.choice([
                    "Hey, sorry if my reply's a bit off—my brain might be on autopilot! What's up with you today?",
                    "Haha, sometimes I just space out. Want to share what's on your mind?"
                ])
            )

def update_summary(existing_summary: Optional[str], history: List[Dict], latest_user: str, latest_bot: str) -> str:
    recent_snips = []
    for entry in history[-6:]:
        speaker = "They" if entry['role'] == 'user' else "I"
        text_cut = entry['text'][:100] + ("..." if len(entry['text']) > 100 else "")
        recent_snips.append(f"{speaker}: {text_cut}")
    recent_context = "\n".join(recent_snips)
    prompt = f"""Here's what we've talked about recently:

{recent_context}

They just said: {latest_user}
I replied: {latest_bot}

Summarize naturally, under 100 words, including:
- What they're going through
- How they're feeling
- What's helping or what they're trying
- Key things to remember

Keep it casual and friendly."""
    try:
        result = model.generate_content(prompt)
        output = result.text.strip() if result.text else (existing_summary or "")
        return add_breaks(output)
    except:
        return add_breaks(existing_summary or "Chat is ongoing and supportive.")

WORK_WORDS = frozenset(["work", "job", "boss", "shift", "overtime"])
SCHOOL_WORDS = frozenset(["school", "study", "exam", "grade"])
FAMILY_WORDS = frozenset(["family", "parent", "sibling", "relationship"])
FAMILY_MOTIVATION = frozenset(["family", "kids", "children"])
FEELING_OVERWHELMED = frozenset(["exhausted", "drained", "overwhelmed"])
FEELING_BETTER = frozenset(["better", "helping", "improving"])
COPING_MAP = {
    "breathing": "breathing exercises",
    "bath": "taking baths",
    "music": "listening to music",
    "walk": "going for walks",
    "tea": "having tea",
    "read": "reading",
    "meditation": "meditation",
    "exercise": "exercise"
}

def update_memory(existing: Optional[Dict[str, Any]], history: List[Dict], latest_user: str, latest_bot: str) -> Dict[str, Any]:
    existing = existing or {}
    recent_texts = [item['text'] for item in history[-8:] if item.get('text')]
    recent_texts.extend([latest_user, latest_bot])
    text_all = " ".join(recent_texts).lower()
    if not existing.get("stressor"):
        if any(w in text_all for w in WORK_WORDS):
            existing["stressor"] = "work stress"
        elif any(w in text_all for w in SCHOOL_WORDS):
            existing["stressor"] = "school stress"
        elif any(w in text_all for w in FAMILY_WORDS):
            existing["stressor"] = "family stuff"
    if not existing.get("motivation"):
        if "tuition" in text_all and ("sister" in text_all or "sibling" in text_all):
            existing["motivation"] = "helping family with school"
        elif any(w in text_all for w in FAMILY_MOTIVATION):
            existing["motivation"] = "looking out for family"
    coping_set = set(existing.get("coping", []))
    for key, val in COPING_MAP.items():
        if key in text_all:
            coping_set.add(val)
    existing["coping"] = list(coping_set)[:8]
    if not existing.get("trajectory"):
        if any(w in text_all for w in FEELING_OVERWHELMED):
            existing["trajectory"] = "feeling drained and overwhelmed"
        elif any(w in text_all for w in FEELING_BETTER):
            existing["trajectory"] = "starting to feel better"
    return existing
