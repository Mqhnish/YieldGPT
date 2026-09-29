# The Internal Brain with Member 3's audit and reliability layer.
FROM python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b
WORKDIR /srv
COPY deploy/requirements.lock deploy/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r deploy/requirements.lock
COPY app app
COPY scripts scripts
RUN chmod -R a+rX /srv && useradd --system --uid 10001 brain && mkdir /data && chown brain /data
USER brain
ENV IB_DATA_DIR=/data PYTHONUNBUFFERED=1
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if b'\"ok\"' in urllib.request.urlopen('http://127.0.0.1:8000/api/health').read() else 1)"
# One worker: the search index lives in process memory (the audit chain itself is multi-worker safe).
CMD ["uvicorn", "app.server:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
