FROM python:3.9-slim

WORKDIR /app

# Install build dependencies for lxml / cryptography if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5050
ENV PORT=5050

CMD ["python", "web_server.py"]
