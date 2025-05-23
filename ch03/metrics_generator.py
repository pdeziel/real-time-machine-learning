import json
import pika
from river import metrics


class MetricsGenerator:
    def __init__(self, stream_name):
        self.stream_name = stream_name
        self.metric = metrics.MAE()

    def process_message(self, channel, method, properties, body):
        data = json.loads(body)
        velocity = data["velocity"]
        velocity_pred = data["velocity_pred"]
        self.metric.update(velocity, velocity_pred)
        print(
            f"velocity_pred: {velocity_pred}, velocity: {velocity}, mae: {self.metric.get()}"
        )

        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.stream_name, durable=True, arguments={"x-queue-type": "stream"}
        )
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(
            queue=self.stream_name,
            on_message_callback=self.process_message,
            arguments={"x-stream-offset": "first"},
        )
        channel.start_consuming()


metrics_generator = MetricsGenerator(stream_name="flight_predictions")
metrics_generator.run()
