from fastapi import APIRouter, UploadFile, File, HTTPException
import fitz  # PyMuPDF

router = APIRouter()

@router.post("/pdf/process", summary="Process PDF and extract text")
async def process_pdf(file: UploadFile = File(...)):
    """Accept a PDF file and return its filename, extracted text, and page count.

    Args:
        file (UploadFile): Uploaded PDF file.

    Returns:
        dict: {"filename": str, "text": str, "page_count": int}
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")
    try:
        contents = await file.read()
        doc = fitz.open(stream=contents, filetype="pdf")
        page_count = doc.page_count
        text = "\n".join([page.get_text() for page in doc])
        return {"filename": file.filename, "text": text, "page_count": page_count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
