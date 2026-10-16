# PostgreSQL 17 provides pg_dump and pg_restore matching the classroom database.
FROM postgres:17-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code
RUN python3 -m venv /opt/backupmanager-venv
ENV PATH="/opt/backupmanager-venv/bin:${PATH}"
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/

ENV PYTHONUNBUFFERED=1
ENV PORT=10000
EXPOSE 10000
ENTRYPOINT []
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
