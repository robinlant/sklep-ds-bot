FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml ./
COPY voice_tracker ./voice_tracker
COPY services ./services

RUN pip install --no-cache-dir .

ARG SERVICE
ENV SERVICE=${SERVICE}

CMD ["sh", "-c", "python -m services.${SERVICE}"]
