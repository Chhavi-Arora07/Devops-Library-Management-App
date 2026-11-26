FROM python:3.13-slim AS build
WORKDIR /build
COPY requirements.txt .
RUN python -m venv /venv && /venv/bin/pip install --no-cache-dir -r requirements.txt

FROM python:3.13-slim
# Pick up OS security fixes, and drop pip because nothing is installed at runtime.
RUN apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/* \
    && pip uninstall -y pip \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin library
ARG APP_VERSION=dev
ENV PATH=/venv/bin:$PATH PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 APP_VERSION=$APP_VERSION
WORKDIR /srv
COPY --from=build /venv /venv
COPY app ./app
COPY wsgi.py gunicorn.conf.py ./
USER 10001
EXPOSE 8000 9100
HEALTHCHECK --interval=30s --timeout=3s \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz')"]
CMD ["gunicorn", "-c", "gunicorn.conf.py", "wsgi:app"]
