from typing import Optional
from pydantic import BaseModel, Field


class TimelineSubstep(BaseModel):
    id: str
    name: str
    status: str
    message: Optional[str] = None


class TimelinePhase(BaseModel):
    id: str
    name: str
    status: str
    message: Optional[str] = None
    substeps: list[TimelineSubstep] = Field(default_factory=list)


class ReviewRequest(BaseModel):
    """Request schema for /review endpoint"""

    report_language: str = Field(..., description="Language of report: 'French' or 'English'")
    comparison_mode: bool = Field(False, description="If True, expect benchmark file as well")


class FileUploadResponse(BaseModel):
    """Response after file upload"""

    job_id: str = Field(..., description="Unique job ID for tracking")
    file_name: str = Field(..., description="Uploaded file name")
    report_language: str = Field(..., description="Language of report")
    comparison_mode: bool = Field(..., description="Is this a comparison review?")
    status: str = Field(default="uploaded", description="Current status")
    message: str = Field(default="File uploaded successfully")
    findings_count: Optional[int] = Field(default=None, description="Number of issues detected")
    findings: Optional[list[dict]] = Field(default=None, description="Detected review issues")
    sheets_url: Optional[str] = Field(default=None, description="Google Sheets URL")
    sheets_status: Optional[str] = Field(default=None, description="Sheets write status: success|failed|skipped")
    sheets_error: Optional[str] = Field(default=None, description="Sheets write error message if failed")
    llm_status: Optional[str] = Field(default=None, description="LLM execution status: success|failed|skipped")
    llm_error: Optional[str] = Field(default=None, description="LLM error message if failed")
    llm_usage: Optional[dict] = Field(default=None, description="LLM usage and estimated cost for this run")
    instructions_source: Optional[str] = Field(default=None, description="Instructions source: custom|default")
    phase_updates: Optional[list[str]] = Field(
        default=None,
        description="Backend phase-by-phase status updates",
    )
    timeline: Optional[list[TimelinePhase]] = Field(
        default=None,
        description="Structured backend timeline with phase and sub-step statuses",
    )


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    environment: str


class InstructionsResponse(BaseModel):
    comparison_instructions: str
    french_instructions: str
    comparison_source: Optional[str] = None
    french_source: Optional[str] = None
