FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 CROSSEXAM_AUDIT_DB=/data/crossexam_audit.db
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY crossexam ./crossexam
RUN useradd --create-home --uid 10001 app && mkdir /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000

# The model is trained when the service starts, so allow time before the first check.
HEALTHCHECK --interval=15s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["uvicorn", "crossexam.api:app", "--host", "0.0.0.0", "--port", "8000"]
