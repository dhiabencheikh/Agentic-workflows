"""M3 evaluation pipeline: tutor replies for setups a, b, c on the same test cases.

Existing artifacts are brought in by URI with Kubeflow's importer (nothing is retrained).
The three setups run one after the other, so only one T4 is needed at a time from the
class's shared quota.
"""

from kfp import dsl
from kfp.dsl import Dataset, Model, pipeline

from src.constants import EVAL_PIPELINE_NAME, GPU_TASK_CPU_LIMIT, GPU_TASK_MEMORY_LIMIT
from src.pipeline_components.inference_component import inference_component


@pipeline(name=EVAL_PIPELINE_NAME)
def evaluation_pipeline(
    test_dataset_uri: str,
    adapter_uri: str,
    base_model_id: str,
    base_model_revision: str,
    system_prompt: str,
    prompt_version: str,
    generation: dict,
    extra_cases_uri: str,
    max_cases: int,
) -> None:
    """Setups a (base, no prompt), b (base + prompt), c (base + adapter + prompt), in sequence."""
    cards = dsl.importer(artifact_uri=test_dataset_uri, artifact_class=Dataset).set_display_name("import-test-cards")
    adapter = dsl.importer(artifact_uri=adapter_uri, artifact_class=Model).set_display_name("import-adapter")

    common = dict(
        test_dataset=cards.output,
        base_model_id=base_model_id,
        base_model_revision=base_model_revision,
        system_prompt=system_prompt,
        prompt_version=prompt_version,
        generation=generation,
        extra_cases_uri=extra_cases_uri,
        max_cases=max_cases,
    )
    previous = None
    for setup in ("a", "b", "c"):
        extra = {"adapter": adapter.output} if setup == "c" else {}
        task = inference_component(setup=setup, **common, **extra)  # type: ignore
        task.set_display_name(f"inference-setup-{setup}")
        task.set_accelerator_type("NVIDIA_TESLA_T4")
        task.set_accelerator_limit(1)
        task.set_cpu_limit(GPU_TASK_CPU_LIMIT)
        task.set_memory_limit(GPU_TASK_MEMORY_LIMIT)
        if previous is not None:
            task.after(previous)
        previous = task
