"""Create an endpoint and deploy a registered model on n1-standard-8 + 1 T4 (min = max = 1 node).

Billed per hour while deployed, NO scale to zero: delete it after every session (scripts/delete_endpoint.py).
Deployment takes 15 to 30 minutes when a T4 is free in europe-west2.

Run:
  uv run python -m scripts.deploy_endpoint --model <model resource name from the registration script>
"""

import argparse
import time

from google.api_core.exceptions import ServiceUnavailable

from google.cloud import aiplatform

from src.constants import PIPELINE_LABELS, PROJECT_ID, REGION

ENDPOINT_DISPLAY_NAME = "benjosh-socratic-tutor-endpoint"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", required=True, help="registered model resource name")
    parser.add_argument("--endpoint", default=None, help="reuse an existing (empty) endpoint id instead of creating one")
    parser.add_argument("--retries", type=int, default=3, help="retries when no T4 is available (503)")
    parser.add_argument("--retry-wait", type=int, default=180, help="seconds between retries")
    args = parser.parse_args()
    aiplatform.init(project=PROJECT_ID, location=REGION)
    model = aiplatform.Model(args.model)
    if args.endpoint:
        endpoint = aiplatform.Endpoint(args.endpoint)
        print(f"Reusing endpoint: {endpoint.resource_name}")
    else:
        endpoint = aiplatform.Endpoint.create(display_name=ENDPOINT_DISPLAY_NAME, labels=PIPELINE_LABELS)
        print(f"Endpoint created: {endpoint.resource_name}")
    print(f"Add to .env: GCP_ENDPOINT_ID={endpoint.name}")
    print("Deploying (15 to 30 min when a T4 is free); this command waits until it is done...")
    for attempt in range(1, args.retries + 2):
        try:
            print(f"Attempt {attempt} at {time.strftime('%H:%M:%S', time.gmtime())} UTC")
            model.deploy(
                endpoint=endpoint,
                machine_type="n1-standard-8",
                accelerator_type="NVIDIA_TESLA_T4",
                accelerator_count=1,
                min_replica_count=1,
                max_replica_count=1,
                deployed_model_display_name="benjosh-socratic-tutor",
            )
            break
        except ServiceUnavailable as error:  # "Machine type temporarily unavailable": no free T4 in the region
            print(f"No capacity: {str(error)[:160]}")
            if attempt > args.retries:
                raise
            time.sleep(args.retry_wait)
    print(f"Deployed. Endpoint id: {endpoint.name}. Remember: python -m scripts.delete_endpoint --endpoint {endpoint.name}")


if __name__ == "__main__":
    main()
