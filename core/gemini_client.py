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


def add_breaks(text: str, max_sentences=4) -> str:
    """Add paragraph breaks every 4 sentences to maintain readability without breaking flow."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    paragraphs = [' '.join(sentences[i:i+max_sentences])
                  for i in range(0, len(sentences), max_sentences)]
    return '\n\n'.join(paragraphs)


def safe_get_response_text(response) -> str:
    """Safely extract text from Gemini response, handling blocked/empty responses."""
    try:
        if hasattr(response, 'text') and response.text:
            return response.text.strip()
    except Exception as e:
        logger.warning(f"Could not extract response.text: {str(e)}")
    
    # If response has candidates with content, try to extract from there
    try:
        if hasattr(response, 'candidates') and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate, 'content') and hasattr(candidate.content, 'parts'):
                parts = candidate.content.parts
                if parts:
                    return parts[0].text.strip()
    except Exception as e:
        logger.warning(f"Could not extract from candidates: {str(e)}")
    
    return ""


def assess_response_type(user_text: str, emotions: List[Dict[str, float]]) -> str:
    """
    Use Gemini to intelligently determine response type, considering RoBERTa emotions.
    Returns response type: immediate_danger, grief, panic, high_distress, or normal
    
    STEP 1: Check for explicit crisis keywords first (safety-first approach)
    STEP 2: Use Gemini for nuanced assessment if not clearly a crisis
    """
    # ============ STEP 1: EXPLICIT CRISIS KEYWORD CHECK ============
    # This catches obvious self-harm/suicide mentions BEFORE Gemini
    # to prevent over-interpretation of user intent
    
    user_lower = user_text.lower()
    
    # EXPLICIT CRISIS MARKERS - these are unambiguous danger signals
    explicit_crisis_markers = {
        "suicide": [
            "kill myself", "kill myself", "killing myself", "want to die", 
            "should die", "end my life", "end it all", "end it", "take my life",
            "suicide", "suicidal", "commit suicide"
        ],
        "self_harm": [
            "cut myself", "cutting myself", "cutting", "self-harm", "self harm",
            "hurt myself", "hurting myself", "harm myself"
        ],
        "methods": [
            "overdose", "rope", "pills", "jump", "hanging", "wrist"
        ],
        "hopelessness_with_intent": [
            "no point in living", "better off dead", "everyone would be better off if i",
            "shouldn't be alive", "don't deserve to live"
        ]
    }
    
    # Check for explicit markers
    for category, markers in explicit_crisis_markers.items():
        for marker in markers:
            if marker in user_lower:
                logger.warning(f"🚨 EXPLICIT CRISIS MARKER DETECTED ({category}): '{marker}' in message")
                return "immediate_danger"
    
    # ============ STEP 2: EMOTION-BASED CHECK ============
    # If high sadness + specific loss keywords = GRIEF (not crisis)
    if emotions and len(emotions) > 0:
        top_emotion = emotions[0].get('label', '').lower()
        score = emotions[0].get('score', 0)
        
        # Grief detection - specific loss language
        grief_keywords = ["died", "passed", "funeral", "death", "lost", "lost my", "miss"]
        if top_emotion == 'sadness' and score > 0.7 and any(kw in user_lower for kw in grief_keywords):
            logger.info(f"Response type: GRIEF (sadness + loss keywords)")
            return "grief"
    
    # Extract emotion context from RoBERTa
    emotion_data = []
    for emotion in emotions[:3]:
        label = emotion.get('label', 'unknown')
        score = emotion.get('score', 0)
        if score > 0.2:  # Only include emotions with reasonable confidence
            emotion_data.append(f"{label} ({score:.2f})")
    
    emotion_summary = ", ".join(emotion_data) if emotion_data else "neutral emotions"
    
    # ============ STEP 3: GEMINI ASSESSMENT FOR EDGE CASES ============
    # Only use Gemini for nuanced assessment if no explicit markers found
    # This prevents over-interpretation while catching subtle crises
    
    assessment_prompt = f"""You are a mental health assessment expert. Your task is to classify the user's emotional state.

Message: "{user_text}"

Emotional indicators (RoBERTa): {emotion_summary}

CLASSIFICATION RULES (strict - only use these):

1. **PANIC**: Physical anxiety symptoms (can't breathe, racing heart, hyperventilating)
   - Only if they describe physical panic symptoms, NOT just emotional distress
   - Example: "My heart is racing, I can't breathe"
   - NOT just: "I'm anxious" or "I'm scared"

2. **GRIEF**: Processing death, loss, or bereavement
   - Already detected in Step 2 - Gemini confirms if needed
   - They mention someone/something died or was lost
   - Expressing sadness about specific loss

3. **HIGH_DISTRESS**: Emotional suffering without self-harm intent
   - Hopelessness BUT no mention of harming themselves
   - Feeling trapped, overwhelmed, can't cope
   - Genuine pain that goes beyond daily stress
   - Example: "Everything feels pointless, I don't know how to continue"
   - NOT: "I should kill myself" (that's crisis, already caught in Step 1)

4. **NORMAL**: Manageable conversation
   - Everyday stress, complaints, jokes
   - Seeking practical advice
   - Venting for relief
   - Even dark humor if clearly joking
   - Example: "This week is killing me" (clearly hyperbole)

DO NOT classify as HIGH_DISTRESS or PANIC if:
- Any hint of self-harm or suicide (already caught in Step 1)
- They're joking or using expressions hyperbolically
- They're handling stress with a coping mechanism

REMEMBER: 
- If there's ANY doubt about self-harm/suicide intent, Step 1 already caught it
- Your job is to classify everything else accurately
- Be conservative - when in doubt, classify as HIGH_DISTRESS, not NORMAL

Respond with ONLY the classification word:
PANIC
GRIEF
HIGH_DISTRESS
NORMAL"""

    try:
        response = model.generate_content(
            assessment_prompt,
            generation_config={
                "temperature": 0.1,  # Low temperature for consistent classification
                "max_output_tokens": 30
            },
            request_options={"timeout": 10}
        )

        assessment = response.text.strip().upper()
        logger.info(
            f"Response type assessment: {assessment} | Emotions: {emotion_summary} | Message: {user_text[:50]}...")

        # Extract the response type from the response
        valid_types = ["PANIC", "GRIEF", "HIGH_DISTRESS", "NORMAL"]
        for resp_type in valid_types:
            if resp_type in assessment:
                return resp_type.lower()

        # Fallback: If Gemini doesn't classify clearly, use emotions
        if emotions and len(emotions) > 0:
            top_emotion = emotions[0].get('label', '').lower()
            score = emotions[0].get('score', 0)
            if score > 0.7:
                if top_emotion == 'fear':
                    logger.info(f"Fallback to panic based on high fear emotion")
                    return "panic"
                elif top_emotion == 'sadness':
                    logger.info(f"Fallback to high_distress based on high sadness emotion")
                    return "high_distress"
        
        return "normal"

    except Exception as e:
        logger.error(f"Response type assessment failed: {str(e)}")
        # Fallback: Use RoBERTa emotions to make a safe guess
        if emotions and len(emotions) > 0:
            top_emotion = emotions[0].get('label', '').lower()
            score = emotions[0].get('score', 0)
            if score > 0.6:
                if top_emotion == 'fear':
                    logger.info(f"Exception fallback to panic based on {top_emotion}")
                    return "panic"
                elif top_emotion in ['sadness', 'anger']:
                    logger.info(f"Exception fallback to high_distress based on {top_emotion}")
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

**CRITICAL INSTRUCTIONS - HOTLINE HANDLING**:
- WHENEVER you give hotlines/resources, ONLY use the ones PROVIDED BELOW
- DO NOT suggest any other hotlines from your training knowledge
- DO NOT add, mention, or recommend any hotlines that are not explicitly listed below
- Repeat back EXACTLY the hotlines I gave you - no alternatives
- If user asks for hotlines, give ONLY these specific numbers

**CRITICAL INSTRUCTIONS**:
- DO NOT repeat or echo back what they said
- DO NOT start with casual interjections like "Hey!" or "Oh!"
- DO take this seriously and respond with genuine concern
- Style: {tone_config['style']}
- Approach: {tone_config['approach']}

**Your task** (be concise and complete):
1. Validate their feelings with genuine concern
2. Emphasize their life has value
3. Provide support and hope
4. Include ONLY the crisis resources below - these are the ONLY resources to mention
5. End with reassurance they're not alone

**Response length**: This is a crisis - respond with appropriate depth and care. Be thorough but not verbose. Use length that matches severity.

Crisis Resources (ONLY these resources - do not add others):
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
            reply = safe_get_response_text(response)
            if reply:
                return add_breaks(reply)
            else:
                raise Exception("Empty response from Gemini")
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

**CRITICAL INSTRUCTIONS**:
- DO NOT repeat or echo back what they said
- DO NOT start with "Hey!" or similar casual greetings
- DO respond with deep compassion
- Style: {tone_config['style']}
- Approach: {tone_config['approach']}

**Your task** (be concise and complete):
1. Respond with deep compassion and understanding
2. Acknowledge the weight of their loss
3. Validate grief as a form of love
4. Offer gentle presence and honor their memories
5. Complete your thoughts fully

**Response length**: Grief requires thoughtful, unhurried response. Match the depth of their loss. Be thorough - don't rush.

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
            grief_reply = safe_get_response_text(response)
            if grief_reply:
                return add_breaks(grief_reply)
            else:
                raise Exception("Empty response from Gemini")
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

**CRITICAL INSTRUCTIONS**:
- DO NOT repeat or echo back what they said
- DO NOT start with "Hey!" or casual greetings
- DO provide immediate grounding support
- Style: {tone_config['style']}
- Approach: {tone_config['approach']}

**Your task** (be concise and complete):
1. Respond with immediate grounding and support
2. Guide them through calming breathing: "Breathe in—1, 2, 3, 4. Hold—1, 2, 3, 4. Out—1, 2, 3, 4."
3. Reassure them they're safe and this will pass
4. Use grounding techniques (5 senses, etc.)
5. Complete your thoughts fully

**Response length**: Panic needs focused, direct support. Be concise but thorough - help them ground NOW. Don't ramble.

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
            panic_reply = safe_get_response_text(response)
            if panic_reply:
                return add_breaks(panic_reply)
            else:
                raise Exception("Empty response from Gemini")
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

**CRITICAL INSTRUCTIONS - HOTLINE HANDLING**:
- WHENEVER you give hotlines/resources, ONLY use the ones PROVIDED BELOW
- DO NOT suggest any other hotlines from your training knowledge
- DO NOT add, mention, or recommend any hotlines that are not explicitly listed below
- Repeat back EXACTLY the hotlines I gave you - no alternatives
- If user asks for hotlines, give ONLY these specific numbers

**CRITICAL INSTRUCTIONS**:
- DO NOT repeat or echo back what they said
- DO NOT start with "Hey!" or casual greetings
- DO respond with genuine concern
- Style: {tone_config['style']}
- Approach: {tone_config['approach']}

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
            distress_reply = safe_get_response_text(response)
            if distress_reply:
                return add_breaks(distress_reply)
            else:
                raise Exception("Empty response from Gemini")
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

**CRITICAL INSTRUCTIONS - HOTLINE HANDLING**:
- If user asks for hotlines/resources, ONLY provide these Philippines hotlines:
  • National Center for Mental Health Crisis Hotline: 1553 (landline nationwide, toll-free) or 0917-899-8727
  • HOPELINE Philippines: 2919 (Globe/TM toll-free) or (02) 8804-4673
  • In Touch Community Services: (02) 8893-7603 or 0917-800-1123 (24/7 free crisis line)
- DO NOT suggest any other hotlines from your training knowledge
- DO NOT add, mention, or recommend any hotlines that are not explicitly listed above

**CRITICAL INSTRUCTIONS**:
- DO NOT repeat or echo back what they said
- DO NOT start with "Hey!" or "Oh!" or similar interjections
- DO match the tone: Style: {tone_config['style']} | Approach: {tone_config['approach']}
- DO respond conversationally as a friend would
- DO be concise and genuine

**Your task** (be concise and complete):
1. Respond naturally and warmly in the specified tone
2. Show you understand their situation
3. Offer genuine support or practical suggestions
4. Ask a thoughtful follow-up question
5. Complete your thoughts fully

**Response length**: Keep it natural. Short and sweet for casual chat, longer if they need advice. Don't force length - be genuine and conversational.

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
            reply = safe_get_response_text(response)
            if reply:
                return add_breaks(reply)
            else:
                raise Exception("Empty response from Gemini")
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
    recent_texts = [item['text'] for item in history[-8:] if item.get('text') and item.get('role') == 'user']
    recent_texts.append(latest_user)  # Only add user's latest message, not bot's
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
        # Use word boundary matching to avoid false positives
        if re.search(r'\b' + re.escape(key) + r'\b', text_all):
            coping_set.add(val)
    existing["coping"] = list(coping_set)[:8]
    
    if not existing.get("trajectory"):
        if any(w in text_all for w in FEELING_OVERWHELMED):
            existing["trajectory"] = "feeling drained and overwhelmed"
        elif any(w in text_all for w in FEELING_BETTER):
            existing["trajectory"] = "starting to feel better"
    
    return existing