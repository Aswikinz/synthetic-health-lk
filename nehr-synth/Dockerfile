FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254 AS build
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.15
COPY . .
RUN uv sync --frozen --no-dev --no-editable && uv build
RUN .venv/bin/python scripts/install_java.py /opt/java \
    && .venv/bin/nehr-synth setup --tools /opt/nehr/tools

FROM python:3.12.14-slim-bookworm@sha256:782412e85d0f0984994c290652577d4018aff08145c85b262bb63dc0c7522254
LABEL org.opencontainers.image.title="nehr-synth" \
      org.opencontainers.image.source="https://github.com/Aswikinz/synthetic-health-lk" \
      org.opencontainers.image.licenses="MIT"
COPY --from=build /app/.venv /app/.venv
COPY --from=build /opt/java /opt/java
COPY --from=build /opt/nehr/tools /opt/nehr/tools
COPY --from=build /app/NOTICES.md /opt/nehr/NOTICES.md
COPY --from=build /app/evidence /opt/nehr/evidence
ENV PATH="/app/.venv/bin:/opt/java/bin:$PATH" \
    NEHR_TOOLS=/opt/nehr/tools NEHR_CACHE=/tmp/nehr-cache \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp
RUN mkdir /data && chown 1000:1000 /data
USER 1000:1000
WORKDIR /data
ENTRYPOINT ["nehr-synth"]
