import logging
import os
from pathlib import Path
from typing import Optional

import pika
from pika import spec
from pika.adapters.blocking_connection import BlockingChannel

from simod_http.app import Request, RequestStatus


class Settings:
    broker_url: str
    exchange_name: str
    binding_key: str

    def __init__(self):
        self.broker_url = os.environ.get('BROKER_URL')
        self.exchange_name = os.environ.get('SIMOD_EXCHANGE_NAME')
        self.binding_key = os.environ.get('SIMOD_STATUS_WORKER_BINDING_KEY')
        self.simod_http_storage_path = Path(os.environ.get('SIMOD_HTTP_STORAGE_PATH'))

        if not self.is_valid():
            raise ValueError('Invalid settings')

    def is_valid(self):
        return (
                self.broker_url is not None
                and self.exchange_name is not None
                and self.binding_key is not None
                and self.simod_http_storage_path is not None
        )


class Worker:
    def __init__(self, settings: Settings):
        self.settings = settings

        self._parameters = pika.URLParameters(self.settings.broker_url)
        self._connection = pika.BlockingConnection(self._parameters)
        self._channel = self._connection.channel()

        self._queue_name = None

    def run(self):
        self._channel.exchange_declare(
            exchange=self.settings.exchange_name,
            exchange_type='topic',
            durable=True,
        )

        result = self._channel.queue_declare('', exclusive=True)
        self._queue_name = result.method.queue

        self._channel.queue_bind(
            exchange=self.settings.exchange_name,
            queue=self._queue_name,
            routing_key=self.settings.binding_key,
        )

        self._channel.basic_consume(queue=self._queue_name, on_message_callback=self.on_message)

        logging.info('Worker started')

        try:
            self._channel.start_consuming()
        except Exception as e:
            logging.error(e)
            self._channel.stop_consuming()
        self._connection.close()

        logging.info('Worker stopped')

    def on_message(
            self,
            channel: BlockingChannel,
            method: spec.Basic.Deliver,
            properties: spec.BasicProperties,
            body: bytes,
    ):
        request_id = body.decode()
        routing_key = method.routing_key
        status = routing_key.split('.')[-1]

        logging.info(f'Got message: {request_id} {status}')

        try:
            request = self.update_status(request_id, status)
        except Exception as e:
            logging.error(f'Error while updating request {request_id}: {e}')
            return

        channel.basic_ack(delivery_tag=method.delivery_tag)

        logging.info(f'Request {request_id} updated: {request.status}')

    def update_status(self, job_request_id: str, status: str) -> Optional[Request]:
        request_dir = self.settings.simod_http_storage_path / 'requests' / job_request_id

        if not request_dir.exists():
            logging.error(f'Request directory does not exist: {request_dir}')
            return None

        request_path = request_dir / 'request.json'

        request = Request.parse_raw(request_path.read_text())

        status = RequestStatus(status)
        request.status = status

        request.save()

        return request


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)

    settings = Settings()
    requests_status_observer = Worker(settings)
    requests_status_observer.run()
