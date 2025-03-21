import json
import pika
import random


class FeedbackGenerator:
    def __init__(self, subscribe_stream_name, publish_stream_name):
        self.subscribe_stream_name = subscribe_stream_name
        self.publish_stream_name = publish_stream_name
        self.choices = ["positive", "negative", "neutral"]

    def publish_rating_event(self, event):
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
        response_data = json.loads(body)
        print(f"Received response data: {response_data}")
        interaction_id = response_data["conversation_id"]
        feedback = random.choice(self.choices)
        rating_event = {}
        rating_event["conversation_id"] = interaction_id
        rating_event["event_type"] = "feedback"
        rating_event["rating"] = feedback
        print(f"Generated rating event: {rating_event}")
        self.publish_rating_event(rating_event)

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


feedback_generator = FeedbackGenerator(
    subscribe_stream_name="responses", publish_stream_name="interactions"
)
feedback_generator.run()
