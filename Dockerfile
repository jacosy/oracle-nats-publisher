FROM python:3.11-slim

# Install system dependencies for Oracle client
RUN apt-get update && apt-get install -y \
    libaio1 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Oracle Instant Client
RUN wget https://download.oracle.com/otn_software/linux/instantclient/instantclient-basiclite-linuxx64.zip \
    && unzip instantclient-basiclite-linuxx64.zip -d /opt/oracle \
    && rm instantclient-basiclite-linuxx64.zip \
    && sh -c "echo /opt/oracle/instantclient* > /etc/ld.so.conf.d/oracle-instantclient.conf" \
    && ldconfig

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY config/ ./config/
COPY models/ ./models/
COPY utils/ ./utils/

# Create non-root user for security
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Run the application
CMD ["python", "src/main.py"]
