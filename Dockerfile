FROM eclipse-temurin:21-jre-jammy

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    MORPHE_DATA_DIR=/app/cache/morphe

RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    curl \
    ca-certificates \
    gosu \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip3 install --no-cache-dir -r /app/requirements.txt

RUN mkdir -p /app/morphe /app/cache/morphe /app/watch /app/output /app/config /app/cache /app/library && chmod -R 777 /app

COPY app/ /app/app/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/app/watch", "/app/output", "/app/config", "/app/cache", "/app/library"]
EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
