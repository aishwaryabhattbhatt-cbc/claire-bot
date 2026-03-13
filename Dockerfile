# Use official Python 3.11 slim image
FROM python:3.11-slim

# Install system dependencies for document parsing and OCR
RUN apt-get update && apt-get install -y \
    tesseract-ocr \
    tesseract-ocr-fra \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create required directories (instructions will be generated on first run)
RUN mkdir -p data/uploads data/processed

# Expose port (Cloud Run uses 8080 by default)
EXPOSE 8080

# Run the app - Cloud Run injects PORT env var
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
