import json
import pika
import time


class StreamPublisher:
    """
    This class abstracts an AMQP publisher stream.
    """

    def __init__(self, stream_name):
        self.stream_name = stream_name
        self.connect()

    def connect(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.stream_name, durable=True, arguments={"x-queue-type": "stream"}
        )
        self.channel = channel

    def publish(self, message, attempts=3):
        """
        Publish to the stream, reconnecting if necessary.
        """

        # TODO: Improve error handling logic with exponential backoff strategy
        while attempts > 0:
            try:
                self.channel.basic_publish(
                    exchange="", routing_key=self.stream_name, body=json.dumps(message)
                )
                print(f"published message to '{self.stream_name}': {message}")
                return
            except pika.exceptions.StreamLostError as e:
                print(e)
                pass

            print(f"reconnecting to stream '{self.stream_name}")
            attempts -= 1
            time.sleep(0.1)
            self.connect()

        raise TimeoutError("timed out reconnecting to the publisher stream")
