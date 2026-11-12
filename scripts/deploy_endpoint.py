"""Create an endpoint and deploy a registered model on n1-standard-8 + 1 T4 (min = max = 1 node).

Billed per hour while deployed, NO scale to zero: delete it after every session (scripts/delete_endpoint.py).
Deployment takes 15 to 30 minutes when a T4 is free in europe-west2.

Run:
  uv run python -m scripts.deploy_endpoint --model <model resource name from the registration script>
"""

import argparse

from google.cloud import aiplatform

from src.constants import PIPELINE_LABELS, PROJECT_ID, REGION

ENDPOINT_DISPLAY_NAME = "benjosh-socratic-tutor-endpoint"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="registered model resource name")
    args = parser.parse_args()
    aiplatform.init(project=PROJECT_ID, location=REGION)
    model = aiplatform.Model(args.model)
    endpoint = aiplatform.Endpoint.create(display_name=ENDPOINT_DISPLAY_NAME, labels=PIPELINE_LABELS)
    print(f"Endpoint created: {endpoint.resource_name}")
    print(f"Add to .env: GCP_ENDPOINT_ID={endpoint.name}")
    print("Deploying (15 to 30 min when a T4 is free); this command waits until it is done...")
    model.deploy(
        endpoint=endpoint,
        machine_type="n1-standard-8",
        accelerator_type="NVIDIA_TESLA_T4",
        accelerator_count=1,
        min_replica_count=1,
        max_replica_count=1,
        deployed_model_display_name="benjosh-socratic-tutor",
    )
    print(f"Deployed. Endpoint id: {endpoint.name}. Remember: python -m scripts.delete_endpoint --endpoint {endpoint.name}")


if __name__ == "__main__":
    main()
