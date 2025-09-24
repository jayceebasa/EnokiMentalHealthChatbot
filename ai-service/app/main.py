from typing import List, Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from transformers import pipeline, AutoTokenizer, AutoModelForSeq2SeqLM
import re
import os
import json
import math
import csv

# ------------------ Models ------------------

class TextRequest(BaseModel):
    text: str

class EmotionResult(BaseModel):
    label: str
    score: float

class MultiPredictionResponse(BaseModel):
    emotions: List[EmotionResult]
    sarcasm: str
    sarcasm_score: float
    sarcasm_sources: List[str]

class FeatureResponse(BaseModel):
    sarcasm: str
    sarcasm_score: float
    features: dict
    sources: List[str]

class BatchRequest(BaseModel):
    texts: List[str]
    debug: Optional[bool] = False

class BatchPredictionResponse(BaseModel):
    results: List[MultiPredictionResponse]

# ------------------ ML Models ------------------

# Emotion classifier
emotion_classifier = pipeline(
    "text-classification",
    model="SamLowe/roberta-base-go_emotions",
    tokenizer="SamLowe/roberta-base-go_emotions",
    top_k=None
)

# Irony classifier
irony_pipeline = pipeline(
    "text-classification",
    model="cardiffnlp/twitter-roberta-base-irony"
)
IRONY_LABEL_MAP = {"LABEL_0": "not_sarcastic", "LABEL_1": "sarcastic"}

# T5 sarcasm model
t5_tokenizer = AutoTokenizer.from_pretrained(
    "mrm8488/t5-base-finetuned-sarcasm-twitter")
t5_model = AutoModelForSeq2SeqLM.from_pretrained(
    "mrm8488/t5-base-finetuned-sarcasm-twitter")
ENABLE_T5 = True

# Thresholds
STRICT_SARCASM_THRESHOLD = float(os.getenv("SARCASM_STRICT_THRESHOLD", 0.50))  # lowered to improve recall
POSSIBLE_SARCASM_THRESHOLD = float(os.getenv("SARCASM_POSSIBLE_THRESHOLD", 0.28))  # slightly raised to keep band meaningful
ENABLE_SARCASM_DEBUG = os.getenv("SARCASM_DEBUG", "false").lower() in {"1","true","yes","on"}

# Heuristic weight overrides via env (fallback to defaults used previously)
def _w(env_key: str, default: float) -> float:
    try:
        return float(os.getenv(env_key, default))
    except ValueError:
        return default

WEIGHT_IRONY_FLOOR = _w("SARCASM_WEIGHT_IRONY_FLOOR", 0.05)
WEIGHT_T5 = _w("SARCASM_WEIGHT_T5", 0.6)
WEIGHT_CONTRADICTION = _w("SARCASM_WEIGHT_CONTRADICTION", 0.45)
WEIGHT_STYLE = _w("SARCASM_WEIGHT_STYLE", 0.35)
WEIGHT_POS_NEG_COMBO = _w("SARCASM_WEIGHT_POS_NEG_COMBO", 0.15)
WEIGHT_POS_BOOST = _w("SARCASM_WEIGHT_POS_BOOST", 0.18)
WEIGHT_ELONGATED = _w("SARCASM_WEIGHT_ELONGATED", 0.08)
WEIGHT_BORDERLINE = _w("SARCASM_WEIGHT_BORDERLINE", 0.03)

# Logistic calibration (blending) support
_logistic_raw = os.getenv("SARCASM_LOGISTIC_COEFFS")  # JSON: {"bias": b, "irony_score": c1, ...}
LOGISTIC_COEFFS = None
if _logistic_raw:
    try:
        LOGISTIC_COEFFS = json.loads(_logistic_raw)
    except Exception:
        LOGISTIC_COEFFS = None
BLEND_ALPHA = _w("SARCASM_BLEND_ALPHA", 0.5)  # fraction heuristic; (1-alpha) logistic

# Feature logging path (append CSV if provided)
FEATURE_LOG_PATH = os.getenv("FEATURE_LOG_PATH")

# ------------------ Lexicons ------------------

NEG_EVENTS = [
    # original
    "spilled", "spill", "lost", "cancelled", "canceled", "delayed", "delay", "crashed", "crash", "stopped", "jammed",
    "died", "forgot", "broken", "broke", "missed", "late", "ticket", "flat tire", "battery", "dead battery",
    "fired", "divorce", "hospital", "overworked", "burned out", "printer", "jam", "cancellation", "error",
    "crash", "issue", "problem", "ticket", "fine"
]

POS_EXAGG = [
    # original + expanded variants / hyperbolic cues
    "best day ever", "living the dream", "just what i needed", "absolutely perfect",
    "so amazing", "so wonderful", "thrilled beyond words", "truly blessed",
    "couldn't be happier", "couldnt be happier", "fantastic", "amazing", "wonderful",
    "awesome", "just great", "perfect", "lovely", "so glad", "could not be happier",
    "could not be better", "dream come true"
]

NEG_REGEX = re.compile("|".join(re.escape(p) for p in NEG_EVENTS), re.IGNORECASE)
POS_REGEX = re.compile("|".join(re.escape(p) for p in POS_EXAGG), re.IGNORECASE)
ELONGATED = re.compile(r"(.)\1{3,}")  # 4+ same char
PROFANITY = {"fucking","damn","shit","crap","hell","pissed","bitch","asshole","bullshit","wtf"}

# ------------------ Utilities ------------------

def count_negatives(text: str) -> int:
    return len(NEG_REGEX.findall(text))

def list_negatives(text: str) -> List[str]:
    return sorted({m.group(0).lower() for m in NEG_REGEX.finditer(text)})

def extra_positive_boost(text: str) -> float:
    return 0.4 if POS_REGEX.search(text.lower()) else 0.0

def t5_predict(text: str) -> str:
    prompt = f"sarcasm: {text}"
    ids = t5_tokenizer.encode(prompt, return_tensors="pt", max_length=256, truncation=True)
    out = t5_model.generate(ids, max_length=8)
    decoded = t5_tokenizer.decode(out[0], skip_special_tokens=True).lower()
    return "sarcastic" if "sarcas" in decoded else "not_sarcastic"

# ------------------ Sarcasm Aggregation ------------------

def aggregate_sarcasm(text: str, emotions: List[EmotionResult]):
    features = {}
    lower = text.lower()

    # Base features
    neg_count = count_negatives(lower)
    neg_hits = list_negatives(lower)
    pos_boost = extra_positive_boost(text)
    elongated = bool(ELONGATED.search(text))
    profanity_hit = any(w in lower for w in PROFANITY)
    upper_ratio = sum(c.isupper() for c in text) / max(1, sum(c.isalpha() for c in text))

    # Emotion scores
    pos_emotion = sum(e.score for e in emotions if e.label in {"joy","love","admiration","excitement","amusement"}) + pos_boost
    neg_emotion = sum(e.score for e in emotions if e.label in {"sadness","disappointment","annoyance","anger","grief","fear"})

    # Irony model
    irony_raw = irony_pipeline(text)
    top_irony = max(irony_raw, key=lambda x: x["score"])
    irony_label = IRONY_LABEL_MAP.get(top_irony["label"], "not_sarcastic")
    sources = []
    if irony_label == "sarcastic":
        sources.append(f"irony_model:{top_irony['score']:.2f}")

    # T5 model
    t5_label = t5_predict(text)
    if t5_label == "sarcastic":
        sources.append("t5_model")

    # Heuristic triggers
    contradiction = (pos_emotion >= 0.15 and neg_count >= 1) or (pos_emotion >= 0.10 and neg_count >= 2)
    style_trigger = (elongated and neg_count >= 1) or (profanity_hit and neg_count >= 1) or (POS_REGEX.search(lower) and neg_count >= 1)

    # New composite mild trigger: positive hyperbole phrase + at least one negative event even if emotion contrast small
    pos_neg_combo = bool(POS_REGEX.search(lower) and neg_count >= 1 and not contradiction)

    if contradiction: sources.append("heuristic_contrast")
    if style_trigger: sources.append("heuristic_style")
    if pos_neg_combo: sources.append("heuristic_pos_neg_combo")
    if elongated: sources.append("elongation")
    if profanity_hit: sources.append("profanity")
    if neg_hits: sources.append(f"neg_hits:{len(neg_hits)}")
    if pos_boost: sources.append("pos_hyperbole")

    # Aggregate score (normalized weights)
    base_prob = 0.0
    if irony_label=="sarcastic":
        base_prob += top_irony["score"]
        if top_irony["score"] < 0.55:
            base_prob += WEIGHT_IRONY_FLOOR
    if t5_label=="sarcastic":
        base_prob += WEIGHT_T5
    if contradiction:
        base_prob += WEIGHT_CONTRADICTION
    if style_trigger:
        base_prob += WEIGHT_STYLE
    if pos_neg_combo:
        base_prob += WEIGHT_POS_NEG_COMBO
    if pos_boost and not contradiction and not pos_neg_combo:
        base_prob += WEIGHT_POS_BOOST
    if elongated:
        base_prob += WEIGHT_ELONGATED
    # Borderline irony assist: if irony indicates sarcasm but total still just below strict and there is at least one negative cue
    # we add a small bump to reduce near-miss false negatives.
    if irony_label == "sarcastic" and neg_count >= 1:
        # compute provisional score before assist
        provisional = base_prob
        if provisional < STRICT_SARCASM_THRESHOLD and (STRICT_SARCASM_THRESHOLD - provisional) <= 0.06:
            base_prob += WEIGHT_BORDERLINE
            sources.append("assist_borderline_irony")
    heuristic_score = min(1.0, base_prob)

    # Logistic calibration blending (optional)
    logistic_prob = None
    if LOGISTIC_COEFFS:
        try:
            z = LOGISTIC_COEFFS.get("bias", 0.0)
            # features used for logistic must be present below
            logistic_features = {
                "irony_score": top_irony["score"],
                "t5_flag": 1.0 if t5_label == "sarcastic" else 0.0,
                "pos_emotion": pos_emotion,
                "neg_emotion": neg_emotion,
                "neg_count": float(neg_count),
                "pos_boost": pos_boost,
                "elongated": 1.0 if elongated else 0.0,
                "profanity": 1.0 if profanity_hit else 0.0,
                "contradiction": 1.0 if contradiction else 0.0,
                "style_trigger": 1.0 if style_trigger else 0.0,
                "pos_neg_combo": 1.0 if pos_neg_combo else 0.0
            }
            for k, v in logistic_features.items():
                if k in LOGISTIC_COEFFS:
                    z += LOGISTIC_COEFFS[k] * v
            logistic_prob = 1.0 / (1.0 + math.exp(-z))
            sarcasm_score = min(1.0, BLEND_ALPHA * heuristic_score + (1.0 - BLEND_ALPHA) * logistic_prob)
            sources.append("logistic_blend")
        except Exception:
            sarcasm_score = heuristic_score
    else:
        sarcasm_score = heuristic_score

    # Threshold evaluation
    if sarcasm_score >= STRICT_SARCASM_THRESHOLD:
        final_label = "sarcastic"
    elif sarcasm_score >= POSSIBLE_SARCASM_THRESHOLD:
        final_label = "possibly_sarcastic"
    else:
        final_label = "not_sarcastic"

    if not sources:
        sources.append("none_triggered")
    if ENABLE_SARCASM_DEBUG:
        sources.append("features:" + json.dumps({
            "base_prob": base_prob,
            "pos_emotion": pos_emotion,
            "neg_count": neg_count,
            "irony_score": top_irony["score"],
            "contradiction": contradiction,
            "style_trigger": style_trigger,
            "pos_neg_combo": pos_neg_combo,
            "margin_to_strict": round(STRICT_SARCASM_THRESHOLD - sarcasm_score, 4),
            "margin_to_possible": round(POSSIBLE_SARCASM_THRESHOLD - sarcasm_score, 4)
        }))

    # expose internal feature set for advanced usage
    feature_dict = {
        "pos_emotion": pos_emotion,
        "neg_emotion": neg_emotion,
        "neg_count": neg_count,
        "pos_boost": pos_boost,
        "elongated": elongated,
        "profanity": profanity_hit,
        "upper_ratio": upper_ratio,
        "irony_score": top_irony["score"],
        "irony_label": irony_label,
        "t5_label": t5_label,
        "contradiction": contradiction,
        "style_trigger": style_trigger,
        "pos_neg_combo": pos_neg_combo,
        "heuristic_score": heuristic_score,
        "logistic_prob": logistic_prob,
        "final_score": sarcasm_score
    }
    return final_label, sarcasm_score, sources, feature_dict

# ------------------ API ------------------

app = FastAPI()

@app.get("/")
def health():
    return {
        "status": "healthy",
        "t5_enabled": ENABLE_T5,
        "strict_threshold": STRICT_SARCASM_THRESHOLD,
        "possible_threshold": POSSIBLE_SARCASM_THRESHOLD
    }

@app.post("/predict_all", response_model=MultiPredictionResponse)
def predict_all(req: TextRequest, request: Request):
    try:
        emo_raw = emotion_classifier(req.text)
        if isinstance(emo_raw, list) and emo_raw and isinstance(emo_raw[0], list):
            emo_raw = emo_raw[0]
        emotions = [EmotionResult(label=e["label"], score=e["score"]) for e in emo_raw]
        sarcasm_label, sarcasm_score, sources, features = aggregate_sarcasm(req.text, emotions)

        if FEATURE_LOG_PATH:
            try:
                file_exists = os.path.isfile(FEATURE_LOG_PATH)
                with open(FEATURE_LOG_PATH, 'a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(["text","label","score"] + list(features.keys()))
                    writer.writerow([req.text, sarcasm_label, f"{sarcasm_score:.4f}"] + [features[k] for k in features.keys()])
            except Exception:
                pass

        # Force include features even if debug env off when ?debug=1 (minimal placeholder)
        if request.query_params.get("debug") in {"1","true","yes","on"} and not any(s.startswith("features:") for s in sources):
            sources.append("features:enable_env_SARCASM_DEBUG_for_full_detail")

        return MultiPredictionResponse(
            emotions=emotions,
            sarcasm=sarcasm_label,
            sarcasm_score=sarcasm_score,
            sarcasm_sources=sources
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


@app.post("/predict_features", response_model=FeatureResponse)
def predict_features(req: TextRequest):
    try:
        emo_raw = emotion_classifier(req.text)
        if isinstance(emo_raw, list) and emo_raw and isinstance(emo_raw[0], list):
            emo_raw = emo_raw[0]
        emotions = [EmotionResult(label=e["label"], score=e["score"]) for e in emo_raw]
        sarcasm_label, sarcasm_score, sources, features = aggregate_sarcasm(req.text, emotions)
        return FeatureResponse(
            sarcasm=sarcasm_label,
            sarcasm_score=sarcasm_score,
            features=features,
            sources=sources
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {e}")


@app.post("/predict_batch", response_model=BatchPredictionResponse)
def predict_batch(batch: BatchRequest, request: Request):
    results: List[MultiPredictionResponse] = []
    for text in batch.texts:
        try:
            emo_raw = emotion_classifier(text)
            if isinstance(emo_raw, list) and emo_raw and isinstance(emo_raw[0], list):
                emo_raw = emo_raw[0]
            emotions = [EmotionResult(label=e["label"], score=e["score"]) for e in emo_raw]
            sarcasm_label, sarcasm_score, sources, _ = aggregate_sarcasm(text, emotions)
            if batch.debug and not any(s.startswith("features:") for s in sources):
                sources.append("features:enable_env_SARCASM_DEBUG_for_full_detail")
            results.append(MultiPredictionResponse(
                emotions=emotions,
                sarcasm=sarcasm_label,
                sarcasm_score=sarcasm_score,
                sarcasm_sources=sources
            ))
        except Exception:
            results.append(MultiPredictionResponse(
                emotions=[], sarcasm="error", sarcasm_score=0.0, sarcasm_sources=["processing_error"]
            ))
    return BatchPredictionResponse(results=results)
