FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
# - WeasyPrint requires cairo/pango/gdk-pixbuf (cannot be installed via pip)
# - LibreOffice is required for DOCX → PDF conversion
# - libxml2-dev + libxslt1-dev are required by lxml (ISF document extraction)
# - libjpeg-dev + zlib1g-dev are required by Pillow (ISF image processing)
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    libglib2.0-0 \
    libreoffice \
    libxml2-dev \
    libxslt1-dev \
    libjpeg-dev \
    zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

# Verify LibreOffice installation
RUN soffice --version || (echo "LibreOffice installation failed" && exit 1)

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only what the app needs at RUNTIME. Explicit list instead of
# `COPY . .` so secrets/local state (.env, .git, uploads, ...) can never leak
# into the image — belt to the .dockerignore's suspenders.
# scripts/, migrations/, tests/ are dev/ops tooling: in dev they're available
# via the compose bind mount, and migrations/seeds run against the DB from a
# dev machine — none of them belong in the production image.
COPY app/ ./app/
COPY docs/ ./docs/
COPY pyproject.toml ./
# Read at runtime by app/modules/study_dashboard/ai_assistant/sdtm_schema.py
COPY metadata_schema_db_01.txt ./

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV PORT=8000

# Run as a non-root user. LibreOffice needs a writable HOME for its profile;
# the app writes runtime data under /app (uploads, signed_artifacts, temp).
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app
ENV HOME=/home/appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
