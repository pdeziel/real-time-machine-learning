import csv
import os
import json
import pika
from river import metrics


class MetricsGeneratorV2:
    def __init__(self, stream_name, file_path):
        self.stream_name = stream_name
        self.file_path = file_path
        self.metric = metrics.MAE()

    def write_to_csv(self, data):
        file_exists = os.path.isfile(self.file_path)
        with open(self.file_path, mode="a", newline="") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=data.keys())
            if not file_exists:
                writer.writeheader()
            writer.writerow(data)

    def process_message(self, channel, method, properties, body):
        data = json.loads(body)
        velocity = data["velocity"]
        velocity_pred = data["velocity_pred"]
        self.metric.update(velocity, velocity_pred)
        mae = self.metric.get()
        print(f"velocity_pred: {velocity_pred}, velocity: {velocity}, mae: {mae}")
        metric_data = {
            "time": data["time"],
            "callsign": data["callsign"],
            "icao24": data["icao24"],
            "geoaltitude": data["geoaltitude"],
            "velocity_pred": velocity_pred,
            "velocity": velocity,
            "mae": mae,
        }
        self.write_to_csv(metric_data)

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


metrics_generator = MetricsGeneratorV2(
    stream_name="flight_predictions", file_path="metrics.csv"
)
metrics_generator.run()
