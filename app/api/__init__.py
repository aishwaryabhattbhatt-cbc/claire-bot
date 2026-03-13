from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, UploadFile, HTTPException

from app.schemas import FileUploadResponse, InstructionsResponse, InstructionsUpdateRequest
from app.services import generate_job_id, save_uploaded_file
from app.services.parser_service import DocumentParserService
from app.services.llm_service import review_with_llm
from app.services.sheets_service import GoogleSheetsWriterService
from app.services.instructions_service import InstructionsService
from app.services.rule_engine import run_deterministic_checks
from app.services.reference_service import get_reference_context
from app.core.config import get_settings

router = APIRouter()
parser_service = DocumentParserService()
instructions_service = InstructionsService()
settings = get_settings()

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".doc"}


@router.post("/review", response_model=FileUploadResponse)
async def upload_report(
    file: UploadFile = File(...),
    report_language: str = Form(...),
    comparison_mode: bool = Form(False),
    benchmark_file: Optional[UploadFile] = File(None),
) -> FileUploadResponse:
    """
    Upload a report for review.

    Args:
        file: Main report file (PDF, PPTX, DOCX)
        report_language: 'French' or 'English'
        comparison_mode: If True, benchmark_file is required
        benchmark_file: Optional benchmark file for comparison

    Returns:
        FileUploadResponse with job_id
    """
    # Validate report file
    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Validate language
    if report_language not in ["French", "English"]:
        raise HTTPException(status_code=400, detail="Language must be 'French' or 'English'")

    # Generate job ID
    job_id = generate_job_id()

    # Save report file
    report_content = await file.read()
    report_path = save_uploaded_file(report_content, file.filename, job_id, "report")

    # Parse the report immediately (V1 - sync parsing)
    try:
        parsed_report = parser_service.parse_document(report_path, report_language)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to parse document: {str(e)}")

    parsed_benchmark = None

    # Save benchmark file if provided
    if comparison_mode and benchmark_file:
        if not benchmark_file.filename:
            raise HTTPException(status_code=400, detail="Benchmark file name is required")

        bench_ext = Path(benchmark_file.filename).suffix.lower()
        if bench_ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Benchmark file type invalid. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            )

        benchmark_content = await benchmark_file.read()
        benchmark_path = save_uploaded_file(
            benchmark_content, benchmark_file.filename, job_id, "benchmark"
        )

        # Parse benchmark file
        try:
            parsed_benchmark = parser_service.parse_document(benchmark_path, "English")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to parse benchmark: {str(e)}")
    elif comparison_mode and not benchmark_file:
        raise HTTPException(
            status_code=400, detail="Benchmark file required when comparison_mode is True"
        )

    # Deterministic checks first
    findings = run_deterministic_checks(parsed_report, parsed_benchmark)

    # Run LLM review (Gemini or OpenAI based on config)
    findings_count = None
    llm_status = "skipped"
    llm_error = None
    instruction_payload = instructions_service.get_instructions()
    if report_language == "French":
        instructions_text = instruction_payload.get("french_instructions", "")
    else:
        instructions_text = instruction_payload.get("english_instructions", "")
    try:
        llm_findings = review_with_llm(
            parsed_report,
            parsed_benchmark,
            instructions_text=instructions_text,
            reference_context=get_reference_context(),
        )
        findings.extend(llm_findings)
        findings = _dedupe_findings(findings)
        findings_count = len(findings)
        llm_status = "success"
    except Exception as e:
        # If LLM is not configured or fails, keep deterministic findings
        findings = _dedupe_findings(findings)
        findings_count = len(findings)
        llm_status = "failed"
        llm_error = f"LLM review failed: {str(e)}"

    sheets_url = None
    sheets_status = "skipped"
    sheets_error = None
    if settings.enable_sheets_writer and findings_count is not None:
        try:
            sheets_writer = GoogleSheetsWriterService()
            sheet_result = sheets_writer.write_findings(findings)
            sheets_url = sheet_result.get("spreadsheet_url")
            sheets_status = "success"
        except Exception as e:
            sheets_url = None
            sheets_status = "failed"
            sheets_error = f"Sheets write failed: {str(e)}"

    return FileUploadResponse(
        job_id=job_id,
        file_name=file.filename,
        report_language=report_language,
        comparison_mode=comparison_mode,
        status="parsed",
        message=f"File uploaded and parsed successfully. Found {parsed_report.metadata.total_pages} pages.",
        findings_count=findings_count,
        findings=findings,
        sheets_url=sheets_url,
        sheets_status=sheets_status,
        sheets_error=sheets_error,
        llm_status=llm_status,
        llm_error=llm_error,
    )


@router.get("/instructions", response_model=InstructionsResponse)
def get_instructions() -> InstructionsResponse:
    payload = instructions_service.get_instructions()
    return InstructionsResponse(
        english_instructions=payload.get("english_instructions", ""),
        french_instructions=payload.get("french_instructions", ""),
    )


@router.put("/instructions", response_model=InstructionsResponse)
def update_instructions(payload: InstructionsUpdateRequest) -> InstructionsResponse:
    saved = instructions_service.save_instructions(
        payload.english_instructions,
        payload.french_instructions,
    )
    return InstructionsResponse(
        english_instructions=saved.get("english_instructions", ""),
        french_instructions=saved.get("french_instructions", ""),
    )


def _dedupe_findings(findings: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in findings:
        key = (
            item.get("page_number"),
            item.get("language"),
            item.get("issue_detected"),
            item.get("proposed_change"),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


@router.get("/review/{job_id}")
def get_review_status(job_id: str) -> dict:
    """Get status of a review job (placeholder for step 3+)"""
    return {"job_id": job_id, "status": "pending", "message": "Review in progress. Check back soon."}
