import json
import time
from urllib import request


class FlightPublisherV1:
    def __init__(self, lat_min, lat_max, long_min, long_max, interval_sec, file_path):
        self.lat_min = lat_min
        self.lat_max = lat_max
        self.long_min = long_min
        self.long_max = long_max
        self.url = f"https://opensky-network.org/api/states/all?lamin={lat_min}&lomin={long_min}&lamax={lat_max}&lomax={long_max}"
        self.interval_sec = interval_sec
        self.file_path = file_path

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
        for event in self.get_events():
            with open(self.file_path, "a") as file:
                file.write(json.dumps(event) + "\n")


publisher = FlightPublisherV1(
    lat_min=45.8389,
    lat_max=47.8229,
    long_min=5.9962,
    long_max=10.5226,
    interval_sec=60,
    file_path="flight_updates.jsonl",
)
publisher.run()
