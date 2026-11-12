"""Compile and submit the M3 evaluation pipeline to Vertex AI.

Usage:
    uv run python -m scripts.evaluation_runner --adapter-uri gs://.../model --mode smoke
    uv run python -m scripts.evaluation_runner --adapter-uri gs://.../model --mode full \
        [--extra-cases-uri gs://.../cases_adversarial.jsonl]
"""

import argparse

from google.cloud import aiplatform
from kfp import compiler

from src.constants import (
    BASE_MODEL_ID,
    BASE_MODEL_REVISION,
    EVAL_PIPELINE_NAME,
    EVAL_RUN_MODES,
    GENERATION_PARAMETERS,
    M1_TEST_DATASET_URI,
    PIPELINE_LABELS,
    PIPELINE_ROOT_PATH,
    PROJECT_ID,
    REGION,
)
from src.pipelines.evaluation_pipeline import build_evaluation_pipeline
from src.prompts import TUTOR_PROMPT_VERSION, load_tutor_prompt

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=sorted(EVAL_RUN_MODES), required=True)
    parser.add_argument("--adapter-uri", required=True, help="the 'model' output of the fine-tuning step")
    parser.add_argument("--extra-cases-uri", default="", help="optional JSONL of hand-written cases (gs://)")
    parser.add_argument("--setups", default="a,b,c", help="comma-separated subset of a,b,c, run in this order")
    args = parser.parse_args()
    mode = EVAL_RUN_MODES[args.mode]

    aiplatform.init(project=PROJECT_ID, location=REGION)
    setups = tuple(s.strip() for s in args.setups.split(",") if s.strip())
    compiler.Compiler().compile(pipeline_func=build_evaluation_pipeline(setups), package_path=f"{EVAL_PIPELINE_NAME}.json")  # type: ignore
    job = aiplatform.PipelineJob(
        display_name=f"{EVAL_PIPELINE_NAME}-{args.mode}-{''.join(setups)}",
        template_path=f"{EVAL_PIPELINE_NAME}.json",
        pipeline_root=f"gs://{PIPELINE_ROOT_PATH}",
        enable_caching=True,
        labels={**PIPELINE_LABELS, "run-mode": mode["name"], "setups": "-".join(setups)},
        parameter_values={
            "test_dataset_uri": M1_TEST_DATASET_URI,
            "adapter_uri": args.adapter_uri,
            "base_model_id": BASE_MODEL_ID,
            "base_model_revision": BASE_MODEL_REVISION,
            "system_prompt": load_tutor_prompt(TUTOR_PROMPT_VERSION),
            "prompt_version": TUTOR_PROMPT_VERSION,
            "generation": GENERATION_PARAMETERS,
            "extra_cases_uri": args.extra_cases_uri,
            "max_cases": mode["max_cases"],
        },
    )
    job.submit()
