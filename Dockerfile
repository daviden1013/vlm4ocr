# Official Python image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Install Poppler for PDF processing (as per your README prerequisites)
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*

# Copy the vlm4ocr package source
COPY ./packages/vlm4ocr /app/packages/vlm4ocr

# Install the vlm4ocr package and its dependencies
# This assumes your vlm4ocr package has a setup.py or similar and can be installed with pip
RUN pip install --no-cache-dir ./packages/vlm4ocr

# Copy the web application requirements file
COPY ./services/web_app/requirements.txt /app/services/web_app/requirements.txt

# Install web application specific dependencies
RUN pip install --no-cache-dir -r /app/services/web_app/requirements.txt

# Copy the rest of the web application code into the container
COPY ./services/web_app /app/services/web_app

# Make port 5000 available to the world outside this container (as used in your run.py)
EXPOSE 5000

# Define environment variables (if any, your run.py uses FLASK_RUN_HOST, FLASK_RUN_PORT, FLASK_DEBUG)
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000
# ENV FLASK_DEBUG=False # Set to False for production

# Run app.py when the container launches using Gunicorn for production
# The CMD instruction should be used to run the software
# contained by your image, along with any arguments.
# Gunicorn is a common choice for Flask production deployments.
ENV PYTHONPATH=/app
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "services.web_app.app:app"]