from datasets import Dataset, load_dataset
import json
import pika
import time


class ChatPublisher:
    def __init__(self, interval_sec, stream_name):
        self.interval_sec = interval_sec
        self.stream_name = stream_name

    def get_chat_events(self):
        chat_event = {}
        webgpt_data = load_dataset("openai/webgpt_comparisons", split="train")
        webgpt_data = webgpt_data.select(range(5))
        for i, rec in enumerate(webgpt_data):
            question = rec["question"]["full_text"]
            chat_event["id"] = i
            chat_event["event_type"] = "prompt"
            chat_event["messages"] = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": question},
            ]
            yield chat_event
            time.sleep(self.interval_sec)

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.stream_name, durable=True, arguments={"x-queue-type": "stream"}
        )

        for event in self.get_chat_events():
            print("Sending chat event:", event)
            channel.basic_publish(
                exchange="", routing_key=self.stream_name, body=json.dumps(event)
            )

        connection.close()


chat_publisher = ChatPublisher(
    interval_sec=60,
    stream_name="interactions",
)
chat_publisher.run()
