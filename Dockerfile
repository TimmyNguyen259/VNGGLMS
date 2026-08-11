FROM python:3.12-slim

# Không tạo pyc, output không buffer -> log ra ngay
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    LMS_DB_PATH=/data/lms.db

WORKDIR /app

# Cài deps trước (layer cache) rồi mới copy source
COPY app/requirements.txt /app/app/requirements.txt
RUN pip install -r /app/app/requirements.txt

COPY . /app

# Data dir cho SQLite (mount volume vào đây)
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 8000

# 2 gunicorn workers — SQLite serialize writes nên nhiều worker không tăng
# throughput write, nhưng vẫn giúp concurrent reads.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-", "app.main:app"]
