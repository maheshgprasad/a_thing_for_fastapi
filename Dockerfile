FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 appuser

COPY pyproject.toml README.md ./
COPY app ./app
COPY main.py ./

RUN pip install --upgrade pip && pip install .

USER appuser

EXPOSE 9190

HEALTHCHECK --interval=30s --timeout=3s --start-period=8s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:9190/health')"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9190"]
