FROM python:3.11.9-slim-bookworm

WORKDIR /app

COPY requirements.txt pyproject.toml ./
COPY src ./src

RUN python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir .

ENV PYTHONPATH=/app/src

COPY . .

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "f1engine.api:app", "--host", "0.0.0.0", "--port", "8000"]
