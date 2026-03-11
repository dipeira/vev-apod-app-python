FROM python:3.11-slim

# Install system dependencies (LibreOffice, DejaVu fonts, Microsoft fonts)
# Note: We enable 'contrib' repos to install ttf-mscorefonts-installer
RUN sed -i 's/Components: main/Components: main contrib/' /etc/apt/sources.list.d/debian.sources 2>/dev/null || true \
    && apt-get update \
    && echo "ttf-mscorefonts-installer msttcorefonts/accepted-mscorefonts-eula select true" | debconf-set-selections \
    && apt-get install -y --no-install-recommends \
        fontconfig \
        ttf-mscorefonts-installer \
        libreoffice \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-crosextra-carlito \
        fonts-crosextra-caladea \
    && rm -rf /var/lib/apt/lists/* \
    && fc-cache -f -v

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
