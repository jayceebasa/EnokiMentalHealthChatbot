import os
import re
import random
import logging
import google.generativeai as genai
from typing import List, Optional, Dict, Any, Tuple

# Setup logging
logger = logging.getLogger(__name__)

GRIEF_KEYWORDS = frozenset(["died", "passed", "funeral",
                           "miss", "pet", "dog", "cat", "tiger", "rainbow bridge"])
HIGH_DISTRESS = frozenset(["sadness", "grief", "despair", "anxiety", "fear"])

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

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel("gemini-2.0-flash")


def add_breaks(text: str, max_sentences=2) -> str:
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = [' '.join(sentences[i:i+max_sentences])
                  for i in range(0, len(sentences), max_sentences)]
    return '\n\n'.join(paragraphs)


def assess_response_type(user_text: str) -> str:
    """
    Use Gemini to intelligently determine what type of response is needed.
    Returns response type: immediate_danger, grief, panic, high_distress, or normal
    """
    assessment_prompt = f"""You are a mental health AI assistant. Analyze this message and determine what type of response is needed.

Message: "{user_text}"

Classify into ONE of these categories:

1. **IMMEDIATE_DANGER**: User mentions active plans to harm themselves/others, suicide intent, self-harm intent
   Examples: "I'm going to hurt myself", "I have a plan to end it", "I want to kill myself tonight"

2. **GRIEF**: User is processing loss, death, grief, mourning
   Examples: "My dad died", "I miss my dog so much", "I went to a funeral today"

3. **PANIC**: User describes panic attack symptoms or acute physical anxiety
   Examples: "I can't breathe", "I'm hyperventilating", "panic attack", "tight chest"

4. **HIGH_DISTRESS**: User expresses severe emotional distress without immediate self-harm plans
   Examples: "I feel hopeless", "Everything is falling apart", "I can't take this anymore"

5. **NORMAL**: Regular conversation, manageable stress, everyday concerns
   Examples: "I'm overwhelmed with homework", "Work is stressful today", "Had a bad day"

Respond with ONLY the category name (one word):
IMMEDIATE_DANGER
GRIEF
PANIC
HIGH_DISTRESS
NORMAL"""

    try:
        response = model.generate_content(
            assessment_prompt,
            generation_config={
                "temperature": 0.1,
                "max_output_tokens": 30
            },
            request_options={"timeout": 10}
        )

        assessment = response.text.strip().upper()
        logger.info(
            f"Response type assessment: {assessment} for message: {user_text[:50]}...")

        # Extract the response type from the response
        valid_types = ["IMMEDIATE_DANGER", "GRIEF", "PANIC", "HIGH_DISTRESS", "NORMAL"]
        for resp_type in valid_types:
            if resp_type in assessment:
                return resp_type.lower()

        return "normal"

    except Exception as e:
        logger.error(f"Response type assessment failed: {str(e)}")
        # If Gemini fails, default to normal conversation
        return "normal"


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

    # STEP 1: Use Gemini to assess what type of response is needed
    response_type = assess_response_type(user_text)
    logger.info(f"Response type determined: {response_type}")

    # Extract tone preference
    tone = preferences.get('tone', 'empathetic').lower(
    ) if preferences else 'empathetic'

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

    # Get recent conversation context
    recent_history = history[-12:]
    convo_snippets = [
        f"{'You' if h.get('role') == 'user' else 'Me'}: {h.get('text', '').strip()}"
        for h in recent_history if h.get('text', '').strip()
    ]
    convo_context = "\n".join(
        convo_snippets) if convo_snippets else "Just getting our convo going!"
    main_emotions = [e.get('label', '')
                     for e in emotions[:3] if e.get('score', 0) > 0.3]
    emotion_context = ", ".join(
        main_emotions) if main_emotions else "just feeling regular"
    memory = memory or {}
    main_focus = memory.get("stressor") or memory.get(
        "motivation") or "whatever's up right now"
    helpful_things = memory.get("coping", [])
    helpful_things_str = ', '.join(
        helpful_things[:2]) if helpful_things else "just finding what works and what doesn't"

    # STEP 2: Handle each response type appropriately

    # IMMEDIATE_DANGER: User may be in crisis
    if response_type == "immediate_danger":
        logger.warning(f"🚨 CRISIS DETECTED - Message: {user_text[:100]}")

        crisis_resources_text = "**🆘 IMMEDIATE HELP - PHILIPPINES CRISIS HOTLINES:**\n\n"
        for hotline in PHILIPPINE_CRISIS_RESOURCES["national_hotlines"]:
            crisis_resources_text += f"• {hotline}\n"
        crisis_resources_text += f"\n• {PHILIPPINE_CRISIS_RESOURCES['emergency']}\n\n"
        crisis_resources_text += "**Regional Support:**\n"
        for hotline in PHILIPPINE_CRISIS_RESOURCES["regional_hotlines"]:
            crisis_resources_text += f"• {hotline}\n"
        crisis_resources_text += "\n**These are all FREE, confidential, and available 24/7.**"

        crisis_prompt = f'''You are Enoki, a compassionate mental health companion. The user expressed concerns about self-harm or suicide.

Message: "{user_text}"

**Your task** (be concise and complete):
1. Validate their feelings with genuine concern
2. Emphasize their life has value
3. Provide support and hope
4. Include ALL crisis resources below
5. End with reassurance they're not alone

Crisis Resources:
{crisis_resources_text}

Keep it warm, caring, and complete - no cut-off sentences.'''

        try:
            response = model.generate_content(
                crisis_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 500
                },
                request_options={"timeout": 10}
            )
            reply = response.text.strip() if hasattr(
                response, "text") and response.text else ""
            return add_breaks(reply)
        except Exception as e:
            logger.error(f"Crisis response generation failed: {str(e)}")
            fallback_msg = f"I'm really concerned about you right now. Your life has value, and there are people who want to help you through this.\n\n{crisis_resources_text}\n\nPlease reach out to one of these resources right now. You don't have to face this alone."
            return add_breaks(fallback_msg)

    # GRIEF: User is processing loss
    elif response_type == "grief":
        logger.info(f"Grief support needed")

        grief_prompt = f'''You are Enoki, supporting someone experiencing grief and loss.

Message: "{user_text}"

**Your task** (be concise and complete):
1. Respond with deep compassion and understanding
2. Acknowledge the weight of their loss
3. Validate grief as a form of love
4. Offer gentle presence and honor their memories
5. Complete your thoughts fully

**Tone**: {tone_config['style']}

Keep it warm, gentle, and complete - no cut-off sentences.'''

        try:
            response = model.generate_content(
                grief_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 300
                },
                request_options={"timeout": 10}
            )
            grief_reply = response.text.strip() if hasattr(
                response, "text") and response.text else ""
            return add_breaks(grief_reply)
        except Exception as e:
            logger.error(f"Grief response generation failed: {str(e)}")
            fallback_grief = f"I'm so sorry for your loss. The love you had is real and precious, and grief is the price we pay for that love. I'm here with you through this."
            return add_breaks(fallback_grief)

    # PANIC: User is having a panic attack or acute anxiety
    elif response_type == "panic":
        logger.info(f"Panic attack support needed")

        panic_prompt = f'''You are Enoki, supporting someone experiencing a panic attack or acute anxiety.

Message: "{user_text}"

**Your task** (be concise and complete):
1. Respond with immediate grounding and support
2. Guide them through calming breathing: "Breathe in—1, 2, 3, 4. Hold—1, 2, 3, 4. Out—1, 2, 3, 4."
3. Reassure them they're safe and this will pass
4. Use grounding techniques (5 senses, etc.)
5. Complete your thoughts fully

**Tone**: {tone_config['style']}

Keep it warm, calming, and complete - no cut-off sentences.'''

        try:
            response = model.generate_content(
                panic_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 300
                },
                request_options={"timeout": 10}
            )
            panic_reply = response.text.strip() if hasattr(
                response, "text") and response.text else ""
            return add_breaks(panic_reply)
        except Exception as e:
            logger.error(f"Panic response generation failed: {str(e)}")
            fallback_panic = f"You're not alone. I'm here with you. Breathe in slowly—1, 2, 3, 4. Hold—1, 2, 3, 4. Out—1, 2, 3, 4.\n\nYou're safe. This will pass."
            return add_breaks(fallback_panic)

    # HIGH_DISTRESS: User expresses severe emotional distress
    elif response_type == "high_distress":
        logger.info(f"High distress support needed")

        crisis_resources = "\n".join(
            PHILIPPINE_CRISIS_RESOURCES["national_hotlines"])
        emergency = PHILIPPINE_CRISIS_RESOURCES["emergency"]

        distress_prompt = f'''You are Enoki, supporting someone in emotional distress.

Message: "{user_text}"

**Your task** (be concise and complete):
1. Validate their feelings with genuine understanding
2. Show you take this seriously
3. Offer 2-3 practical, actionable suggestions (be specific)
4. If they mention suicide/self-harm, include these resources:
{crisis_resources}
{emergency}
5. End with hope and reassurance

**Tone**: {tone_config['style']}

Keep it warm, caring, and concise. Complete your thoughts - no cut-off sentences.'''

        try:
            response = model.generate_content(
                distress_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 350
                },
                request_options={"timeout": 10}
            )
            distress_reply = response.text.strip() if hasattr(
                response, "text") and response.text else ""
            return add_breaks(distress_reply)
        except Exception as e:
            logger.error(f"High distress response generation failed: {str(e)}")
            return add_breaks("I hear you, and I'm here for you. What you're feeling is real and valid. I'm listening.")

    # NORMAL: Regular conversation
    else:  # response_type == "normal"
        normal_prompt = f'''You are Enoki, chatting like a close friend who genuinely cares.

Message: "{user_text}"

Their situation: {main_focus}
What's helping them: {helpful_things_str}

**Your task** (be concise and complete):
1. Respond naturally and warmly
2. Show you understand their situation
3. Offer genuine support or practical suggestions
4. Ask a thoughtful follow-up question
5. Complete your thoughts fully

**Tone**: {tone_config['style']}

Keep it natural, warm, and complete - no cut-off sentences.'''

        try:
            response = model.generate_content(
                normal_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 300
                },
                request_options={"timeout": 10}
            )
            reply = response.text.strip() if hasattr(
                response, "text") and response.text else ""
            return add_breaks(reply)
        except Exception as e:
            logger.error(f"Normal response generation failed: {str(e)}")
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
        text_cut = entry['text'][:100] + \
            ("..." if len(entry['text']) > 100 else "")
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


# Memory tracking constants
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