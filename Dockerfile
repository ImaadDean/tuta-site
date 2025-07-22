# Use a slim Python base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy all files
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 5000

# Run the FastAPI app
CMD ["uvicorn", "run:app", "--host", "0.0.0.0", "--port", "5000"]
