# Robin dev/test/run image.
# Python 3.12 inside the Linux VM — sidesteps host ThreatLocker, which
# blocks native Homebrew Python + compiled wheels on the macOS host.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Deps first for layer caching.
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt

# Source mounted via compose for live edits; copied for standalone runs.
COPY . .

EXPOSE 8000

CMD ["pytest", "-q"]
