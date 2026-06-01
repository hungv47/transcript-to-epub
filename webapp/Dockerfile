# TalkToBook — Python engine needs pandoc (system binary) + WeasyPrint's
# native libs, and optionally Calibre for Kindle AZW3. A container is the
# smallest thing that makes pandoc + Python coexist (Railway / Render / Fly).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

# pandoc (EPUB) + WeasyPrint runtime libs (PDF) + fonts are always installed.
# Calibre (Kindle AZW3) is large and only needed for the paid Kindle format;
# gate it behind a build arg so the validation image stays lean. Enable with
# --build-arg INSTALL_CALIBRE=true (or set it in your host's build settings).
ARG INSTALL_CALIBRE=false
RUN apt-get update && apt-get install -y --no-install-recommends \
      pandoc \
      libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 libffi-dev \
      libcairo2 fonts-dejavu fonts-liberation \
    && if [ "$INSTALL_CALIBRE" = "true" ]; then \
         apt-get install -y --no-install-recommends calibre; \
       fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /srv
COPY webapp/requirements.txt /srv/requirements.txt
RUN pip install -r /srv/requirements.txt

# The web layer imports scripts/build.py as a library, so copy both.
COPY scripts /srv/scripts
COPY webapp /srv/webapp

WORKDIR /srv/webapp
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --no-server-header --no-date-header --header server:TalkToBook"]
