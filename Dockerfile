FROM mirror.gcr.io/library/python:3.12-slim

ARG LITESTREAM_VERSION=0.3.13
ARG TARGETARCH=amd64
ADD https://github.com/benbjohnson/litestream/releases/download/v${LITESTREAM_VERSION}/litestream-v${LITESTREAM_VERSION}-linux-${TARGETARCH}.tar.gz /tmp/litestream.tar.gz
RUN tar -C /usr/local/bin -xzf /tmp/litestream.tar.gz && rm /tmp/litestream.tar.gz

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY best_deal ./best_deal
COPY deploy/litestream.yml /etc/litestream.yml
COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && useradd --create-home app && mkdir -p /data && chown app /data

ENV BEST_DEAL_DB=/data/best_deal.db \
    PYTHONUNBUFFERED=1 \
    PORT=8080
USER app
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
