from functools import lru_cache
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_name: str = "Clairebot API"
    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    log_level: str = "INFO"

    # Google APIs
    google_api_key: Optional[str] = None
    google_application_credentials: Optional[str] = None
    gcp_project_id: Optional[str] = None
    gcp_location: str = "us-central1"

    # Gemini (default to gemini-2.5-flash)
    gemini_model: str = "gemini-2.5-flash"

    # LLM Provider
    llm_provider: str = "gemini"
    llm_temperature: float = 0.0  # 0 = fully deterministic; increase for more variation

    # OpenAI
    openai_api_key: Optional[str] = None
    openai_model: str = "auto"

    # Google Sheets
    google_sheets_template_id: Optional[str] = None
    google_sheets_output_folder_id: Optional[str] = None
    google_sheets_worksheet_name: str = "Review Findings"
    enable_sheets_writer: bool = True

    # Document processing (future steps)
    doc_ai_processor_id: Optional[str] = None
    ocr_provider: str = "tesseract"

    # Local storage
    upload_dir: str = "./data/uploads"
    processed_dir: str = "./data/processed"
    reference_dir: str = "./reference"
    feedback_memory_filename: str = "review_feedback_memory.json"
    feedback_registry_filename: str = "review_feedback_registry.json"


@lru_cache
def get_settings() -> Settings:
    return Settings()
