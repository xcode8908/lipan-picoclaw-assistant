FROM python:3.11-slim

# Install system dependencies (ffmpeg for media extraction, curl for checks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        curl \
        git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Environment defaults
ENV PORT=10000 \
    PYTHONUNBUFFERED=1

EXPOSE 10000

# Start bot and healthcheck server
CMD ["python", "bot_main.py"]
