import json
import pika
import time
from urllib import request


class FlightPublisherV3:
    def __init__(self, url, interval_sec, stream_name):
        self.url = url
        self.interval_sec = interval_sec
        self.stream_name = stream_name

    def response_to_events(self, api_response):
        flight_events = []
        for update in api_response["states"]:
            flight_events.append(
                {
                    "icao24": update[0],
                    "origin_country": update[2],
                    "time_position": update[3],
                    "longitude": update[5],
                    "latitude": update[6],
                    "velocity": update[9],
                    "true_track": update[10],
                }
            )
        return sorted(flight_events, key=lambda x: x["time_position"])

    def get_events(self):
        while True:
            with request.urlopen(self.url) as response:
                yield from self.response_to_events(
                    json.loads(response.read().decode("utf-8"))
                )
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


publisher = FlightPublisherV3(
    url="https://opensky-network.org/api/states/all?lamin=45.8389&lomin=5.9962&lamax=47.8229&lomax=10.5226",
    interval_sec=60,
    stream_name="flight_events",
)
publisher.run()
