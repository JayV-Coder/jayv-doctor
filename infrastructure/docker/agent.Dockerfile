# Imagem do agente local (#39), instalada na rede do cliente. Contexto: raiz do repositório.
#   docker build -f infrastructure/docker/agent.Dockerfile -t aid-agent .
# Sem EXPOSE e sem servidor: o agente só abre conexões de saída (HTTPS para a API). A biblioteca
# RFC não vem aqui (licença da SAP); quem usa coletas RFC estende esta imagem
# (docs/operations/agente.md).
FROM python:3.12-slim AS build
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv==0.9.5
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY apps/agent apps/agent
COPY apps/api apps/api
COPY packages packages
COPY workers workers
RUN uv sync --frozen --no-dev --no-editable --package aid-agent

FROM python:3.12-slim
ENV PATH=/app/.venv/bin:$PATH PYTHONUNBUFFERED=1 AID_AGENT_STATE=/var/lib/aid-agent
RUN useradd --system --uid 10001 aid && install -d -o 10001 -m 0700 /var/lib/aid-agent
WORKDIR /app
COPY --from=build /app/.venv .venv
USER 10001
VOLUME ["/var/lib/aid-agent"]
ENTRYPOINT ["aid-agent"]
CMD ["run"]
