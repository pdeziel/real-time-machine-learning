import json
import os
import time

from datasets import Dataset
import pika
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from trl import (
    PPOTrainer,
    PPOConfig,
    AutoModelForCausalLMWithValueHead,
    create_reference_model,
    ModelConfig,
)
from peft import LoraConfig, get_peft_model, TaskType
from accelerate import Accelerator


class RealTimePPOTrainer:
    def __init__(self, config=None, model_name="Qwen/Qwen2.5-0.5B-Instruct"):
        self.config = config
        if self.config is None:
            self.config = {}
        self.model_name = model_name
        self.model_dir = self.config.get("model_dir", "model_output")
        self.log_dir = self.config.get("log_dir", "log_output")
        self.interactions_stream_name = self.config.get(
            "interactions_stream_name", "interactions"
        )
        self.responses_stream_name = self.config.get(
            "responses_stream_name", "responses"
        )
        self.checkpoint_steps = self.config.get("checkpoint_steps", 2)
        self.ref_model = None
        self.ppo_model = None
        self.ppo_trainer = None
        self.ppo_trained_model = None
        self.ppo_trained_tokenizer = None
        self.ppo_config = PPOConfig(
            model_name=model_name,
            learning_rate=1.41e-5,
            batch_size=1,
            mini_batch_size=1,
            gradient_accumulation_steps=1,
            log_with="tensorboard",
            project_kwargs={"logging_dir": self.log_dir},
        )
        self.num_steps = 0
        self.interaction_info = {}  # to track interactions and rewards
        self.initialize_model()

    def initialize_model(self):
        if torch.cuda.is_available():
            self.device = torch.device("cuda")
        elif torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.accelerator = Accelerator(cpu=True)
            self.device = torch.device("cpu")
        lora_config = LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.1,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name, device_map=self.device
        )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        peft_model = get_peft_model(self.model, lora_config)
        self.ppo_model = AutoModelForCausalLMWithValueHead.from_pretrained(
            peft_model, device_map=self.device
        )
        self.ref_model = create_reference_model(self.ppo_model)
        self.generation_kwargs = {
            "top_p": 1.0,
            "top_k": 0.0,
            "do_sample": True,
            "max_new_tokens": 128,
        }
        self.ppo_trainer = PPOTrainer(
            config=self.ppo_config,
            model=self.ppo_model,
            ref_model=self.ref_model,
            tokenizer=self.tokenizer,
        )
        self.ppo_trainer.current_device = self.device

    def publish_model_response(self, prompt_response):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.responses_stream_name,
            durable=True,
            arguments={"x-queue-type": "stream"},
        )
        channel.basic_publish(
            exchange="",
            routing_key=self.responses_stream_name,
            body=json.dumps(prompt_response),
        )
        connection.close()

    def get_rating_score(self, rating):
        if rating == "positive":
            return 1.0
        elif rating == "negative":
            return -1.0
        elif rating == "neutral":
            return 0.0

    def process_rating_data(self, rating_data):
        rating = rating_data["rating"]
        interaction_id = rating_data["id"]
        if interaction_id in self.interaction_info:
            interaction_details = self.interaction_info[interaction_id]
            query_tensors = interaction_details["query_tensors"]
            response_tensors = interaction_details["response_tensors"]
            rating_score = self.get_rating_score(rating)
            rewards = [torch.tensor(rating_score)]
            stats = self.ppo_trainer.step(query_tensors, response_tensors, rewards)
            print(self.ppo_trainer.model.parameters())
            self.ppo_trainer.log_stats(stats, interaction_details, rewards)
            self.num_steps += 1
            if self.num_steps == self.checkpoint_steps:
                timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                model_checkpoint = f"{self.model_dir}/model/checkpoint-{timestamp}"
                os.makedirs(model_checkpoint, exist_ok=True)
                tokenizer_checkpoint = (
                    f"{self.model_dir}/tokenizer/checkpoint-{timestamp}"
                )
                os.makedirs(tokenizer_checkpoint, exist_ok=True)
                self.ppo_trainer.model.save_pretrained(model_checkpoint)
                self.ppo_trainer.tokenizer.save_pretrained(tokenizer_checkpoint)
                print("saved model checkpoint")
                self.num_steps = 0
        else:
            print(f"Interaction not found for ID {interaction_id}")

    def tokenize(self, sample):
        sample["templated_text"] = self.tokenizer.apply_chat_template(
            sample["messages"], tokenize=False, add_generation_prompt=True
        )
        sample["input_ids"] = self.tokenizer.encode(
            sample["templated_text"], return_tensors="pt"
        ).to(self.device)
        return sample

    def process_prompt_data(self, prompt_data):
        # ppo_data = {}
        messages = prompt_data["messages"]
        print(messages)
        messages_dict = {"messages": [messages]}
        print(messages_dict)
        messages_dataset = Dataset.from_dict(messages_dict)
        print(messages_dataset[0])
        messages_dataset = messages_dataset.map(self.tokenize, batched=False)
        messages_dataset.set_format(
            type="torch", columns=["input_ids"], device=self.device
        )
        query_tensors = [q.squeeze() for q in messages_dataset["input_ids"]]
        response_tensors = []
        for query in query_tensors:
            query_response = self.ppo_trainer.generate(
                query, **self.generation_kwargs
            ).squeeze()[len(query) :]
            response_tensors.append(query_response)
        response = [
            self.tokenizer.decode(r, skip_special_tokens=True) for r in response_tensors
        ]
        # append response to messages
        messages.append({"role": "assistant", "content": response[0]})
        print(f"Updated messages: {messages}")
        # update prompt data
        prompt_data["messages"] = messages
        # add interaction details to interaction_info
        interaction_details = {}
        interaction_id = prompt_data["id"]
        interaction_details["messages"] = prompt_data["messages"]
        interaction_details["query_tensors"] = query_tensors
        interaction_details["response_tensors"] = response_tensors
        interaction_details["response"] = response
        self.interaction_info[interaction_id] = interaction_details
        self.publish_model_response(prompt_data)

    def process_interaction(self, channel, method, properties, body):
        interaction = json.loads(body)
        print("Received interaction:", interaction)
        event_type = interaction.get("event_type", None)
        if event_type == "prompt":
            messages = interaction["messages"]
            if len(messages) > 0:
                self.process_prompt_data(interaction)
            else:
                print("No messages found in the prompt event.")
        elif event_type == "feedback":
            print("Processing feedback event:", interaction)
            rating = interaction["rating"]
            if rating is not None:
                self.process_rating_data(interaction)
            else:
                print("No rating found in the feedback event.")
        else:
            print("Unknown event type:", event_type)

        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        connection = pika.BlockingConnection(pika.ConnectionParameters("localhost"))
        channel = connection.channel()
        channel.queue_declare(
            queue=self.interactions_stream_name,
            durable=True,
            arguments={"x-queue-type": "stream"},
        )
        channel.basic_qos(prefetch_count=1)
        channel.basic_consume(
            queue=self.interactions_stream_name,
            on_message_callback=self.process_interaction,
            arguments={"x-stream-offset": "first"},
        )
        channel.start_consuming()


ppo_trainer = RealTimePPOTrainer()
ppo_trainer.run()
