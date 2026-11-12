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
