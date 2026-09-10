FROM python:3.12-slim

WORKDIR /app

# libgl1/libglib2.0-0 are required by opencv-python-headless's video decode/codec paths.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/recordings /data/snapshots /data/models

# MJPEG live-view server — internal only, never published to the host or routed by
# nginx; the backend is the only client (see app/streaming.py).
EXPOSE 8090

CMD ["python", "-m", "app.main"]
