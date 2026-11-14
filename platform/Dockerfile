# One image for the trust services: boundary, discovery and the dev IdP. Each service picks its command in compose.
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/app/platform:/app/platform/discovery

COPY requirements-trust.txt /app/requirements-trust.txt
RUN pip install --no-cache-dir -r /app/requirements-trust.txt

COPY shared /app/shared
COPY platform /app/platform
COPY domains /app/domains
COPY tools /app/tools

EXPOSE 8000
CMD ["uvicorn", "--factory", "boundary.main:get_app", "--app-dir", "platform", "--host", "0.0.0.0", "--port", "8000"]
