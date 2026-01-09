FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY tests/ ./tests/

# Create directory for SQLite database
RUN mkdir -p /app/data

# Set environment variables
ENV DATABASE_URL=sqlite:///./data/ab_testing.db
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Default command: run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
