# Base image with Python
FROM python:3.11-slim

# Set a working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port that the FastAPI app will run on
EXPOSE 8000

# Default command - run uvicorn on startup.
# Heroku exposes a $PORT environment variable which is used by the command.
CMD ["uvicorn", "app.web.server:app", "--host", "0.0.0.0", "--port", "${PORT:-8000}"]
