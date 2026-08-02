FROM python:3.14-alpine AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON=python3.14 \
    UV_PROJECT_ENVIRONMENT=/app

RUN --mount=type=cache,target=/root/.cache \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync \
        --locked \
        --no-dev \
        --no-install-project

COPY . /src
WORKDIR /src
RUN --mount=type=cache,target=/root/.cache \
    uv pip install --python=/app .


FROM python:3.14-alpine AS run

RUN addgroup -S app && adduser -S app -G app

COPY --from=build --chown=app:app /app /app

USER app

WORKDIR /data

CMD ["/app/bin/mushroomd"]
