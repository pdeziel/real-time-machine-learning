import json
import os
import time
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from trl import (
    PPOTrainer,
    PPOConfig,
    AutoModelForCausalLMWithValueHead,
    create_reference_model,
)
from peft import LoraConfig, get_peft_model, TaskType

from utils.publisher import StreamPublisher
from utils.subscriber import StreamSubscriber


class RealTimePPOTrainer:
    def __init__(
        self,
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        interactions_stream="interactions",
        responses_stream="responses",
        model_dir="tuned_models",
        log_dir="logs",
        checkpoint_steps=2,
        device_map="auto",
    ):
        self.model_name = model_name
        self.model_dir = model_dir
        self.log_dir = log_dir
        self.checkpoint_steps = checkpoint_steps
        self.publisher = StreamPublisher(responses_stream)
        self.subscriber = StreamSubscriber(interactions_stream)
        self.ppo_config = PPOConfig(
            model_name=self.model_name,
            learning_rate=1.41e-5,
            batch_size=1,
            mini_batch_size=1,
            gradient_accumulation_steps=1,
            log_with="tensorboard",
            project_kwargs={"logging_dir": self.log_dir},
        )
        self.num_steps = 0
        self.conversations = {}  # to track interactions and rewards
        self.initialize_model(device_map)

    def initialize_model(self, device_map):
        lora_config = LoraConfig(
            r=8,
            lora_alpha=16,
            lora_dropout=0.1,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            self.model_name, device_map=device_map
        )
        self.tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        peft_model = get_peft_model(self.model, lora_config)
        self.ppo_model = AutoModelForCausalLMWithValueHead.from_pretrained(
            peft_model, device_map=device_map
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
        self.device = self.model.device
        self.ppo_trainer.current_device = self.device

    def rating_to_score(self, rating):
        if rating == "positive":
            return 1.0
        elif rating == "negative":
            return -1.0
        else:
            return 0.0

    def process_rating_data(self, rating_data):
        """
        This function is called when the subscriber receives a rating for a
        conversation in order to incrementally train the model.
        """

        rating = rating_data["rating"]
        id = rating_data["conversation_id"]
        if id in self.conversations:
            # Get the cached conversation info
            info = self.conversations[id]
            query_tensors = info["query_tensors"]
            response_tensors = info["response_tensors"]
            rewards = [torch.tensor(self.rating_to_score(rating))]

            # Train a step with the observed rewards
            print(f"training step for conversation {id}, rewards: {rewards}")
            stats = self.ppo_trainer.step(query_tensors, response_tensors, rewards)
            self.ppo_trainer.log_stats(stats, info, rewards)
            self.num_steps += 1

            # Save the latest checkpoint of the model
            if self.num_steps % self.checkpoint_steps == 0:
                timestamp = time.strftime("%Y-%m-%d_%H-%M-%S", time.localtime())
                model_checkpoint = f"{self.model_dir}/model/checkpoint-{timestamp}"
                os.makedirs(model_checkpoint, exist_ok=True)
                tokenizer_checkpoint = (
                    f"{self.model_dir}/tokenizer/checkpoint-{timestamp}"
                )
                os.makedirs(tokenizer_checkpoint, exist_ok=True)
                self.ppo_trainer.model.save_pretrained(model_checkpoint)
                self.ppo_trainer.tokenizer.save_pretrained(tokenizer_checkpoint)
                print(
                    f"step: {self.num_steps}, saved model checkpoint to {model_checkpoint}"
                )
        else:
            print(f"error: interaction not found for ID {id}")

    def tokenize(self, messages):
        templated_text = self.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        messages_tokenized = self.tokenizer.encode(
            templated_text, return_tensors="pt"
        ).to(self.device)
        return messages_tokenized

    def process_prompt_data(self, prompt_data):
        """
        This function is called when a user message is received and generates a
        response completion using the current model.
        """

        messages = prompt_data["messages"]
        query_tensors = [q.squeeze() for q in self.tokenize(messages)]
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
        # update prompt data
        prompt_data["messages"] = messages
        # update the conversation in local memory
        info = {}
        id = prompt_data["conversation_id"]
        info["messages"] = prompt_data["messages"]
        info["query_tensors"] = query_tensors
        info["response_tensors"] = response_tensors
        info["response"] = response
        self.conversations[id] = info

        # Publish the completed messages to the outgoing stream
        self.publisher.publish(prompt_data)

    def process_interaction(self, channel, method, properties, body):
        print(f"Received interaction: {body}")
        interaction = json.loads(body)
        if "messages" in interaction and interaction["messages"][-1]["role"] == "user":
            self.process_prompt_data(interaction)
        elif "rating" in interaction:
            self.process_rating_data(interaction)
        else:
            print("error: unrecognized event schema")
        channel.basic_ack(delivery_tag=method.delivery_tag)

    def run(self):
        """
        Run the subscriber stream and respond to interaction events.
        """

        self.subscriber.start(
            block=True,
            on_message_callback=self.process_interaction,
            stream_offset="last",
        )


if __name__ == "__main__":
    ppo_trainer = RealTimePPOTrainer()
    ppo_trainer.run()
