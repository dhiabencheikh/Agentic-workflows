"""Model training pipeline definition for Vertex AI."""

from kfp.dsl import pipeline

from src.pipeline_components.data_transformation_component import (
    data_transformation_component,
)
from src.pipeline_components.fine_tuning_component import fine_tuning_component


@pipeline()
def model_training_pipeline(
    raw_dataset_uri: str,
    system_prompt: str,
    prompt_version: str,
    num_validation_problems: int,
    seed: int,
    base_model_id: str,
    base_model_revision: str,
    hyperparameters: dict,
    max_steps: int,
    max_train_cards: int,
) -> None:
    """Data transformation, then QLoRA fine-tuning on a T4 GPU."""
    data_task = data_transformation_component(
        raw_dataset_uri=raw_dataset_uri,
        system_prompt=system_prompt,
        prompt_version=prompt_version,
        num_validation_problems=num_validation_problems,
        seed=seed,
    )  # type: ignore

    fine_tuning_task = fine_tuning_component(
        train_dataset=data_task.outputs["train_dataset"],
        validation_dataset=data_task.outputs["validation_dataset"],
        base_model_id=base_model_id,
        base_model_revision=base_model_revision,
        hyperparameters=hyperparameters,
        use_quantization=True,
        max_steps=max_steps,
        max_train_cards=max_train_cards,
    )  # type: ignore
    fine_tuning_task.set_accelerator_type("NVIDIA_TESLA_T4")
    fine_tuning_task.set_accelerator_limit(1)
    fine_tuning_task.set_cpu_limit("16")
    fine_tuning_task.set_memory_limit("50G")
