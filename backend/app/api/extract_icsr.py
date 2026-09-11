from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.core.config import settings
from app.services.ai_service import AIService
from app.models.enums import ClassificationCategory
from app.schemas.ai_schemas import ExtractionResult, ExtractResponse

router = APIRouter()

class ICSRExtractRequest(BaseModel):
    document_text: str

@router.post("/extract/icsr", response_model=ExtractResponse, summary="Extract ICSR facts using Gemini")
async def extract_icsr(request: ICSRExtractRequest):
    if not settings.GEMINI_API_KEY:
        raise HTTPException(status_code=500, detail="Gemini API key not configured")
    service = AIService()
    try:
        result, model_used = service._extract_with_gemini(
            document_content=request.document_text,
            category=ClassificationCategory.ICSR,
        )
        response = ExtractResponse(
            success=True,
            document_id=-1,
            category=result.category,
            extraction=result,
            facts_stored=0,
            processing_time=0.0,
            model_used=model_used,
            error=None,
        )
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
