import json
import pika


class FlightSubscriberV2:
    def __init__(self, stream_name):
        self.stream_name = stream_name
        self.flights = {}

    def check_duplicate(self, event):
        if (
            event["icao24"] in self.flights
            and event["time_position"] == self.flights[event["icao24"]]["time_position"]
        ):
            return True
        self.flights[event["icao24"]] = event
        return False

    def process_message(self, channel, method, properties, body):
        data = json.loads(body)
        if not self.check_duplicate(data):
            print(f"Received flight update: {data}")
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


subscriber = FlightSubscriberV2(stream_name="flight_events")
subscriber.run()
