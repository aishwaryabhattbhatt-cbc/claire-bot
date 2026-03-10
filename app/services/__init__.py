import uuid
from pathlib import Path

from app.core.config import get_settings

settings = get_settings()


def generate_job_id() -> str:
    """Generate a unique job ID"""
    return str(uuid.uuid4())


def save_uploaded_file(file_content: bytes, original_filename: str, job_id: str, file_type: str) -> str:
    """
    Save uploaded file to disk.

    Args:
        file_content: File bytes
        original_filename: Original file name
        job_id: Unique job ID
        file_type: 'report' or 'benchmark'

    Returns:
        Path to saved file
    """
    upload_path = Path(settings.upload_dir) / job_id
    upload_path.mkdir(parents=True, exist_ok=True)

    # Preserve original extension
    file_ext = Path(original_filename).suffix
    saved_filename = f"{file_type}{file_ext}"
    file_path = upload_path / saved_filename

    with open(file_path, "wb") as f:
        f.write(file_content)

    return str(file_path)


def get_job_directory(job_id: str) -> Path:
    """Get job directory path"""
    return Path(settings.upload_dir) / job_id
