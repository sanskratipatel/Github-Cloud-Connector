FROM python:3.12.3-slim

# Set working directory
WORKDIR /app

# Install dependencies first (separate layer = faster rebuilds)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY app/ ./app/

# Create logs directory
RUN mkdir -p logs

# Expose port (Render injects $PORT at runtime)
EXPOSE 8000

# Start server — uses $PORT from Render environment
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
