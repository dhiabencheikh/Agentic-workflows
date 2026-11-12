"""Pipeline compilation and submission utilities for Vertex AI.

Usage:
    uv run python -m scripts.pipeline_runner --mode smoke   # short GPU test run
    uv run python -m scripts.pipeline_runner --mode full    # real fine-tuning run
"""

import argparse

from google.cloud import aiplatform
from kfp import compiler

from src.constants import (
    BASE_MODEL_ID,
    BASE_MODEL_REVISION,
    FINE_TUNING_HYPERPARAMETERS,
    NUM_VALIDATION_PROBLEMS,
    PIPELINE_ROOT_PATH,
    PROJECT_ID,
    RAW_DATASET_URI,
    REGION,
    RUN_MODES,
    SPLIT_SEED,
)
from src.pipelines.model_training_pipeline import model_training_pipeline
from src.prompts import TUTOR_PROMPT_VERSION, load_tutor_prompt

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=sorted(RUN_MODES), required=True)
    mode = RUN_MODES[parser.parse_args().mode]

    aiplatform.init(project=PROJECT_ID, location=REGION)

    pipeline_name = "model_training_pipeline"
    compiler.Compiler().compile(
        pipeline_func=model_training_pipeline,  # type: ignore
        package_path=f"{pipeline_name}.json",
    )
    job = aiplatform.PipelineJob(
        display_name=f"{pipeline_name}-{mode['name']}",
        template_path=f"{pipeline_name}.json",
        pipeline_root=f"gs://{PIPELINE_ROOT_PATH}",
        enable_caching=True,  # reuse the data step output when its inputs are unchanged
        parameter_values={
            "raw_dataset_uri": RAW_DATASET_URI,
            "system_prompt": load_tutor_prompt(TUTOR_PROMPT_VERSION),
            "prompt_version": TUTOR_PROMPT_VERSION,
            "num_validation_problems": NUM_VALIDATION_PROBLEMS,
            "seed": SPLIT_SEED,
            "base_model_id": BASE_MODEL_ID,
            "base_model_revision": BASE_MODEL_REVISION,
            "hyperparameters": FINE_TUNING_HYPERPARAMETERS,
            "max_steps": mode["max_steps"],
            "max_train_cards": mode["max_train_cards"],
        },
    )
    job.submit()
