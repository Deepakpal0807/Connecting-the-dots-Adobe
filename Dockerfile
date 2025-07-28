# Stage 1: Build image with dependencies
FROM python:3.11-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies if needed (e.g. for PDF processing)
RUN apt-get update && apt-get install -y \
    gcc g++ libpoppler-cpp-dev pkg-config python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file if exists
COPY requirements.txt .

# Install dependencies to a local user path
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime image
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy source code and input/output folders
COPY app/ ./app/

# Set environment variables for performance/logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONOPTIMIZE=1

# Health check (optional)
HEALTHCHECK CMD python3 -c "import sys; sys.exit(0)"

# Set default command to run test2.py with input/output arguments
ENTRYPOINT ["python", "app/test2.py", "app/input", "app/output"]
