"""Undeploy every model from an endpoint and delete it: stops the hourly billing.

Run:
  uv run python -m scripts.delete_endpoint --endpoint <endpoint id>
"""

import argparse
from datetime import datetime, timezone

from google.cloud import aiplatform

from src.constants import PROJECT_ID, REGION


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    args = parser.parse_args()
    aiplatform.init(project=PROJECT_ID, location=REGION)
    endpoint = aiplatform.Endpoint(args.endpoint)
    endpoint.undeploy_all()
    endpoint.delete()
    print(f"Endpoint {args.endpoint} undeployed and deleted at {datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} UTC")


if __name__ == "__main__":
    main()
