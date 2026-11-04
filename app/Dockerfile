# Stage 1: Build React + Tailwind + ECharts Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /build

COPY app/frontend/package*.json ./
RUN npm install

COPY app/frontend/ ./
RUN npm run build

# Stage 2: Production Python Image (FastAPI + DuckDB + Scikit-Learn)
FROM python:3.12-slim
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend and pure python core/ml modules
COPY app/backend /app/app/backend
COPY custom_components /app/custom_components

# Copy compiled frontend dist into place
COPY --from=frontend-builder /build/dist /app/app/frontend/dist

ENV PYTHONPATH=/app
ENV PORT=8080
EXPOSE 8080

CMD ["python", "-m", "app.backend.main"]
