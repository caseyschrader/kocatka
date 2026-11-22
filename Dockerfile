# The bot in a container. Build and run with: docker compose up -d --build
FROM python:3.12-slim

# No .pyc files, and log lines appear immediately in `docker compose logs`.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

# Dependencies first, so code changes do not reinstall them.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY bot ./bot
COPY analytics ./analytics
COPY scripts ./scripts
COPY webapp ./webapp

# Run as an ordinary user, not root. Id 1000 matches the first user on the server.
RUN useradd --uid 1000 --create-home kocatka
USER kocatka

CMD ["python", "-m", "bot"]
