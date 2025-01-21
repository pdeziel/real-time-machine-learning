import json
import pika
import time
import pandas as pd


class FlightPublisher:
    def __init__(self, file_path, interval_sec, stream_name):
        self.file_path = file_path
        self.interval_sec = interval_sec
        self.stream_name = stream_name

    def get_events(self):
        flights_df = pd.read_csv(self.file_path)
        for _, row in flights_df.iterrows():
            yield (row.to_dict())
            time.sleep(self.interval_sec)

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.stream_name, durable=True, arguments={"x-queue-type": "stream"}
        )

        for event in self.get_events():
            print("Sending flight update:", event)
            channel.basic_publish(
                exchange="", routing_key=self.stream_name, body=json.dumps(event)
            )

        connection.close()


publisher = FlightPublisher(
    file_path="states_2022-06-27-08-sample.csv",
    interval_sec=1,
    stream_name="flight_events",
)
publisher.run()
