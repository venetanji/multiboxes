# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:aa943ce411423c7582288f18707ff66eddcbaeb510502d747a72aeb34f30d159
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml requirements.lock README.md ./
COPY src ./src
# Ordinary builds use normal roots. Managed proxy builds can mount the combined CA.
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then \
      PIP_CERT=/run/secrets/proxy_ca python -m pip install --no-cache-dir -c requirements.lock .; \
    else python -m pip install --no-cache-dir -c requirements.lock .; fi
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "multibox.game_server", "--host", "0.0.0.0", "--port", "8000"]
