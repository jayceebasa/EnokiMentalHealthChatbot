import os
import re
import random
import hashlib
import time
import logging
import google.generativeai as genai
from typing import List, Optional, Dict, Any, Tuple

# Setup logging
logger = logging.getLogger(__name__)

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

PHILIPPINE_CRISIS_RESOURCES = {
    "national_hotlines": [
        "**National Center for Mental Health Crisis Hotline**: 1553 (landline nationwide, toll-free) or 0917-899-8727",
        "**HOPELINE Philippines**: 2919 (Globe/TM toll-free) or (02) 8804-4673",
        "**In Touch Community Services**: (02) 8893-7603 or 0917-800-1123 (24/7 free crisis line)"
    ],
    "regional_hotlines": [
        "**Tawag Paglaum - Centro Bisaya** (Cebu): 0939-937-5433 or 0927-654-1629",
        "**Quezon City Helpline**: 122 (for QC residents)"
    ],
    "emergency": "**Emergency Services**: 911"
}

SELF_HARM_KEYWORDS = frozenset([
    "self harm", "self-harm", "cut myself", "cutting", "hurt myself", 
    "end my life", "kill myself", "suicide", "suicidal", "want to die",
    "better off dead", "no point living", "can't go on", "join them",
    "be with them", "end it all", "take my life", "overdose"
])
CRISIS_PHRASES = frozenset([
    "i want to die", "i don't want to live", "life isn't worth living",
    "everyone would be better without me", "i have a plan", "i can't take it anymore",
    "there's no hope", "i'm done", "i give up", "what's the point"
])

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.5-flash")

def add_breaks(text: str, max_sentences=2) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = [' '.join(sentences[i:i+max_sentences]) for i in range(0, len(sentences), max_sentences)]
    return '\n\n'.join(paragraphs)

def assess_crisis_risk(user_text: str) -> Tuple[bool, str]:
    """
    Use Gemini to assess if message indicates immediate crisis/self-harm risk.
    Returns (is_crisis, risk_type)
    
    Risk types:
    - immediate_danger: Active plans to harm self or others
    - severe_distress: Extreme distress but no immediate harm plans
    - safe: Normal conversation or manageable distress
    """
    crisis_prompt = f"""You are a mental health crisis detector. Analyze this message for IMMEDIATE safety concerns.

Message: "{user_text}"

Determine if this indicates:
1. **IMMEDIATE_DANGER**: Active plans to harm self or others, suicidal intent, self-harm intent
2. **SEVERE_DISTRESS**: Extreme emotional distress but no immediate harm plans
3. **SAFE**: Normal conversation or manageable distress

Look for:
- Direct or indirect mentions of self-harm, suicide, or harming others
- Expressions of hopelessness with plans to act
- Descriptions of self-harm methods or plans
- Statements about wanting to die or end life

Examples of IMMEDIATE_DANGER:
- "I'm going to hurt myself"
- "I'll just slice my neck with a blade"
- "I want to end it all tonight"
- "I have pills and I'm ready"
- "I'm going to jump"
- "I can't take it anymore, I'm done"

Examples of SEVERE_DISTRESS (not immediate danger):
- "I feel so hopeless"
- "Everything is falling apart"
- "I don't know how much longer I can do this"

Examples of SAFE:
- "I'm having a bad day"
- "I'm feeling sad about my breakup"
- "Work is really stressing me out"

Respond with ONLY ONE WORD:
- IMMEDIATE_DANGER
- SEVERE_DISTRESS
- SAFE"""

    try:
        response = model.generate_content(
            crisis_prompt,
            generation_config={
                "temperature": 0.1,  # Low temperature for consistent assessment
                "max_output_tokens": 50
            },
            request_options={"timeout": 10}
        )
        
        assessment = response.text.strip().upper()
        logger.info(f"Crisis assessment: {assessment} for message: {user_text[:50]}...")
        
        if "IMMEDIATE_DANGER" in assessment:
            return (True, "immediate_danger")
        elif "SEVERE_DISTRESS" in assessment:
            return (False, "severe_distress")
        else:
            return (False, "safe")
            
    except Exception as e:
        logger.error(f"Crisis assessment failed: {str(e)}")
        # Fallback to keyword detection if Gemini fails
        user_lower = user_text.lower()
        if any(phrase in user_lower for phrase in SELF_HARM_KEYWORDS) or \
           any(phrase in user_lower for phrase in CRISIS_PHRASES):
            logger.warning(f"Fallback crisis detection triggered for: {user_text[:50]}")
            return (True, "immediate_danger")
        return (False, "safe")

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
    
    # STEP 1: Use Gemini to assess crisis risk FIRST (before any other checks)
    is_crisis, risk_type = assess_crisis_risk(user_text)
    
    # STEP 2: If Gemini detects IMMEDIATE_DANGER, show hotlines immediately
    if is_crisis or risk_type == "immediate_danger":
        logger.warning(f"🚨 CRISIS DETECTED by Gemini - Message: {user_text[:100]}")
        
        crisis_message = "I'm really concerned about you right now. Your life has value, and there are people who want to help.\n\n"
        crisis_message += "**🆘 IMMEDIATE HELP - PHILIPPINES CRISIS HOTLINES:**\n\n"
        for hotline in PHILIPPINE_CRISIS_RESOURCES["national_hotlines"]:
            crisis_message += f"• {hotline}\n"
        crisis_message += f"\n• {PHILIPPINE_CRISIS_RESOURCES['emergency']}\n\n"
        crisis_message += "**Regional Support:**\n"
        for hotline in PHILIPPINE_CRISIS_RESOURCES["regional_hotlines"]:
            crisis_message += f"• {hotline}\n"
        crisis_message += "\n**These are all FREE, confidential, and available 24/7.** Please reach out to any of them right now - you don't have to face this alone.\n\n"
        crisis_message += "You matter. Your feelings are valid, but there are people trained to help you through this safely. I'm here with you too, but please contact one of these crisis lines for immediate professional support."
        return add_breaks(crisis_message)
    
    # Continue with normal conversation flow
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
    
    # Extract tone preference
    tone = preferences.get('tone', 'empathetic').lower() if preferences else 'empathetic'
    
    # Define tone styles for mental health context
    tone_styles = {
        'empathetic': {
            'style': 'warm, deeply understanding, and compassionate',
            'approach': 'Validate feelings gently and offer comforting presence'
        },
        'supportive': {
            'style': 'encouraging, uplifting, and positive',
            'approach': 'Focus on strengths and offer hopeful perspectives'
        },
        'professional': {
            'style': 'respectful, structured, and therapeutic',
            'approach': 'Use therapeutic language while maintaining warmth'
        },
        'gentle': {
            'style': 'soft, calming, and tender',
            'approach': 'Speak very softly and prioritize comfort over all else'
        },
        'casual': {
            'style': 'friendly, relaxed, and conversational',
            'approach': 'Chat like a close friend who genuinely cares'
        },
        'batman': {
            'style': 'gravelly, direct, and justice-oriented with dark knight wisdom',
            'approach': 'Speak like batman. Speak with intensity and determination, emphasizing strength and resilience. Use short, powerful statements. Channel the darkness into hope.'
        }
    }
    
    tone_config = tone_styles.get(tone, tone_styles['empathetic'])
    
    friendly_greets = [
        "Hey, good to hear from you!",
        "Hi! Been up to anything interesting today?",
        "Heyy! What's new or just the same old same old?"
    ]

    # ...existing code for severity checks...
    self_harm_detected = any(phrase in user_lower for phrase in SELF_HARM_KEYWORDS)
    crisis_phrases_detected = any(phrase in user_lower for phrase in CRISIS_PHRASES)
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

    # Include Gemini's severe_distress assessment in high_distress
    high_distress = any(
        e.get('label', '').lower() in HIGH_DISTRESS and e.get('score', 0) >= 0.35
        for e in emotions
    ) or risk_type == "severe_distress"

    # Note: Crisis intervention is now handled at the top of the function via assess_crisis_risk()

    # Panic attack support - tone doesn't override panic response
    if severe_panic or panic_present or "can't breathe" in user_lower:
        panic_msg = "You're not alone. I'm here with you. Try this:\n\nBreathe in slowly—1, 2, 3, 4. Hold—1, 2, 3, 4. Out—1, 2, 3, 4.\n\nYou're safe. This moment will pass. If you need urgent help, you can contact:\n"
        panic_msg += f"• {PHILIPPINE_CRISIS_RESOURCES['national_hotlines'][0]}\n"
        panic_msg += f"• {PHILIPPINE_CRISIS_RESOURCES['emergency']}\n\n"
        panic_msg += "No need to reply—just focus on breathing and know I'm right here for you."
        return add_breaks(panic_msg)

    if grief_present or grief_context:
        pet_name = "Tiger" if "tiger" in user_lower else "them"
        return add_breaks(
            f"It's so hard to lose someone who means so much. The love you have for {pet_name} is real and precious. Grief can feel like too much sometimes. I'm here and holding space for you."
        )

    if any(greet in user_lower for greet in ["hi", "hello", "hey", "what's up", "hi there"]):
        return add_breaks(random.choice(friendly_greets))

    # Conversation logic with tone applied
    smalltalk_examples = [
        "I've been thinking way too much about what to eat for dinner.",
        "Honestly, my brain's been bouncing around random memories today.",
        "Kept humming a song all morning for some reason. Earworms, right?",
        "Just the usual—trying to not nap in the middle of the afternoon, haha.",
        "Trying and failing to keep my plants alive. Oops."
    ]
    helpful_things_str = ', '.join(helpful_things[:2]) if helpful_things else "just finding what works and what doesn't"

    if high_distress or grief_context:
        # Format crisis resources for the prompt
        crisis_resources = "\n".join(PHILIPPINE_CRISIS_RESOURCES["national_hotlines"])
        emergency = PHILIPPINE_CRISIS_RESOURCES["emergency"]
        
        prompt = f'''
You're Enoki, giving gentle support: "{user_text}"

Recent convo:
{convo_context}

State: {emotion_context}
Main focus: {main_focus}

**Conversation Tone**: {tone_config['style']}
**Approach**: {tone_config['approach']}

**IMPORTANT**: If their message mentions thoughts of suicide, self-harm, wanting to die, or that life isn't worth living, you MUST include these Philippine crisis resources in your response:

{crisis_resources}
{emergency}

Reply with this tone in mind:
- Validate their feeling
- Offer comfort/presence
- If they mention suicidal thoughts, provide the crisis hotlines above warmly and encourage them to reach out
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

**Conversation Tone**: {tone_config['style']}
**Approach**: {tone_config['approach']}

Respond:
- Keep it {tone_config['style'].split(',')[0]}
- Break replies into short, warm paragraphs
- End naturally—a gentle question or comforting thought
- Embody the tone throughout your response
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
