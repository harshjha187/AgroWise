# Production image for the AgroWise backend (serves the API + both
# frontends, same as `python server.py` — just via gunicorn instead of
# Flask's dev server). Build context must be the project root (not
# backend/), since server.py expects web-dashboard/ and mobile-app/ as
# siblings of backend/.
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt gunicorn redis

COPY backend/ backend/
COPY web-dashboard/ web-dashboard/
COPY mobile-app/ mobile-app/

WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
EXPOSE 5000

# --workers >1 requires AGROWISE_RATELIMIT_STORAGE=redis://... (see
# docker-compose.yml) — flask-limiter's default in-memory store isn't
# shared across worker processes.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--access-logfile", "-", "server:app"]
