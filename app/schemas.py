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
    prompt_mode: Optional[str] = Field(default=None, description="Prompt mode used for the review")
    applied_memory_count: Optional[int] = Field(default=0, description="Active feedback-registry rules applied for this mode")
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
    english_instructions: str
    comparison_source: Optional[str] = None
    french_source: Optional[str] = None
    english_source: Optional[str] = None


class FeedbackRegistryCreateRequest(BaseModel):
    mode: str = Field(..., description="Target prompt mode: comparison|french_review|english_review")
    feedback_type: str = Field(..., description="false_alarm|missed_issue|correction")
    finding_category: Optional[str] = Field(default=None, description="Finding category")
    issue_pattern: str = Field(..., min_length=1, description="Issue phrase/pattern this feedback applies to")
    reason: str = Field(..., min_length=1, description="Why this entry should be applied")
    expected_finding: Optional[str] = Field(default=None, description="Expected corrected/missed finding text")
    original_finding: Optional[dict] = Field(default=None, description="Original finding snapshot")
    priority: str = Field(default="medium", description="low|medium|high")
    created_by: Optional[str] = Field(default=None, description="Optional user identifier")


class FeedbackRegistryUpdateRequest(BaseModel):
    mode: Optional[str] = Field(default=None, description="comparison|french_review|english_review")
    feedback_type: Optional[str] = Field(default=None, description="false_alarm|missed_issue|correction")
    finding_category: Optional[str] = None
    issue_pattern: Optional[str] = Field(default=None, min_length=1)
    reason: Optional[str] = Field(default=None, min_length=1)
    expected_finding: Optional[str] = None
    priority: Optional[str] = Field(default=None, description="low|medium|high")
    status: Optional[str] = Field(default=None, description="pending_review|active|disabled")


class FeedbackRegistryDisableRequest(BaseModel):
    reason: Optional[str] = Field(default=None, description="Optional soft-disable reason")


class FeedbackRegistryItem(BaseModel):
    id: str
    mode: str
    feedback_type: str
    finding_category: Optional[str] = None
    issue_pattern: str
    reason: str
    expected_finding: Optional[str] = None
    original_finding: Optional[dict] = None
    status: str
    priority: str
    created_by: Optional[str] = None
    disabled_reason: Optional[str] = None
    created_at: str
    updated_at: str
    version: int


class FeedbackRegistryListResponse(BaseModel):
    items: list[FeedbackRegistryItem]
