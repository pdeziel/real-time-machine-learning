import json
import pika
import time
from urllib import request
import pandas as pd


class FlightPublisher:
    def __init__(self, stream_name):
        self.stream_name = stream_name

    def get_events(self):
        flights_df = pd.read_csv("states_2022-06-27-08.csv")
        flights_df_filtered = flights_df.loc[flights_df.callsign.str.strip().isin(["ARP41"])]
        for _, row in flights_df_filtered.iterrows():
            yield(row.to_dict())
            time.sleep(1)

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
    stream_name="flight_events",
)
publisher.run()
