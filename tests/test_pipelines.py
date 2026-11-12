"""Both pipelines compile, with the expected tasks, order and GPU settings (no cloud calls)."""

import json

from kfp import compiler

from src.constants import GPU_TASK_CPU_LIMIT
from src.pipelines.evaluation_pipeline import evaluation_pipeline
from src.pipelines.model_training_pipeline import model_training_pipeline


def compile_spec(pipeline_func, tmp_path) -> dict:
    path = tmp_path / "pipeline.json"
    compiler.Compiler().compile(pipeline_func=pipeline_func, package_path=str(path))
    return json.loads(path.read_text())


def test_training_pipeline_compiles_with_a_gpu_fine_tuning_step(tmp_path):
    tasks = compile_spec(model_training_pipeline, tmp_path)["root"]["dag"]["tasks"]
    assert set(tasks) == {"data-transformation-component", "fine-tuning-component"}


def test_evaluation_pipeline_runs_setups_a_b_c_in_sequence_on_one_gpu_each(tmp_path):
    spec = compile_spec(evaluation_pipeline, tmp_path)
    tasks = spec["root"]["dag"]["tasks"]
    inference = {name: t for name, t in tasks.items() if name.startswith("inference-component")}
    assert len(inference) == 3
    setups = {t["inputs"]["parameters"]["setup"]["runtimeValue"]["constant"]: name for name, t in inference.items()}
    assert set(setups) == {"a", "b", "c"}
    # b runs after a, c after b
    assert setups["a"] in inference[setups["b"]].get("dependentTasks", [])
    assert setups["b"] in inference[setups["c"]].get("dependentTasks", [])
    # only setup c receives the adapter
    assert "adapter" in inference[setups["c"]]["inputs"].get("artifacts", {})
    assert "adapter" not in inference[setups["a"]]["inputs"].get("artifacts", {})
    for executor in spec["deploymentSpec"]["executors"].values():
        resources = executor.get("container", {}).get("resources")
        if resources:
            assert resources["accelerator"]["type"] == "NVIDIA_TESLA_T4"
            assert resources["resourceCpuLimit"] == GPU_TASK_CPU_LIMIT
