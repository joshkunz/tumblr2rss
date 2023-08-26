FROM debian:11-slim AS build
RUN apt-get update && \
    apt-get install --no-install-suggests --no-install-recommends --yes \
        gcc \
        libpython3-dev \
        python3-venv && \
    python3 -m venv /venv && \
    /venv/bin/pip install --upgrade pip setuptools wheel

FROM build AS build-env
COPY requirements.lock /requirements.lock
RUN /venv/bin/pip install --disable-pip-version-check -r /requirements.lock

FROM gcr.io/distroless/python3-debian11
COPY --from=build-env /venv /venv
COPY . /app
WORKDIR /app
ENTRYPOINT ["/venv/bin/python3", "tumblr2rss/tumblr2rss.py"]
