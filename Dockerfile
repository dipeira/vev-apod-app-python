FROM python:3.11-slim

# Install system dependencies (LibreOffice for Excel→PDF, DejaVu fonts for Greek)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libreoffice \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create required directories (instance/ and data/ are mounted as volumes at runtime)
RUN mkdir -p /app/data /app/instance

# Strip Windows CRLF line endings and make entrypoint executable
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

EXPOSE 5000

# entrypoint.sh runs init_db.py (idempotent) then starts gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
