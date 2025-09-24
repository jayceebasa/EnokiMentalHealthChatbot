import os
import google.generativeai as genai
from typing import List, Optional, Dict, Any

# Hard baseline banned opening stems to reduce "first time" feel.
BASELINE_BANNED_OPENINGS = [
    "it sounds like",
    "it seems like",
    "i'm sorry",
    "that sounds",
    "that must be",
    "i hear",
]

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Pick a model (flash = faster, pro = smarter)
model = genai.GenerativeModel("gemini-1.5-flash")


def generate_reply(
    user_text: str,
    emotions: list[dict[str, float]],
    preferences: dict,
    history: Optional[List[dict]] = None,
    summary: Optional[str] = None,
    memory: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate a reply using Gemini with lightweight conversation memory.

    history: list of dict items like {"role": "user"|"bot", "text": str}
    Only the last several exchanges are included to stay within token limits.
    """

    history = history or []
    # Keep only the last 8 turns (user+bot pairs) for brevity
    trimmed = history[-16:]
    formatted_history_lines = []
    for h in trimmed:
        speaker = "User" if h.get("role") == "user" else "Enoki"
        txt = h.get("text", "").strip().replace("\n", " ")
        formatted_history_lines.append(f"{speaker}: {txt}")
    formatted_history = "\n".join(formatted_history_lines) if formatted_history_lines else "(No prior context)"

    emotions_compact = ", ".join(
        f"{e.get('label')}({e.get('score'):.2f})" for e in emotions[:6] if e.get('label')
    ) or "none"

    # Memory unpack
    memory = memory or {}
    stressor = memory.get("stressor") or "unspecified"
    motivation = memory.get("motivation") or "unspecified"
    coping = memory.get("coping") or []
    trajectory = memory.get("trajectory") or "unknown"
    openings_used = memory.get("bot_openings", [])[-4:]
    openings_block = ", ".join(openings_used) if openings_used else "(none tracked)"

    tone = preferences.get("tone", "empathetic")
    language = preferences.get("language", "en")

    # Early mock path for reliable local testing without hitting external API
    if os.getenv("FAKE_LLM", "0") == "1":
        ut_l_fake = (user_text or "").lower()
        grief_words = ["rainbow bridge", "pass the bridge", "cross the bridge", "be with him again", "be with her again", "join him", "join her", "died", "passed", "funeral", "grief", "mourning", "memorial", "pet", "dog", "cat", "tiger"]
        risk_words = ["end my life", "end it", "kill myself", "suicide", "self harm", "self-harm"] + grief_words
        is_grief_fake = any(k in ut_l_fake for k in grief_words)
        is_risk_fake = any(k in ut_l_fake for k in risk_words)

        def _cb_from_context() -> str:
            for key in ["stressor", "motivation", "coping", "trajectory"]:
                val = (memory or {}).get(key)
                if val:
                    head = val if isinstance(val, str) else (", ".join(val) if isinstance(val, list) else str(val))
                    words = head.strip().split()
                    if words:
                        return " ".join(words[:12])
            if summary:
                sw = summary.strip().split()
                if sw:
                    return " ".join(sw[:12])
            if user_text:
                return " ".join(user_text.strip().split()[:12])
            return "what you mentioned earlier"
        cb = _cb_from_context()
        if is_risk_fake or is_grief_fake:
            name_hint = "Tiger" if "tiger" in ut_l_fake else "them"
            reply = (f"That love for {name_hint} runs deep, and it hurts—that makes sense. If a hard wave is hitting, we can slow it down together: a few steady breaths, hand on your heart, maybe holding a photo. "
                     f"If part of you is thinking about harm, could you reach someone you trust right now or a local crisis line? You deserve support. I’m here with you.")
            return reply
        return (f"Let’s build on {cb} for a moment. What feels like the smallest next move that would ease things, even a little?")

    # Derive turn number (user turns) to modulate style
    user_turns = sum(1 for h in history if h.get("role") == "user") + 1

    # Detect grief / risk / high-distress to adapt length and tone
    ut_l = (user_text or "").lower()
    risk_keywords = [
        "end my life", "end it", "kill myself", "suicide", "self harm", "self-harm",
        "be with him again", "be with her again", "join him", "join her", "pass the bridge", "cross the bridge",
    ]
    grief_keywords = ["loss", "passed", "died", "funeral", "grief", "mourning", "memorial", "eulogy", "pet", "dog", "cat", "tiger"]
    is_risk = any(k in ut_l for k in risk_keywords)
    is_grief = any(k in ut_l for k in grief_keywords)
    # Emotion-aware distress signal
    distress_labels = {"sadness", "grief", "despair", "remorse", "guilt", "fear", "anxiety", "lonely", "hopelessness"}
    high_distress = any((e.get('label','').lower() in distress_labels) and (float(e.get('score', 0)) >= 0.35) for e in emotions)

    style_profile = "warm_longer" if (is_risk or is_grief or high_distress) else "concise"
    # Set word and sentence guidance
    if style_profile == "warm_longer":
        word_limit = 160
        sent_min, sent_max = 3, 5
    else:
        word_limit = 95
        sent_min, sent_max = 2, 4

    continuity_instruction = (
        "Ongoing conversation: no re-introductions; weave in earlier specifics (but avoid naming them as 'stressor', 'coping strategies', or 'trajectory'). Avoid generic empathy templates." if formatted_history_lines else "First turn: gently invite sharing."
    )

    # Collect recent bot opening stems (first 4 words) directly from history to enforce variation
    recent_bot_openings: List[str] = []
    for h in reversed(trimmed):
        if h.get("role") == "bot":
            words = h.get("text", "").strip().split()
            if words:
                stem = " ".join(words[:4]).lower()
                if stem not in recent_bot_openings:
                    recent_bot_openings.append(stem)
        if len(recent_bot_openings) >= 5:
            break
    banned_list = recent_bot_openings[:5]
    # Merge dynamic stems with baseline for instruction display only
    merged_for_display = []
    seen = set()
    for stem in banned_list + BASELINE_BANNED_OPENINGS:
        if stem not in seen:
            seen.add(stem)
            merged_for_display.append(stem)
    banned_display = "; ".join(merged_for_display) if merged_for_display else "(none)"

    # Additional guidance becomes stricter after a few turns
    progression_rules = "" if user_turns <= 2 else (
        "AFTER INITIAL PHASE: Do NOT open with any of these previously used stems or clichés: "
        + banned_display
        + ". Avoid starts like 'That sounds', 'That must be', 'It can be hard', 'I'm sorry to hear'. Begin instead with a concise, specific callback (e.g., referencing staying late, supporting family, or coping attempts) before moving forward."
    )

    summary_block = f"Conversation summary (for context, do not repeat verbatim):\n{summary}\n\n" if summary else ""

    prompt = f"""
    SYSTEM ROLE: You are Enoki, a supportive, trauma-aware, culturally sensitive mental health companion (not a clinician). You provide emotional validation and gentle guidance.

    Conversation history (most recent last):\n{formatted_history}

    {summary_block}

        Structured memory (do not parrot verbatim; use only to tailor response):
            - Primary stressor: {stressor}
            - Motivation: {motivation}
            - Coping strategies mentioned: {', '.join(coping) if coping else 'none'}
            - Emotional trajectory: {trajectory}
            - Recent opening phrases used: {openings_block}

    New user input: "{user_text}"\n
    Detected emotions (top): {emotions_compact}
    User preferences: tone={tone}, language={language}

    SAFETY & SARCASM CHECK:
    1. First, silently assess: sarcasm? self-harm risk? crisis indicators? (Do NOT output a list—integrate naturally.)
    2. If self-harm / suicidal ideation is present: respond with deep empathy, validate, and encourage reaching a helpline / trusted person. Avoid mandatory reporting tone. No hotline numbers unless clearly appropriate.

    STYLE & BEHAVIOR RULES:
    - {continuity_instruction}
    - {progression_rules}
    - First sentence must reference a concrete prior element (choose ONE): a specific pressure, why the user cares, a coping attempt, or a recent emotional shift—NOT a generic empathy template. Avoid clinical labels.
    - Do NOT start with: It/That sounds | It/That must be | I'm sorry | I hear | It seems (unless user explicitly used those words asking for validation).
    - Use contractions and natural, plain language. Keep it human and warm; no lists, no headings.
    - Keep reply around {word_limit} words (±20%), {sent_min}–{sent_max} sentences total, unless user explicitly asks for more detail.
    - Vary structure; avoid mirroring the user's sentence order exactly.
    - If sarcasm detected, address underlying feeling indirectly (no explicit 'sarcasm' label).
    - No diagnosis, no promises, no clinical jargon. Never say terms like 'stressor', 'coping strategies', 'emotional trajectory' in the reply.
    - Provide at most one gentle next step OR reflective question (not both) and only after validation.
    - If grief/loss is apparent, include the person's/pet's name if shared, acknowledge love and ache without tidy silver-linings, and suggest one small grounding or remembrance ritual (e.g., a few breaths, holding a photo, writing a memory). Presence first; solutions second.
    - If any self-harm risk is present, include a soft, non-judgmental safety nudge (e.g., reaching a trusted person or local hotline) in natural language.

    OUTPUT:
    Provide ONLY the compassionate reply. Do not include analysis labels, stage names (e.g., 'Initial contact'), or meta commentary of any kind.
    """.strip()

    # Attempt generation with Gemini; fallback gracefully on errors (quota/network/OOM)
    try:
        response = model.generate_content(prompt)
        raw = (response.text or "") if hasattr(response, "text") else ""
    except Exception:
        # Build a continuity-aware fallback without generic onboarding tone
        import re as _re
        import hashlib as _hash
        def _build_callback() -> Optional[str]:
            # For grief/risk, anchor to the user's present wording first
            if is_risk or is_grief:
                if user_text:
                    return " ".join(user_text.strip().split()[:12])
            for key in ["stressor", "motivation", "coping", "trajectory"]:
                val = memory.get(key) if memory else None
                if val:
                    head = (val if isinstance(val, str) else (", ".join(val) if isinstance(val, list) else str(val)))
                    words = head.strip().split()
                    if words:
                        return " ".join(words[:12])
            if summary:
                sw = summary.strip().split()
                if sw:
                    return " ".join(sw[:12])
            if user_text:
                return " ".join(user_text.strip().split()[:12])
            return None

        cb = _build_callback()
        # Pick a friendly opening variant deterministically from callback
        def _variant(opening: str) -> str:
            opts = [
                "Let’s build on {} for a moment.",
                "Since {} is front and center, let’s keep it simple.",
                "With {} in mind, we can start small.",
                "Given {}, we’ll take one step at a time.",
            ]
            if not opening:
                return "I’m here with you."
            idx = int(_hash.md5(opening.encode('utf-8')).hexdigest(), 16) % len(opts)
            return opts[idx].format(opening)
        if is_risk or is_grief:
            name_hint = "Tiger" if "tiger" in (user_text or "").lower() else "them"
            first = f"I can feel how much you love {name_hint}. That ache is real."
            raw = first + " If a hard wave is hitting, let’s slow it down together: a few breaths, hand on your heart, maybe holding a photo. If part of you is thinking about harm, could you reach someone you trust right now or a local crisis line? I can stay with you here."
        else:
            first = _variant(cb) if cb else "I’m here with you."
            # Keep concise and include one gentle question OR step
            raw = first + " What feels like the smallest next move that would ease things, even a little?"

    # Post-process to reduce generic first-time vibe if constraints ignored
    import re as _re
    text = raw.strip()
    lowered = text.lower()

    # Helper to build a concrete callback
    def _build_callback() -> Optional[str]:
        # Prefer structured memory
        for key in ["stressor", "motivation", "coping", "trajectory"]:
            val = memory.get(key) if memory else None
            if val:
                head = (val if isinstance(val, str) else (", ".join(val) if isinstance(val, list) else str(val)))
                head_words = head.strip().split()
                if head_words:
                    return " ".join(head_words[:12])
        # Then summary
        if summary:
            sw = summary.strip().split()
            if sw:
                return " ".join(sw[:12])
        # Finally, derive from user_text
        ut = (user_text or "").strip()
        if ut:
            # If "work" present, anchor to it explicitly
            if "work" in ut.lower():
                return "work feeling overwhelming"
            return " ".join(ut.split()[:12])
        return None

    # Split into sentences (lightweight)
    sentences = _re.split(r"(?<=[.!?])\s+|\n+", text)
    first = sentences[0] if sentences else text
    first_l = first.lower()

    banned_frag_present = any(b in first_l for b in BASELINE_BANNED_OPENINGS) or any(
        first_l.startswith(b) for b in BASELINE_BANNED_OPENINGS
    )

    # Helper for varied, more organic opening rephrases
    import hashlib as _hash
    def _varied_open(opening: str) -> str:
        opts = [
            "Let’s build on {} for a moment.",
            "Since {} is front and center, let’s keep it simple.",
            "With {} in mind, we can start small.",
            "Given {}, we’ll take one step at a time.",
        ]
        if not opening:
            return "I’m here with you."
        idx = int(_hash.md5(opening.encode('utf-8')).hexdigest(), 16) % len(opts)
        return opts[idx].format(opening)

    if banned_frag_present:
        callback = _build_callback()
        if callback:
            sentences[0] = _varied_open(callback)
            text = " ".join(s for s in sentences if s)

    # Also soften remaining banned fragments anywhere in the text
    def _soften(_match):
        # Remove the generic empathy stem entirely to avoid robotic tone
        return " "

    # Handle variations with/without 'like'
    text = _re.sub(r"\b[Ii]t\s+sounds(?:\s+like)?\b", _soften, text)
    text = _re.sub(r"\b[Ii]t\s+seems(?:\s+like)?\b", _soften, text)
    text = _re.sub(r"\b[Tt]hat\s+sounds\b", _soften, text)
    text = _re.sub(r"\b[Tt]hat\s+must\s+be\b", _soften, text)
    text = _re.sub(r"\b[Ii]\s+hear\b", "I’m tracking", text)
    text = _re.sub(r"\b[Ii]'m\s+sorry\b", "I’m here with you—", text)

    # Remove clinical/meta-analysis sentences if any leaked
    def _drop_if_clinical(s: str) -> bool:
        bad = [
            "initial contact",
            "user's affect",
            "core concerns",
            "stressor",
            "coping strategies",
            "emotional trajectory",
            "detected emotions",
            "assessment",
            "diagnosis",
        ]
        sl = s.lower()
        return any(b in sl for b in bad)

    sentences2 = [s for s in _re.split(r"(?<=[.!?])\s+|\n+", text) if s]
    sentences2 = [s for s in sentences2 if not _drop_if_clinical(s)]
    # Cap to 3 sentences to avoid rambling
    if len(sentences2) > 3:
        sentences2 = sentences2[:3]
    if sentences2:
        text = " ".join(sentences2)

    # Trim repeated hedging; keep at most one occurrence across the reply
    hedges = ["perhaps", "maybe", "might", "could"]
    for h in hedges:
        # Allow first occurrence, tone down subsequent ones
        pattern = _re.compile(rf"\b{h}\b", flags=_re.IGNORECASE)
        matches = list(pattern.finditer(text))
        if len(matches) > 1:
            # Replace occurrences after the first with softer variants or drop
            start = matches[0].end()
            text = pattern.sub(lambda m: "can" if m.start() <= start else "", text, count=0)

    # If the reply starts with a connective like 'From what you shared,', drop it to feel more direct (robust, case-insensitive)
    text = _re.sub(r"^\s*[\"'“”]?\s*(from what you shared,|based on what you’ve said,|based on what you've said,|given what you’ve shared,|given what you've shared,),\s*",
                   "", text, flags=_re.IGNORECASE)

    # De-robotify common templates
    replacements = [
        (r"\bcompletely understandable\b", "makes sense"),
        (r"\bit's okay to\b", "it’s understandable to"),
        (r"\bthat's incredibly important to you\b", "that really matters to you"),
        (r"\bfeeling wiped out is (totally|completely) understandable\b", "no wonder you feel wiped"),
        (r"\bperhaps\b", "maybe"),
    ]
    for pat, repl in replacements:
        text = _re.sub(pat, repl, text, flags=_re.IGNORECASE)

    # Safety/presence adjustments
    words = len(text.split())
    # If high distress or grief and response is very short, add a presence line
    if (is_risk or is_grief or high_distress) and words < 55:
        text += " We can take this minute by minute. I’m here with you."

    # If potential risk language detected, ensure a gentle safety nudge is present
    lower = text.lower()
    if is_risk and not any(k in lower for k in ["reach", "trusted", "helpline", "hotline", "crisis", "safety", "stay with you"]):
        text += " If part of you is thinking about harm, could you reach someone you trust right now or a local crisis line? You deserve support."

    # Final polishing
    return text.strip()


def update_summary(existing_summary: Optional[str], history: List[dict], latest_user: str, latest_bot: str) -> str:
    """Produce / refine a running summary capturing themes, emotional trajectory, user goals.

    We give only a compact subset of recent turns plus prior summary to keep tokens low.
    """
    recent_pairs = []
    # collect last 4 user/bot exchanges from tail of history
    for item in reversed(history):
        if len(recent_pairs) >= 8:
            break
        recent_pairs.append(f"{item['role']}: {item['text']}")
    recent_pairs_text = "\n".join(reversed(recent_pairs))

    summarization_prompt = f"""
    You are maintaining a structured, compact ongoing summary for a mental health support chat.

    Prior summary (may be empty): {existing_summary or '(none)'}

    Recent dialogue excerpt:
    {recent_pairs_text}

    Latest user message: {latest_user}
    Latest assistant reply: {latest_bot}

    TASK: Produce an updated concise summary (<=80 words) capturing:
    - User emotional trajectory (shifts, intensity)
    - Core concerns / stressors / motivations
    - Any coping strategies mentioned
    - Tone preferences if expressed
    - Risk indicators (use: 'none noted', or brief note)

    Do NOT give advice. Do NOT repeat verbatim sentences. Keep it factual & neutral.
    Return ONLY the summary sentence(s).
    """.strip()

    result = model.generate_content(summarization_prompt)
    return (result.text or existing_summary or "")[:800]


def update_memory(existing: Optional[Dict[str, Any]], history: List[dict], latest_user: str, latest_bot: str) -> Dict[str, Any]:
    """Derive / refine structured memory elements using the model.

    Elements: stressor, motivation, coping (list), trajectory (string), bot_openings (list of phrases used at start)
    """
    existing = existing or {}
    recent_text = []
    for item in reversed(history):
        if len(recent_text) >= 10:
            break
        recent_text.append(f"{item['role']}: {item['text']}")
    recent_text = "\n".join(reversed(recent_text))

    memory_prompt = f"""
    You are extracting structured memory fields from a supportive mental health chat.
    Existing memory (JSON): {existing}

    Recent dialogue excerpt:
    {recent_text}
    Latest user: {latest_user}
    Latest assistant: {latest_bot}

    TASK: Update (or create) a small JSON object with keys:
      stressor (string, main recurring difficulty if any),
      motivation (string, what keeps user going if mentioned),
      coping (array of short strings),
      trajectory (short phrase describing emotional shift),
      bot_openings (array of last 6 distinct assistant opening clause stems, lowercase, no punctuation).

    Respond with ONLY valid JSON.
    """.strip()

    result = None
    try:
        result = model.generate_content(memory_prompt)
    except Exception:
        result = None

    import json as _json
    parsed = {}
    if result and getattr(result, 'text', None):
        try:
            parsed = _json.loads(result.text or '{}')
        except Exception:
            parsed = {}

    # Merge model-derived memory when available
    if parsed:
        for k in ["stressor", "motivation", "trajectory"]:
            if parsed.get(k):
                existing[k] = parsed[k]
        if parsed.get("coping"):
            existing_coping = set(existing.get("coping") or [])
            for c in parsed.get("coping", []):
                if c and c not in existing_coping:
                    existing_coping.add(c)
            existing["coping"] = list(existing_coping)[:10]
        if parsed.get("bot_openings"):
            merged = (existing.get("bot_openings") or []) + [o for o in parsed.get("bot_openings", []) if o]
            # keep last 12 unique preserving order
            seen = []
            for o in merged[-30:]:
                if o not in seen:
                    seen.append(o)
            existing["bot_openings"] = seen[-12:]

    # Heuristic fallback to enrich memory if still sparse
    text_blob = (recent_text + "\n" + (latest_user or "") + "\n" + (latest_bot or "")).lower()

    # Stressor heuristic
    if not existing.get("stressor"):
        if "work" in text_blob or "shift" in text_blob or "overwhelmed" in text_blob:
            existing["stressor"] = existing.get("stressor") or "work pressure / overload"

    # Motivation heuristic
    if not existing.get("motivation"):
        if ("sister" in text_blob and "tuition" in text_blob) or ("pay" in text_blob and "tuition" in text_blob):
            existing["motivation"] = "helping pay sister's college tuition"
        elif "family" in text_blob or "kids" in text_blob:
            existing["motivation"] = existing.get("motivation") or "supporting family"

    # Coping heuristic
    coping_found = set(existing.get("coping") or [])
    def _add_c(item: str):
        if item and item not in coping_found:
            coping_found.add(item)
    if "cutting caffeine" in text_blob or ("caffeine" in text_blob and "3pm" in text_blob):
        _add_c("cutting caffeine after 3pm")
    if "breathing app" in text_blob or "deep breathing" in text_blob:
        _add_c("breathing app / deep breathing")
    if "warm bath" in text_blob:
        _add_c("warm bath")
    if "progressive muscle relaxation" in text_blob:
        _add_c("progressive muscle relaxation")
    if "quiet music" in text_blob or "listening to music" in text_blob:
        _add_c("quiet music")
    if "reading" in text_blob:
        _add_c("light reading")
    if coping_found:
        existing["coping"] = list(coping_found)[:10]

    # Trajectory heuristic
    if not existing.get("trajectory"):
        if "wired" in text_blob and "sleep" in text_blob:
            existing["trajectory"] = "overwhelmed -> wired and exhausted evenings"
        elif "exhausted" in text_blob:
            existing["trajectory"] = existing.get("trajectory") or "sustained exhaustion"

    return existing
