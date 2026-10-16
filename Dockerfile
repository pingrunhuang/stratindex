# StratIndex — Flask app behind gunicorn
FROM python:3.12-slim

WORKDIR /app

# System deps (none required for pure Flask + sqlite3 stdlib)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=5055 \
    STRATINDEX_DB_PATH=/data/stratindex.db \
    STRATINDEX_DATA_DIR=/data

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /data \
    && chmod +x /app/docker-entrypoint.sh

# Documentary default; actual listen port is $PORT
EXPOSE 5055

VOLUME ["/data"]

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn"]
