"""Client for the deployed tutor endpoint (used by the Chainlit app).

Rule 1 of docs/m5-serving-rules.md: the client sends the conversation WITHOUT a system message;
the handler adds the tutor prompt server-side. Decoding is fixed server-side too (no parameters sent).
"""

import os
import time
from typing import Any

from src.constants import PROJECT_ID, REGION


def build_request(history: list) -> dict:
    """Vertex predict body for one conversation. Refuses a system message: the server adds the prompt."""
    if any(m["role"] == "system" for m in history):
        raise ValueError("the client must not send a system message: the handler adds the tutor prompt")
    return {"instances": [{"messages": [{"role": m["role"], "content": m["content"]} for m in history]}]}


def parse_prediction(predictions: list) -> dict:
    """The single prediction of a one-instance request, with an explicit error if it failed."""
    if len(predictions) != 1:
        raise ValueError(f"expected 1 prediction, got {len(predictions)}")
    prediction = dict(predictions[0])
    if prediction.get("error"):
        raise RuntimeError(f"endpoint error: {prediction['error']}")
    return prediction


class TutorEndpoint:
    """Calls the Vertex AI endpoint whose id is GCP_ENDPOINT_ID in .env."""

    def __init__(self, endpoint_id: str | None = None, region: str | None = None) -> None:
        """endpoint_id and region default to GCP_ENDPOINT_ID and GCP_REGION from .env."""
        from google.cloud import aiplatform

        aiplatform.init(project=PROJECT_ID, location=region or REGION)
        self.endpoint = aiplatform.Endpoint(endpoint_id or os.environ["GCP_ENDPOINT_ID"])

    def deployed_model_info(self) -> dict[str, Any]:
        """The model currently deployed on the endpoint (for trace metadata)."""
        deployed = self.endpoint.list_models()
        if not deployed:
            return {"endpoint_id": self.endpoint.name, "deployed_model": None}
        d = deployed[0]
        return {"endpoint_id": self.endpoint.name, "deployed_model_id": d.id, "deployed_model_name": d.display_name,
                "model_resource": d.model, "model_version_id": d.model_version_id}

    def reply(self, history: list) -> dict[str, Any]:
        request = build_request(history)
        start = time.time()
        response = self.endpoint.predict(instances=request["instances"])
        prediction = parse_prediction(response.predictions)
        prediction["round_trip_seconds"] = round(time.time() - start, 3)
        return prediction
