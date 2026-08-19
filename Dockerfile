FROM node:22-alpine AS frontend-build

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade \
        pip==26.2.1 \
        setuptools==83.0.0 \
        wheel==0.46.2 \
    && pip install --no-cache-dir -r /app/requirements.txt

COPY proxy /app
COPY --from=frontend-build /proxy/static/react /app/static/react

RUN addgroup --system --gid 10001 cardiollm \
    && adduser --system --uid 10001 --ingroup cardiollm --home /app cardiollm \
    && mkdir -p /app/static/generated \
    && chown -R cardiollm:cardiollm /app

USER cardiollm

EXPOSE 8000
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
