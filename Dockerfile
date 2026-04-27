FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY README.md ./
COPY app ./app
COPY agents ./agents
COPY schemas ./schemas
COPY workflows ./workflows
COPY playbooks ./playbooks
COPY data ./data
COPY scripts ./scripts
COPY evals ./evals
COPY docs ./docs

RUN python -m pip install --upgrade pip \
    && pip install -e ".[dev]"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
