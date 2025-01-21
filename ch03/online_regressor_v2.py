import json
import numpy as np
import pika
from river import compose
from river import linear_model
from river import preprocessing


class OnlineRegressorV2:
    def __init__(self, stream_name):
        self.stream_name = stream_name
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

        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.stream_name,
            durable=True,
            arguments={"x-queue-type": "stream"},
        )
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(
            queue=self.stream_name,
            on_message_callback=self.process_message,
            arguments={"x-stream-offset": "first"},
        )
        channel.start_consuming()


regressor = OnlineRegressorV2(
    stream_name="flight_events",
)
regressor.run()
