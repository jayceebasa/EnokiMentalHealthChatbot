from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import pipeline

# ------------------ Models ------------------

class TextRequest(BaseModel):
    text: str

class EmotionResult(BaseModel):
    label: str
    score: float

class EmotionResponse(BaseModel):
    emotions: List[EmotionResult]

# ------------------ ML Models ------------------

# Emotion classifier
emotion_classifier = pipeline(
    "text-classification",
    model="SamLowe/roberta-base-go_emotions",
    tokenizer="SamLowe/roberta-base-go_emotions",
    top_k=None
)

# ------------------ API ------------------

app = FastAPI()

@app.get("/")
def health():
    return {
        "status": "healthy",
        "emotion_model": "SamLowe/roberta-base-go_emotions"
    }

@app.post("/predict_all", response_model=EmotionResponse)
def predict_all(req: TextRequest):
    """Returns emotion predictions only - sarcasm detection moved to Gemini"""
    try:
        emo_raw = emotion_classifier(req.text)
        if isinstance(emo_raw, list) and emo_raw and isinstance(emo_raw[0], list):
            emo_raw = emo_raw[0]
        emotions = [EmotionResult(label=e["label"], score=e["score"]) for e in emo_raw]
        
        return EmotionResponse(emotions=emotions)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Emotion prediction failed: {e}")

@app.post("/emotions", response_model=EmotionResponse)
def predict_emotions(req: TextRequest):
    """Alternative endpoint for emotion prediction only"""
    return predict_all(req)
