FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (needed for torch)
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (separate layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-download the model in a separate layer
RUN python -c "from transformers import pipeline; pipeline('text-classification', model='SamLowe/roberta-base-go_emotions', tokenizer='SamLowe/roberta-base-go_emotions')"

# Copy application code last (most frequently changed)
COPY ./app ./app

EXPOSE 8001

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]