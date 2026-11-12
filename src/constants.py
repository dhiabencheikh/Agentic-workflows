"""Main constants of the project."""

import os
from pathlib import Path

from dotenv import load_dotenv

# Paths
PROJECT_ROOT_PATH = Path(__file__).parents[1]

# Copy the values written in .env into the environment variables,
# so the os.getenv calls below find them. Variables already set
# in the shell (for example in CI) are kept and win over .env.
load_dotenv(PROJECT_ROOT_PATH / ".env")

# GCP Configuration
PROJECT_ID: str | None = os.getenv("GCP_PROJECT_ID")
REGION: str = os.getenv("GCP_REGION", "europe-west2")
BUCKET_NAME: str | None = os.getenv("GCP_BUCKET_NAME")

# Paths
RAW_DATASET_URI: str = f"gs://{BUCKET_NAME}/raw/socratic_debugging_benchmark/v2_sigcse"
PIPELINE_ROOT_PATH: str = f"{BUCKET_NAME}/vertexai-pipeline-root/"

# Data split: validation problems are drawn from the authors' train folder
NUM_VALIDATION_PROBLEMS: int = 4
SPLIT_SEED: int = 42

# Base model, pinned to one Hugging Face commit so that weights, tokenizer and
# chat template cannot change under us. Use BOTH values everywhere the model or
# tokenizer is loaded: data checks, fine-tuning, inference, serving.
# Revision checked on 2026-11-12: it was the head of `main`, last modified 2025-12-10.
BASE_MODEL_ID: str = "microsoft/Phi-3-mini-4k-instruct"
BASE_MODEL_REVISION: str = "f39ac1d28e925b323eae81227eaba4464caced4e"

# Fine-tuning hyper-parameters: the single place to change them. The whole dict
# is passed to the fine-tuning component, logged to Vertex and saved with the model.
# Starting values (M2 decision D3): LoRA and learning rate as in the course article,
# fewer epochs than its 10, best checkpoint kept by validation loss.
FINE_TUNING_HYPERPARAMETERS: dict = {
    # LoRA (Session 3 slide 11): W' = W + (alpha / r) * BA
    "lora_r": 8,
    "lora_alpha": 16,
    "lora_dropout": 0.05,
    "lora_target_modules": ["o_proj", "qkv_proj", "gate_up_proj", "down_proj"],
    # Training (Session 3 slide 12)
    "learning_rate": 3e-4,
    "num_train_epochs": 3,
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 8,  # effective batch = 2 x 8 = 16 cards per update
    "per_device_eval_batch_size": 2,
    # Above the longest card (2066 tokens, docs/results/m2_finetuning_prep.md): no card is cut
    "max_seq_length": 2304,
    "eval_steps": 10,  # validation loss every 10 updates, best checkpoint kept
    "logging_steps": 5,
    "seed": 42,
}

# Pipeline run modes (scripts/pipeline_runner.py --mode ...)
# smoke: a short paid GPU test on the LONGEST training cards (worst case for memory),
#        to check that training fits on a T4 and to measure seconds per step before a full run.
RUN_MODES: dict = {
    "smoke": {"name": "smoke", "max_steps": 20, "max_train_cards": 40},
    "full": {"name": "full", "max_steps": -1, "max_train_cards": 0},
}
