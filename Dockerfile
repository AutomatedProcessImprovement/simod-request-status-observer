FROM python:3.9-bullseye

RUN pip install --upgrade pip poetry

WORKDIR /usr/src/simod-request-status-observer
ADD . .
RUN poetry install

ENV PYTHONUNBUFFERED=1

ENV BROKER_URL=amqp://guest:guest@rabbitmq-service:5672
ENV SIMOD_EXCHANGE_NAME=simod
ENV SIMOD_STATUS_WORKER_BINDING_KEY=requests.status.*
ENV SIMOD_HTTP_STORAGE_PATH=/tmp/simod-volume/data

CMD ["poetry", "run", "python", "src/simod_request_status_observer/main.py"]