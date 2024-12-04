import json
import pika


def handle_message(channel, method, properties, body):
    print(f"Received message: {body}")


connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
channel = connection.channel()
channel.queue_declare(queue="flight_updates")
channel.basic_consume(
    queue="flight_updates", on_message_callback=handle_message, auto_ack=True
)
channel.start_consuming()
