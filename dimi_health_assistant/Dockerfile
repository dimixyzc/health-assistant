ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apk add --no-cache python3 py3-pip gcc musl-dev libffi-dev openssl-dev python3-dev cargo

WORKDIR /opt/health-assistant

COPY requirements.txt .
RUN pip3 install --no-cache-dir --break-system-packages -r requirements.txt

COPY main.py config.py ./
COPY connectors/ connectors/
COPY analytics/ analytics/
COPY ai/ ai/
COPY bot/ bot/
COPY storage/ storage/

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
