FROM python:3.12-slim

WORKDIR /srv

# Engine first (own layer — changes less often than web code)
COPY engine /srv/engine
RUN pip install --no-cache-dir /srv/engine

COPY web/requirements.txt /srv/web/requirements.txt
RUN grep -v "^-e" /srv/web/requirements.txt | pip install --no-cache-dir -r /dev/stdin

COPY web /srv/web
WORKDIR /srv/web

EXPOSE 8000
CMD ["gunicorn", "-b", "0.0.0.0:8000", "-w", "2", "wsgi:app"]
