FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    BDS_WORKSPACE_ROOT=/app/studio/backend/workspace

WORKDIR /app

COPY studio/backend/requirements.txt /app/studio/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/studio/backend/requirements.txt

COPY README.md BUILD_LOG.md black_dragon_studio_constitution_v1.md /app/
COPY studio /app/studio
COPY scripts /app/scripts
COPY sample_prompts /app/sample_prompts

WORKDIR /app/studio/backend
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
