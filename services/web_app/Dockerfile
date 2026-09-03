# Official Python image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# No system PDF dependency: the web app renders PDFs with pypdfium2, a pure wheel pinned in
# requirements.txt and selected by `pdf.backend` in config.yaml. If you switch that setting
# to "pdf2image", re-add the poppler binary here:
#   RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*

# Copy and install the local vlm4ocr package (picks up latest source including bbox support)
COPY ./packages/vlm4ocr /app/packages/vlm4ocr
RUN pip install --no-cache-dir /app/packages/vlm4ocr

# Copy the web application requirements file
COPY ./services/web_app/requirements.txt /app/services/web_app/requirements.txt

# Install web application specific dependencies
RUN pip install --no-cache-dir -r /app/services/web_app/requirements.txt

# Copy the rest of the web application code into the container
COPY ./services/web_app /app/services/web_app

# Make port 5000 available to the world outside this container
EXPOSE 5000

# Define environment variables
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000
# ENV FLASK_DEBUG=False # Set to False for production

# Run app.py when the container launches using Gunicorn for production
ENV PYTHONPATH=/app
CMD ["gunicorn", "--workers", "3", "--bind", "0.0.0.0:5000", "--timeout", "300", "services.web_app.app:app"]