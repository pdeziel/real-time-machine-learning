import json
import pika
import queue
import threading


class StreamSubscriber:
    """
    This class abstracts an AMQP subscriber stream.
    """

    def __init__(self, stream_name):
        self.stream_name = stream_name
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.stream_name, durable=True, arguments={"x-queue-type": "stream"}
        )
        channel.basic_qos(prefetch_count=1)
        self.channel = channel
        self.queue = None

    def start(self, block=True, on_message_callback=None, stream_offset="last"):
        """
        Start subscribing to the stream. In blocking mode, the on_message_callback function must be provided.
        """

        callback_fn = on_message_callback if block else self.on_message
        self.channel.basic_consume(
            queue=self.stream_name,
            on_message_callback=callback_fn,
            arguments={"x-stream-offset": stream_offset},
        )

        print(f"subscribing to topic: {self.stream_name}")
        if block:
            self.channel.start_consuming()
        else:
            self.queue = queue.Queue(maxsize=10)
            self.thread = threading.Thread(target=self.channel.start_consuming)
            self.thread.start()

    def stop(self):
        self.channel.close()
        self.thread.join()

    def on_message(self, channel, method, properties, body):
        print(f"Received message from '{self.stream_name}': {body}")
        self.queue.put(json.loads(body))
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def get_one(self):
        """
        Get the next message from the queue.
        """

        if self.queue is not None:
            return self.queue.get()

    def flush(self):
        """
        Flush messages in the queue.
        """

        if self.queue is not None:
            while not self.queue.empty():
                self.queue.get()
