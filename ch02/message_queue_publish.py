import json
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
channel = connection.channel()
channel.queue_declare(queue="flight_updates")
data = {"icao24": "abc123", "origin_country": "United States"}
channel.basic_publish(exchange="", routing_key="flight_updates", body=json.dumps(data))
print("Sent message:", data)
connection.close()
