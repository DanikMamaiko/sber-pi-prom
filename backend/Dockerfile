FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY backend/app /app/app
COPY backend/alembic.ini /app/alembic.ini
COPY backend/alembic /app/alembic
COPY backend/audit_alembic.ini /app/audit_alembic.ini
COPY backend/audit_alembic /app/audit_alembic

EXPOSE 8000

# Production startup: apply audit and business migrations, then run Uvicorn.
CMD ["sh", "-c", "if [ \"${AUDIT_ENABLED:-true}\" = \"true\" ]; then alembic -c audit_alembic.ini upgrade head; fi && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
