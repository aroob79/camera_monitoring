# Single image used by both services in docker-compose.yml -- the monitor
# (writer) and the dashboard (reader) run the same image with a different
# command, so RTSP/OpenCV/Streamlit dependencies only need to be built once.

FROM python:3.11-slim

# ffmpeg: gives OpenCV's cv2.VideoCapture RTSP transport support.
# libgl1 / libglib2.0-0: common runtime deps for opencv-python-headless wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        libgl1 \
        libglib2.0-0 \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite DB + WAL files live here, mounted as a volume in compose so both
# the monitor and dashboard containers see the same file.
RUN mkdir -p /app/data
ENV DB_PATH=/app/data/cctv_monitor.db

# Run as non-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# No default CMD -- docker-compose.yml sets the command per service
# (monitor.py for the writer, streamlit for the dashboard).
