# TalkToBook — Python engine needs pandoc (system binary) + WeasyPrint's
# native libs, and optionally Calibre for Kindle AZW3. A container is the
# smallest thing that makes pandoc + Python coexist (Railway / Render / Fly).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# pandoc (EPUB), WeasyPrint runtime libs (PDF), fonts, calibre (Kindle AZW3).
# calibre is ~large; drop the apt line below if you don't need Kindle output.
RUN apt-get update && apt-get install -y --no-install-recommends \
      pandoc \
      libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev \
      libcairo2 fonts-dejavu fonts-liberation \
      calibre \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY webapp/requirements.txt /srv/requirements.txt
RUN pip install -r /srv/requirements.txt

# The web layer imports scripts/build.py as a library, so copy both.
COPY scripts /srv/scripts
COPY webapp /srv/webapp

WORKDIR /srv/webapp
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
