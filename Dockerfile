FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src ./src
# The threshold profile smart_router reads at import. Two lines, not one: the file has to
# be in the image AND findable. ayarlar.varsayilan_yol() walks four levels up from its own
# module, which lands on the repository root in a source checkout but on the interpreter's
# lib directory once pip has installed the package into site-packages -- so the copied file
# would sit at /app/config while the router looked somewhere else entirely. Naming the path
# outright removes the arithmetic. Without both, the router silently falls back to its
# embedded defaults and writes an esik_version nobody chose into every document's
# provenance.
COPY config ./config
ENV SMART_ROUTER_CONFIG_PATH=/app/config/smart_router.yaml
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
