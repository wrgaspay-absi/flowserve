# Use an official lightweight Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable real-time logging
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Copy dependency requirements first to leverage Docker layer caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files into the container
COPY . .

# Default fallback command if executed without arguments
CMD ["python", "sales/ingestion.py"]