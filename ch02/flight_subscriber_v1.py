import pika


class FlightSubscriberV1:
    def __init__(self, queue_name):
        self.queue_name = queue_name

    def process_message(self, channel, method, properties, body):
        print(f"Received flight update: {body}")

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(queue=self.queue_name)
        channel.basic_consume(
            queue=self.queue_name,
            on_message_callback=self.process_message,
            auto_ack=False,
        )
        channel.start_consuming()


subscriber = FlightSubscriberV1(queue_name="flight_updates")
subscriber.run()
