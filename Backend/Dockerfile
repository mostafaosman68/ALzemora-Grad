FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    INSIGHTFACE_CTX_ID=-1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        cmake \
        curl \
        ffmpeg \
        git \
        libasound2-dev \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
        libsndfile1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        portaudio19-dev \
    && rm -rf /var/lib/apt/lists/*

COPY Backend/requirements-docker.txt /tmp/requirements-docker.txt
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -r /tmp/requirements-docker.txt

COPY Backend ./Backend
COPY ML ./ML

RUN mkdir -p \
        /app/data/NewPersonImages \
        /app/data/voices \
        /app/data/medications \
        /app/data/temp_recognition \
        /app/data/temp_medscan \
        /app/data/medscan_reference_images

WORKDIR /app/Backend

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; import os; port=os.environ.get('PORT', '8000'); urllib.request.urlopen(f'http://127.0.0.1:{port}/', timeout=5)" || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
