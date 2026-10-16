FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROJECT_ROOT=/app \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    DATABASE_PATH=/app/data/processed/procurement.db

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY data ./data
COPY --from=frontend-build /frontend/dist ./frontend/dist

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "procurement_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]
