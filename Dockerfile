FROM docker.1ms.run/astral/uv:python3.14-trixie-slim

WORKDIR /app
COPY pyproject.toml .
COPY README.md .
COPY src ./src
COPY uv.lock .

RUN uv sync

CMD ["uv", "run", "src/pickcat_summary"]