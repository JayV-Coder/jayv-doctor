# Imagem da API e dos workers. Contexto: raiz do repositório.
#   docker build -f infrastructure/docker/python.Dockerfile \
#     --build-arg PACKAGE=aid-api --build-arg APP=aid_api.main:app .
FROM python:3.12-slim AS build
ARG PACKAGE
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv==0.9.5
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/api apps/api
COPY packages/contracts packages/contracts
COPY workers/runtime workers/runtime
RUN uv sync --frozen --no-dev --no-editable --package "$PACKAGE"

FROM python:3.12-slim
ARG APP
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 APP=$APP
RUN useradd --system --uid 10001 aid
WORKDIR /app
COPY --from=build /app/.venv .venv
USER 10001
# O Cloud Run informa a porta em $PORT.
CMD ["sh", "-c", "exec uvicorn \"$APP\" --host 0.0.0.0 --port \"${PORT:-8080}\""]
