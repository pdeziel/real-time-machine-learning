import json
import numpy as np
import pika
from river import compose
from river import linear_model
from river import preprocessing


class OnlineRegressorV3:
    def __init__(self, subscribe_stream_name, publish_stream_name):
        self.subscribe_stream_name = subscribe_stream_name
        self.publish_stream_name = publish_stream_name
        self.flights = {}
        self.model = compose.Pipeline(
            ("scale", preprocessing.StandardScaler()),
            ("lin_reg", linear_model.LinearRegression()),
        )

    def check_duplicate(self, event):
        if (
            event["icao24"] in self.flights
            and event["time"] == self.flights[event["icao24"]]["time"]
        ):
            return True
        self.flights[event["icao24"]] = event
        return False

    def publish_model_event(self, event):
        print(f"Sending model event: {event}")
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.publish_stream_name,
            durable=True,
            arguments={"x-queue-type": "stream"},
        )
        channel.basic_publish(
            exchange="", routing_key=self.publish_stream_name, body=json.dumps(event)
        )
        connection.close()

    def process_message(self, channel, method, properties, body):
        data = json.loads(body)
        if not self.check_duplicate(data):
            time = data["time"]
            geoaltitude = data["geoaltitude"]
            if geoaltitude is not None and np.isnan(geoaltitude) == False:
                features = {"time": time, "geoaltitude": geoaltitude}
                velocity_pred = self.model.predict_one(features)
                velocity = data["velocity"]
                if velocity is not None:
                    self.model.learn_one(features, velocity)
                    print(
                        f"geoaltitude: {geoaltitude}, velocity_pred: {velocity_pred}, velocity: {velocity}"
                    )
                    event = {
                        "time": data["time"],
                        "callsign": data["callsign"],
                        "icao24": data["icao24"],
                        "geoaltitude": geoaltitude,
                        "velocity": velocity,
                        "velocity_pred": velocity_pred,
                    }
                    self.publish_model_event(event)

        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.subscribe_stream_name,
            durable=True,
            arguments={"x-queue-type": "stream"},
        )
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(
            queue=self.subscribe_stream_name,
            on_message_callback=self.process_message,
            arguments={"x-stream-offset": "first"},
        )
        channel.start_consuming()


regressor = OnlineRegressorV3(
    subscribe_stream_name="flight_events", publish_stream_name="flight_predictions"
)
regressor.run()
