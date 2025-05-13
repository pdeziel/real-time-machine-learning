import uuid
import gradio as gr

from utils.publisher import StreamPublisher
from utils.subscriber import StreamSubscriber


class ChatApp:
    def __init__(
        self, interactions_stream="interactions", responses_stream="responses"
    ):
        self.publisher = StreamPublisher(interactions_stream)
        self.subscriber = StreamSubscriber(responses_stream)
        self.conversation_id = str(uuid.uuid4())

    def on_chat(self, message, chat_history):
        """
        This function is called when the user sends a message to the chatbot.
        It publishes the user message to an event stream and waits for a response.
        """

        # Flush the queue to ensure the response is the latest one
        self.subscriber.flush()
        payload = {
            "conversation_id": self.conversation_id,
            "messages": chat_history + [{"role": "user", "content": message}],
        }
        self.publisher.publish(payload)
        response = self.subscriber.get_one()
        self.conversation_id = response["conversation_id"]
        return response["messages"][-1]["content"]

    def on_vote(self, data: gr.LikeData):
        """
        This function is called when the user votes on a response.
        It publishes the vote to an event stream.
        """

        payload = {
            "conversation_id": self.conversation_id,
            "rating": "positive" if data.liked else "negative",
        }
        self.publisher.publish(payload)

    def on_clear(self):
        self.conversation_id = str(uuid.uuid4())

    def run(self):
        css = """
        #chatbot {background-color: lightgray}
        """

        self.subscriber.start(block=False, stream_offset="last")
        with gr.Blocks(
            theme=gr.themes.Glass(
                text_size="lg",
            ),
            css=css,
        ) as app:
            chatbot = gr.Chatbot(type="messages", render=False, elem_id="chatbot")
            chatbot.like(self.on_vote)
            chatbot.clear(self.on_clear)
            textbox = gr.Textbox(
                placeholder="Enter a message to chat with the model",
                elem_id="chatbot",
                render=False,
            )
            gr.ClearButton([chatbot, textbox], render=False)
            gr.ChatInterface(
                self.on_chat,
                type="messages",
                chatbot=chatbot,
                textbox=textbox,
                title="Model chat",
            )
            app.launch()
        self.subscriber.stop()


if __name__ == "__main__":
    app = ChatApp()
    app.run()
