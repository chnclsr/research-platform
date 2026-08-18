FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY alembic.ini ./
COPY migrations ./migrations
RUN pip install --no-cache-dir .
# Create the delivery mount point in the image so a fresh named volume inherits this
# ownership. Without it Docker creates /data/deliveries as root and the non-root app
# cannot write the bundles it streams back to MCP clients and Telegram.
RUN useradd --create-home --uid 10001 research \
    && mkdir -p /data/deliveries \
    && chown -R research:research /data
USER research
CMD ["research-api"]
