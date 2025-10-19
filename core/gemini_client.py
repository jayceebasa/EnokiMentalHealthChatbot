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


def assess_response_type(user_text: str, emotions: List[Dict[str, float]]) -> str:
    """
    Use Gemini to intelligently determine response type, considering RoBERTa emotions.
    Returns response type: immediate_danger, grief, panic, high_distress, or normal
    """
    # Extract emotion context from RoBERTa
    emotion_data = []
    for emotion in emotions[:3]:
        label = emotion.get('label', 'unknown')
        score = emotion.get('score', 0)
        if score > 0.2:  # Only include emotions with reasonable confidence
            emotion_data.append(f"{label} ({score:.2f})")
    
    emotion_summary = ", ".join(emotion_data) if emotion_data else "neutral emotions"
    
    assessment_prompt = f"""You are a mental health AI expert. Your task is to understand the USER'S TRUE INTENT AND EMOTIONAL STATE, not just surface-level words.

Message: "{user_text}"

Emotional indicators (RoBERTa): {emotion_summary}

Analyze these dimensions:

1. **TRUE INTENT**: What is the user actually trying to communicate?
   - Are they joking/venting for relief? (even with negative words)
   - Are they genuinely in crisis with specific plans?
   - Are they seeking practical help vs. emotional support?

2. **TONE & CONTEXT**: How serious is this message?
   - Casual/humorous tone (even with "I hate", "I'm dying") = likely not crisis
   - Serious/hopeless tone = escalate
   - Factual complaint vs. emotional spiral

3. **SEMANTIC MEANING**: What does this really mean?
   - "I want to die" (in a joke context) ≠ "I have a plan to end my life"
   - "I'm overwhelmed" (with work) ≠ "I feel completely hopeless"
   - Strong language ≠ strong intent

4. **COHERENCE CHECK**: Do RoBERTa emotions match message intent?
   - High anxiety + casual tone = likely stress-masking → NORMAL (for now) or HIGH_DISTRESS if serious content
   - High sadness + loss mention = GRIEF
   - High fear + physical symptoms = PANIC

Now classify based on TRUE INTENT and SEMANTIC MEANING:

**IMMEDIATE_DANGER**: User expresses active intent to harm self/others with specific plans or timeframe
- "I'm going to [specific method]"
- "I have a plan for tonight"
- "I'm ready to end this"
- NOT just dark thoughts or venting

**GRIEF**: User is processing loss, mourning, or death-related content
- Mentions death, funeral, loss
- Expressing sadness about someone/something specific
- Contextually clear loss situation

**PANIC**: User describes acute physical anxiety or panic attack symptoms
- Can't breathe, chest pain, hyperventilating
- Describes panic attack
- Acute physical distress (not just emotional)

**HIGH_DISTRESS**: User expresses genuine emotional suffering without immediate self-harm plans
- Hopelessness/despair without specific intent
- Feeling trapped or unable to cope
- Severe emotional pain that goes beyond daily stress
- NOT just casual venting or homework stress

**NORMAL**: Regular conversation about manageable concerns
- Everyday stress, procrastination, complaints
- Joking/sarcasm even with negative words
- Seeking practical advice
- Venting for relief (not crisis)

REMEMBER: Understand the MEANING, not just the WORDS.

Classify into ONE category:
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
            f"Response type assessment: {assessment} | Emotions: {emotion_summary} | Message: {user_text[:50]}...")

        # Extract the response type from the response
        valid_types = ["IMMEDIATE_DANGER", "GRIEF", "PANIC", "HIGH_DISTRESS", "NORMAL"]
        for resp_type in valid_types:
            if resp_type in assessment:
                return resp_type.lower()

        return "normal"

    except Exception as e:
        logger.error(f"Response type assessment failed: {str(e)}")
        # Fallback: Use RoBERTa emotions to make a safe guess
        if emotions:
            top_emotion = emotions[0].get('label', '').lower()
            score = emotions[0].get('score', 0)
            if score > 0.6:
                if top_emotion in ['fear', 'sadness', 'anger']:
                    logger.info(f"Fallback to high_distress based on {top_emotion}")
                    return "high_distress"
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

    # STEP 1: Use Gemini to assess response type, considering RoBERTa emotions
    response_type = assess_response_type(user_text, emotions)
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

Recent conversation:
{convo_context}

Current message: "{user_text}"

Emotional indicators (RoBERTa): {emotion_context}

**Your task** (be concise and complete):
1. Validate their feelings with genuine concern
2. Emphasize their life has value
3. Provide support and hope
4. Include ALL crisis resources below
5. End with reassurance they're not alone

**Response length**: This is a crisis - respond with appropriate depth and care. Be thorough but not verbose. Use length that matches severity.

Crisis Resources:
{crisis_resources_text}

Keep it warm, caring, and complete - no cut-off sentences. Reference their situation from the conversation.'''

        try:
            response = model.generate_content(
                crisis_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 1000
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

Recent conversation:
{convo_context}

Current message: "{user_text}"

Emotional indicators (RoBERTa): {emotion_context}

**Your task** (be concise and complete):
1. Respond with deep compassion and understanding
2. Acknowledge the weight of their loss
3. Validate grief as a form of love
4. Offer gentle presence and honor their memories
5. Complete your thoughts fully

**Response length**: Grief requires thoughtful, unhurried response. Match the depth of their loss. Be thorough - don't rush.

**Tone**: {tone_config['style']}

Keep it warm, gentle, and complete - no cut-off sentences. Reference their loss and our conversation history.'''

        try:
            response = model.generate_content(
                grief_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 600
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

Recent conversation:
{convo_context}

Current message: "{user_text}"

Emotional indicators (RoBERTa): {emotion_context}

**Your task** (be concise and complete):
1. Respond with immediate grounding and support
2. Guide them through calming breathing: "Breathe in—1, 2, 3, 4. Hold—1, 2, 3, 4. Out—1, 2, 3, 4."
3. Reassure them they're safe and this will pass
4. Use grounding techniques (5 senses, etc.)
5. Complete your thoughts fully

**Response length**: Panic needs focused, direct support. Be concise but thorough - help them ground NOW. Don't ramble.

**Tone**: {tone_config['style']}

Keep it warm, calming, and complete - no cut-off sentences. Reference their situation from our conversation.'''

        try:
            response = model.generate_content(
                panic_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 600
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

Recent conversation:
{convo_context}

Current message: "{user_text}"

Emotional indicators (RoBERTa): {emotion_context}
Their situation: {main_focus}

**Your task** (be concise and complete):
1. Validate their feelings with genuine understanding
2. Show you take this seriously
3. Offer 2-3 practical, actionable suggestions (be specific)
4. If they mention suicide/self-harm, include these resources:
{crisis_resources}
{emergency}
5. End with hope and reassurance

**Response length**: Match the depth of their distress. If severe, be thorough. If manageable, be brief but supportive. Quality over quantity.

**Tone**: {tone_config['style']}

Keep it warm, caring, and concise. Complete your thoughts - no cut-off sentences. Reference what they've shared with you.'''

        try:
            response = model.generate_content(
                distress_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 700
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

Recent conversation:
{convo_context}

Current message: "{user_text}"

Emotional indicators (RoBERTa): {emotion_context}
Their situation: {main_focus}
What's helping them: {helpful_things_str}

**Your task** (be concise and complete):
1. Respond naturally and warmly
2. Show you understand their situation
3. Offer genuine support or practical suggestions
4. Ask a thoughtful follow-up question
5. Complete your thoughts fully

**Response length**: Keep it natural. Short and sweet for casual chat, longer if they need advice. Don't force length - be genuine and conversational.

**Tone**: {tone_config['style']}

Keep it natural, warm, and complete - no cut-off sentences. Remember what they've shared with you in our conversation.'''

        try:
            response = model.generate_content(
                normal_prompt,
                generation_config={
                    "temperature": 0.7,
                    "max_output_tokens": 600
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