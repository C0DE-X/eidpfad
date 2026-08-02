FROM python:3.13-slim AS builder

ENV VIRTUAL_ENV=/opt/venv
RUN python -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

WORKDIR /build
COPY server/ /build/server/
RUN pip install --no-cache-dir --disable-pip-version-check /build/server


FROM python:3.13-slim AS runtime

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random

RUN groupadd --gid 10001 eidpfad \
    && useradd --uid 10001 --gid eidpfad --no-create-home --shell /usr/sbin/nologin eidpfad

COPY --from=builder /opt/venv /opt/venv
WORKDIR /app/server
COPY --chown=eidpfad:eidpfad server/app/ /app/server/app/
COPY --chown=eidpfad:eidpfad server/migrations/ /app/server/migrations/
COPY --chown=eidpfad:eidpfad server/alembic.ini server/entrypoint.sh /app/server/
COPY --chown=eidpfad:eidpfad shared/ /app/shared/

USER 10001:10001
EXPOSE 8080

HEALTHCHECK --interval=15s --timeout=5s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=3).read()"]

CMD ["sh", "/app/server/entrypoint.sh"]
