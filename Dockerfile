FROM python:3.12-slim

ARG INSTALL_DESKTOP_INPUT=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CYBERDECK_PORT=8080 \
    CYBERDECK_PORT_AUTO=0 \
    CYBERDECK_MDNS=0 \
    CYBERDECK_LOG=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ffmpeg \
      libglib2.0-0 \
      libgl1 \
      libpulse0 \
      libx11-6 && \
    rm -rf /var/lib/apt/lists/*

COPY requirements-core.txt requirements-desktop-input.txt ./
RUN python -m pip install --upgrade pip && \
    pip install -r requirements-core.txt && \
    if [ "${INSTALL_DESKTOP_INPUT}" = "1" ]; then pip install -r requirements-desktop-input.txt; fi

COPY . .

EXPOSE 8080
EXPOSE 5555/udp

CMD ["python", "main.py"]

