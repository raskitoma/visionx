# Stage 1: Build the React Frontend
FROM node:20-alpine AS frontend-builder
WORKDIR /ui
COPY ui/package.json ui/package-lock.json* ./
RUN npm install
COPY ui/ ./
RUN npm run build

# Stage 2: Runtime Environment
FROM python:3.11-slim
WORKDIR /app
COPY app/requirements.txt .
# Install ping utility
RUN apt-get update && apt-get install -y iputils-ping && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./
COPY init.sql .
# Copy built React frontend to static folder
RUN mkdir -p /app/static
COPY --from=frontend-builder /ui/dist /app/static

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
