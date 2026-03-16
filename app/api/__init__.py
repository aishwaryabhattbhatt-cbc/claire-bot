from pathlib import Path
from typing import Optional
import logging

from fastapi import APIRouter, File, Form, UploadFile, HTTPException, Query

from app.schemas import FileUploadResponse, InstructionsResponse
from app.services import generate_job_id, save_uploaded_file
from app.services.parser_service import DocumentParserService
from app.services.llm_service import review_with_llm
from app.services.sheets_service import GoogleSheetsWriterService
from app.services.rule_engine import run_deterministic_checks
from app.services.reference_service import (
    get_reference_context,
    get_reference_documents,
    get_reference_glossary_rules,
    reload_reference_documents,
    get_reference_style_rules,
)
from app.prompts.review_prompt import get_fixed_mode_instructions
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()
parser_service = DocumentParserService()
settings = get_settings()

ALLOWED_EXTENSIONS = {".pdf", ".pptx", ".docx", ".doc"}

GLOBAL_REFERENCE_UPLOADS = {
    "benchmark_report": {
        "prefix": "benchmark_report",
        "extensions": {".pptx", ".pdf"},
    },
    "age_references": {
        "prefix": "age_references",
        "extensions": {".pdf", ".docx"},
    },
    "text_preferences": {
        "prefix": "text_preferences",
        "extensions": {".pdf", ".docx"},
    },
}


@router.post("/review", response_model=FileUploadResponse)
async def upload_report(
    file: UploadFile = File(...),
    report_language: str = Form("French"),
    comparison_mode: bool = Form(False),
    prompt_mode: str = Form("french_review"),
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

    allowed_prompt_modes = {"comparison", "french_review"}
    if prompt_mode not in allowed_prompt_modes:
        raise HTTPException(
            status_code=400,
            detail="prompt_mode must be one of: comparison, french_review",
        )

    if prompt_mode == "comparison" and not comparison_mode:
        raise HTTPException(
            status_code=400,
            detail="comparison prompt requires comparison_mode=true",
        )

    if prompt_mode == "french_review" and report_language != "French":
        raise HTTPException(
            status_code=400,
            detail="french_review prompt requires report_language='French'",
        )

    # Generate job ID
    job_id = generate_job_id()
    phase_updates: list[str] = []
    logger.info(f"[{job_id}] Starting review process for report: {file.filename}")
    phase_updates.append("Phase 1: Validating request and receiving report...")
    logger.info(f"[{job_id}] Phase 1: Request validated and report received.")

    # Save report file
    report_content = await file.read()
    report_path = save_uploaded_file(report_content, file.filename, job_id, "report")
    logger.info(f"[{job_id}] Report file saved. Parsing document...")

    # Parse the report immediately (V1 - sync parsing)
    try:
        parsed_report = parser_service.parse_document(report_path, report_language)
        logger.info(f"[{job_id}] Report parsed successfully: {parsed_report.metadata.total_pages} pages")
    except NotImplementedError as e:
        logger.error(f"[{job_id}] Parse error (not implemented): {str(e)}")
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        logger.error(f"[{job_id}] Parse error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to parse document: {str(e)}")
    phase_updates.append("Phase 1: Report parsing completed.")

    parsed_benchmark = None

    # Save benchmark file if provided
    if comparison_mode and benchmark_file:
        logger.info(f"[{job_id}] Phase 2: Processing benchmark file...")
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
            logger.info(f"[{job_id}] Benchmark file parsed: {parsed_benchmark.metadata.total_pages} pages")
        except Exception as e:
            logger.error(f"[{job_id}] Benchmark parse error: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to parse benchmark: {str(e)}")
        phase_updates.append("Phase 2: Benchmark file loaded.")
    elif comparison_mode and not benchmark_file:
        raise HTTPException(
            status_code=400, detail="Benchmark file required when comparison_mode is True"
        )

    # Deterministic checks first
    logger.info(f"[{job_id}] Phase 3: Running deterministic checks...")
    findings = run_deterministic_checks(
        parsed_report,
        parsed_benchmark,
        glossary_rules=get_reference_glossary_rules(),
        style_rules=get_reference_style_rules(),
    )
    logger.info(f"[{job_id}] Deterministic checks found {len(findings)} issues")
    phase_updates.append("Phase 3: Deterministic checks completed.")

    # Run LLM review (Gemini or OpenAI based on config)
    findings_count = None
    llm_status = "skipped"
    llm_error = None
    instructions_text = get_fixed_mode_instructions(prompt_mode)
    logger.info(f"[{job_id}] Phase 4: Starting LLM review (mode: {prompt_mode})...")
    try:
        llm_findings = review_with_llm(
            parsed_report,
            parsed_benchmark,
            instructions_text=instructions_text,
            reference_context=get_reference_context(),
            prompt_mode=prompt_mode,
        )
        findings.extend(llm_findings)
        findings = _dedupe_findings(findings)
        findings_count = len(findings)
        llm_status = "success"
        logger.info(f"[{job_id}] LLM review completed. Total findings: {findings_count}")
        phase_updates.append("Phase 4: LLM review completed.")
    except Exception as e:
        # If LLM is not configured or fails, keep deterministic findings
        findings = _dedupe_findings(findings)
        findings_count = len(findings)
        llm_status = "failed"
        llm_error = f"LLM review failed: {str(e)}"
        logger.warning(f"[{job_id}] LLM review failed: {str(e)}")
        phase_updates.append("Phase 4: LLM review failed. Using deterministic findings only.")

    sheets_url = None
    sheets_status = "skipped"
    sheets_error = None
    if settings.enable_sheets_writer and findings_count is not None:
        logger.info(f"[{job_id}] Phase 5: Writing findings to Google Sheets...")
        try:
            sheets_writer = GoogleSheetsWriterService()
            sheet_result = sheets_writer.write_findings(findings)
            sheets_url = sheet_result.get("spreadsheet_url")
            sheets_status = "success"
            logger.info(f"[{job_id}] Findings written to Google Sheets successfully")
            phase_updates.append("Phase 5: Findings exported to Google Sheets.")
        except Exception as e:
            sheets_url = None
            sheets_status = "failed"
            sheets_error = f"Sheets write failed: {str(e)}"
            logger.error(f"[{job_id}] Google Sheets write failed: {str(e)}")
            phase_updates.append("Phase 5: Google Sheets export failed.")
    
    logger.info(f"[{job_id}] Review process completed. Status: success")
    phase_updates.append("Review process completed successfully.")

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
        phase_updates=phase_updates,
    )


@router.get("/instructions", response_model=InstructionsResponse)
def get_instructions() -> InstructionsResponse:
    return InstructionsResponse(
        comparison_instructions=get_fixed_mode_instructions("comparison"),
        french_instructions=get_fixed_mode_instructions("french_review"),
    )


@router.get("/references")
def get_references() -> dict:
    """Return reference document inventory for UI visualization."""
    docs = get_reference_documents()
    glossary_docs = [d for d in docs if d.get("type") == "glossary"]
    style_docs = [d for d in docs if d.get("type") == "style_guide"]
    other_docs = [d for d in docs if d.get("type") == "reference"]
    return {
        "documents": docs,
        "glossary_documents": glossary_docs,
        "style_guide_documents": style_docs,
        "other_documents": other_docs,
        "global_uploads": _get_global_uploads(docs),
    }


@router.post("/references/global-upload")
async def upload_global_reference(
    category: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Upload or replace global reference files used in workflow."""
    if category not in GLOBAL_REFERENCE_UPLOADS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Allowed: {', '.join(GLOBAL_REFERENCE_UPLOADS.keys())}",
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="File name is required")

    config = GLOBAL_REFERENCE_UPLOADS[category]
    ext = Path(file.filename).suffix.lower()
    if ext not in config["extensions"]:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type for {category}. Allowed: {', '.join(sorted(config['extensions']))}",
        )

    ref_dir = Path(settings.reference_dir)
    ref_dir.mkdir(parents=True, exist_ok=True)

    prefix = config["prefix"]
    for existing in ref_dir.glob(f"{prefix}.*"):
        existing.unlink(missing_ok=True)

    destination = ref_dir / f"{prefix}{ext}"
    content = await file.read()
    destination.write_bytes(content)

    reload_reference_documents()

    docs = get_reference_documents()
    return {
        "status": "success",
        "category": category,
        "file_name": destination.name,
        "global_uploads": _get_global_uploads(docs),
    }


@router.delete("/references/global-upload")
def delete_global_reference(category: str = Query(...)) -> dict:
    """Remove a previously uploaded global reference file for a given category."""
    if category not in GLOBAL_REFERENCE_UPLOADS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid category. Allowed: {', '.join(GLOBAL_REFERENCE_UPLOADS.keys())}",
        )

    ref_dir = Path(settings.reference_dir)
    ref_dir.mkdir(parents=True, exist_ok=True)
    prefix = GLOBAL_REFERENCE_UPLOADS[category]["prefix"]

    removed = []
    for existing in ref_dir.glob(f"{prefix}.*"):
        removed.append(existing.name)
        existing.unlink(missing_ok=True)

    reload_reference_documents()
    docs = get_reference_documents()
    return {
        "status": "success",
        "category": category,
        "removed_files": removed,
        "global_uploads": _get_global_uploads(docs),
    }


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
    # Sort by page number in ascending order
    unique.sort(key=lambda x: (x.get("page_number") or 0))
    return unique


def _get_global_uploads(docs: list[dict]) -> dict:
    by_name = {d.get("name", ""): d for d in docs}

    def find(prefix: str) -> Optional[str]:
        for name in by_name.keys():
            if name.startswith(prefix + "."):
                return name
        return None

    return {
        "benchmark_report": find("benchmark_report"),
        "age_references": find("age_references"),
        "text_preferences": find("text_preferences"),
    }


@router.get("/review/{job_id}")
def get_review_status(job_id: str) -> dict:
    """Get status of a review job (placeholder for step 3+)"""
    return {"job_id": job_id, "status": "pending", "message": "Review in progress. Check back soon."}
