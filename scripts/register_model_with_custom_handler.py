"""Register the fine-tuned model in Vertex AI Model Registry with the custom handler (Session 4 practice).

Uploads next to the adapter, at the root of the model artifacts folder:
  handler.py           src/handler.py
  serving_config.json  src/serving_contract.build_serving_config() (decoding, dtype, model revision, prompt version)
  <prompt file>        prompts/tutor_system_v<version>.txt
then registers the folder with the pre-built Hugging Face serving image.

Run:
  uv run python -m scripts.register_model_with_custom_handler --model-uri gs://.../model [--parent-model <resource>]
"""

import argparse
import json

from google.cloud import aiplatform, storage

from src.constants import BUCKET_NAME, PIPELINE_LABELS, PROJECT_ID, PROJECT_ROOT_PATH, REGION
from src.prompts import TUTOR_PROMPT_VERSION, tutor_prompt_path
from src.serving_contract import SERVING_CONFIG_FILENAME, build_serving_config

SERVING_IMAGE = (
    "us-docker.pkg.dev/deeplearning-platform-release/gcr.io/"
    "huggingface-pytorch-inference-cu121.2-3.transformers.4-46.ubuntu2204.py311"
)
MODEL_DISPLAY_NAME = "benjosh-socratic-tutor"


def upload_serving_files(model_uri: str) -> list:
    """Put handler, config and prompt at the root of the model artifacts folder."""
    prefix = model_uri.replace(f"gs://{BUCKET_NAME}/", "").rstrip("/")
    bucket = storage.Client(project=PROJECT_ID).bucket(BUCKET_NAME)
    config = build_serving_config(TUTOR_PROMPT_VERSION)
    uploads = [
        ("handler.py", (PROJECT_ROOT_PATH / "src" / "handler.py").read_text(encoding="utf-8"), "text/x-python"),
        (SERVING_CONFIG_FILENAME, json.dumps(config, indent=2), "application/json"),
        (config["prompt_file"], tutor_prompt_path(TUTOR_PROMPT_VERSION).read_text(encoding="utf-8"), "text/plain"),
    ]
    for name, content, content_type in uploads:
        bucket.blob(f"{prefix}/{name}").upload_from_string(content, content_type=content_type)
    if not bucket.blob(f"{prefix}/adapter_config.json").exists():
        raise FileNotFoundError(f"No adapter_config.json in {model_uri}: is this the fine-tuning 'model' output?")
    return [name for name, _, _ in uploads]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-uri", required=True, help="the 'model' output folder of the fine-tuning step")
    parser.add_argument("--display-name", default=MODEL_DISPLAY_NAME)
    parser.add_argument("--parent-model", default=None, help="register as a new version of this model")
    parser.add_argument("--region", default=REGION, help="GCP region (default: GCP_REGION from .env)")
    args = parser.parse_args()

    uploaded = upload_serving_files(args.model_uri)
    print(f"Uploaded to {args.model_uri}: {', '.join(uploaded)}")
    aiplatform.init(project=PROJECT_ID, location=args.region)
    model = aiplatform.Model.upload(
        display_name=args.display_name,
        artifact_uri=args.model_uri,
        serving_container_image_uri=SERVING_IMAGE,
        serving_container_ports=[8080],
        parent_model=args.parent_model,
        labels={**PIPELINE_LABELS, "prompt-version": TUTOR_PROMPT_VERSION.replace(".", "-")},
        description=f"Socratic tutor: Phi-3 + LoRA, prompt v{TUTOR_PROMPT_VERSION}, fp16, greedy decoding",
    )
    print(f"Registered model: {model.resource_name} (version {model.version_id})")


if __name__ == "__main__":
    main()
