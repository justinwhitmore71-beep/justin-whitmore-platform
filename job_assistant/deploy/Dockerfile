FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    FORCE_HTTPS_COOKIES=1

WORKDIR /app

COPY job_assistant/deploy/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY job_assistant /app/job_assistant

# Run non-root user in production
RUN useradd -m appuser && mkdir -p /app/job_assistant/data && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "--threads", "4", "--timeout", "120", "job_assistant.dashboard.app:app"]
