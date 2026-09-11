import os
import json
import requests
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings

router = APIRouter()

class ClassifyRequest(BaseModel):
    text: str

class ClassifyResponse(BaseModel):
    category: str
    confidence: float
    reason: str

@router.post("/classify", response_model=ClassifyResponse, summary="Classify document using Gemini")
async def classify_document(request: ClassifyRequest):
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")
    prompt = (
        "Classify the following document text into one of the categories: ICSR, PQC, MI, NOT_RELEVANT. "
        "Return a JSON object with fields: category (one of the four strings), confidence (0-1 float), "
        "and reason (a short explanation).\n\nDocument:\n" + request.text
    )
    payload = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    url = f"https://generativelanguage.googleapis.com/v1/models/{settings.GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    try:
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        text_response = data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        try:
            result = json.loads(text_response)
        except json.JSONDecodeError:
            raise ValueError("Unable to parse Gemini response")
        return ClassifyResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
