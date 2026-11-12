"""Model training pipeline definition for Vertex AI."""

from kfp.dsl import pipeline

from src.pipeline_components.data_transformation_component import (
    data_transformation_component,
)


@pipeline()
def model_training_pipeline(
    raw_dataset_uri: str,
    system_prompt: str,
    prompt_version: str,
    num_validation_problems: int,
    seed: int,
) -> None:
    """Model training pipeline definition."""
    data_transformation_component(
        raw_dataset_uri=raw_dataset_uri,
        system_prompt=system_prompt,
        prompt_version=prompt_version,
        num_validation_problems=num_validation_problems,
        seed=seed,
    )  # type: ignore
