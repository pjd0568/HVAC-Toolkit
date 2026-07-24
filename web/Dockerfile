FROM python:3.12-slim

WORKDIR /srv

# Engine first (own layer — changes less often than web code)
COPY engine /srv/engine
RUN pip install --no-cache-dir /srv/engine

COPY web/requirements.txt /srv/web/requirements.txt
RUN grep -v "^-e" /srv/web/requirements.txt | pip install --no-cache-dir -r /dev/stdin

COPY web /srv/web
WORKDIR /srv/web

ENV PORT=8000
ENV FLASK_APP=wsgi:app
EXPOSE 8000

# Railway injects $PORT; local Compose keeps the default 8000.
CMD ["sh", "-c", "gunicorn -b 0.0.0.0:${PORT:-8000} -w 2 wsgi:app"]
