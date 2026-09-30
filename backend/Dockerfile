# syntax=docker/dockerfile:1
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY . /app/

# Expose port (default 8000)
EXPOSE 8000

# Run Daphne ASGI server supporting both HTTP and WebSockets
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "tftw_project.asgi:application"]
