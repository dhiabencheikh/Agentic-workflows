"""Timeline and outputs of a pipeline run's fine-tuning step, from Vertex AI and Cloud Logging.

Usage:
    uv run python -m scripts.pipeline_job_report --job <pipeline-job-id> --out docs/results/<file>.md

Phases (all from timestamps, nothing estimated):
  0 wait          pipeline step start -> "Waiting for job to be provisioned" (service log)
  1 provisioning  that line -> "Job is running" (service log: machine and GPU allocated)
  2a container    "Job is running" -> first line of our code (image, container start, pip install)
  2b model/data   our first line -> "Trainable parameters" (tokenizer, data, download, quantization, LoRA)
  3 training      "Trainable parameters" -> last training log; split into updates and validation
  4 final eval + save   last training log -> "Training done"
  5 teardown      "Training done" -> step end
"""

import argparse
import ast
import json
import re
from datetime import datetime

import google.auth
from google.auth.transport.requests import AuthorizedSession
from google.cloud import aiplatform, storage

from src.constants import BUCKET_NAME, PROJECT_ID, REGION


def log_entries(session: AuthorizedSession, custom_job_id: str) -> list:
    """All Cloud Logging entries of a Vertex custom job, oldest first."""
    entries, token = [], None
    while True:
        body = {
            "resourceNames": [f"projects/{PROJECT_ID}"],
            "filter": f'resource.type="ml_job" AND resource.labels.job_id="{custom_job_id}"',
            "orderBy": "timestamp asc",
            "pageSize": 1000,
        }
        if token:
            body["pageToken"] = token
        response = session.post("https://logging.googleapis.com/v2/entries:list", json=body)
        response.raise_for_status()
        data = response.json()
        entries += data.get("entries", [])
        token = data.get("nextPageToken")
        if not token:
            return entries


def text_of(entry: dict) -> str:
    if "textPayload" in entry:
        return entry["textPayload"]
    payload = entry.get("jsonPayload", {})
    return payload.get("message") or json.dumps(payload)


def ts(value) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def first(entries: list, pattern: str):
    return next((e for e in entries if re.search(pattern, text_of(e))), None)


def last(entries: list, pattern: str):
    return next((e for e in reversed(entries) if re.search(pattern, text_of(e))), None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", required=True, help="pipeline job id, e.g. model-training-pipeline-20261112163043")
    parser.add_argument("--out", required=True, help="markdown file to write")
    args = parser.parse_args()

    aiplatform.init(project=PROJECT_ID, location=REGION)
    job = aiplatform.PipelineJob.get(args.job)
    task = next(t for t in job.gca_resource.job_detail.task_details if t.task_name == "fine-tuning-component")
    custom_job_name = task.executor_detail.custom_job_detail.job
    if not custom_job_name:
        # Vertex does not always fill the link; every job of a run carries the run's billing label.
        billing_id = job.labels["vertex-ai-pipelines-run-billing-id"]
        candidates = aiplatform.CustomJob.list(filter=f'labels.vertex-ai-pipelines-run-billing-id="{billing_id}"')
        gpu_jobs = [c for c in candidates if c.gca_resource.job_spec.worker_pool_specs[0].machine_spec.accelerator_count]
        if len(gpu_jobs) != 1:
            raise RuntimeError(f"Expected 1 GPU job for run {args.job}, found {len(gpu_jobs)}")
        custom_job_name = gpu_jobs[0].resource_name
    custom_job = aiplatform.CustomJob.get(custom_job_name)
    cj = custom_job.gca_resource
    machine = cj.job_spec.worker_pool_specs[0].machine_spec

    credentials, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    entries = log_entries(AuthorizedSession(credentials), custom_job_name.rsplit("/", 1)[-1])
    # Lines printed inside the container carry the worker's task name; service lines do not.
    container = [e for e in entries if e.get("resource", {}).get("labels", {}).get("task_name") not in (None, "service")]

    marks = {
        "step_start": ts(task.start_time),
        "waiting_for_provisioning": first(entries, r"Waiting for job to be provisioned"),
        "job_running": first(entries, r"^Job is running"),
        "first_container_line": container[0] if container else None,
        "our_first_line": first(entries, r"GPU available:"),
        "trainable_parameters": first(entries, r"Trainable parameters:"),
        "last_training_log": last(entries, r"'train_runtime'|'loss':"),
        "training_done": first(entries, r"Training done:"),
        "step_end": ts(task.end_time),
    }
    times = {k: (v if isinstance(v, datetime) else ts(v["timestamp"]) if v else None) for k, v in marks.items()}

    def span(a: str, b: str):
        return (times[b] - times[a]).total_seconds() if times[a] and times[b] else None

    # Validation and per-update timing from the trainer's own log dicts.
    eval_runtimes, train_runtime, steps = [], None, None
    for entry in entries:
        text = text_of(entry)
        for match in re.finditer(r"\{[^{}]*'(?:eval_runtime|train_runtime)'[^{}]*\}", text):
            record = ast.literal_eval(match.group(0))
            if "eval_runtime" in record:
                eval_runtimes.append(record["eval_runtime"])
            if "train_runtime" in record:
                train_runtime = record["train_runtime"]

    info = None
    for name, arts in task.outputs.items():
        if name == "model" and arts.artifacts:
            blob = storage.Client(project=PROJECT_ID).bucket(BUCKET_NAME).blob(
                arts.artifacts[0].uri.replace(f"gs://{BUCKET_NAME}/", "") + "/training_info.json"
            )
            if blob.exists():
                info = json.loads(blob.download_as_text())
    # Number of validations: exact, from training_info.json (eval_history = during training + final).
    # Duration of one validation: mean of the eval_runtime values found in the logs (same 99 cards each time).
    n_evals_during, mean_eval, update_seconds, steps, final_eval = None, None, None, None, None
    if info:
        steps = info["global_steps"]
        n_evals_during = len(info["eval_history"]) - 1
        timings = info.get("timings_seconds")
        if timings:  # runs after the per-phase timing commit record this directly
            update_seconds = timings["seconds_per_update_excluding_validation"]
            mean_eval = timings["seconds_per_validation_run"]
            final_eval = timings["final_evaluation"]
    if mean_eval is None and eval_runtimes:
        mean_eval = sum(eval_runtimes) / len(eval_runtimes)
    if update_seconds is None and train_runtime and steps and mean_eval is not None:
        update_seconds = (train_runtime - n_evals_during * mean_eval) / steps

    def fmt(seconds) -> str:
        return "unknown" if seconds is None else f"{seconds:,.0f} s ({seconds / 60:.1f} min)"

    report = [
        f"# Pipeline run report: `{args.job}`",
        "",
        f"Generated by `scripts/pipeline_job_report.py` from Vertex AI and Cloud Logging. State: {job.state.name}.",
        f"Fine-tuning ran as custom job `{custom_job_name.rsplit('/', 1)[-1]}` on `{machine.machine_type}` "
        f"+ {machine.accelerator_count} x {machine.accelerator_type.name}; custom job state {cj.state.name}.",
        "",
        "## Timeline of the fine-tuning step (UTC)",
        "",
        "| Mark | Time |",
        "|---|---|",
        *[f"| {k} | {v.strftime('%H:%M:%S') if v else 'not found'} |" for k, v in times.items()],
        f"| custom job created | {ts(cj.create_time).strftime('%H:%M:%S')} |",
        f"| custom job start | {ts(cj.start_time).strftime('%H:%M:%S') if cj.start_time else 'unknown'} |",
        f"| custom job end | {ts(cj.end_time).strftime('%H:%M:%S') if cj.end_time else 'unknown'} |",
        "",
        "## Phases",
        "",
        "| Phase | Duration |",
        "|---|---|",
        f"| 0 wait (step start -> waiting for provisioning) | {fmt(span('step_start', 'waiting_for_provisioning'))} |",
        f"| 1 provisioning: machine + GPU allocated (-> 'Job is running') | {fmt(span('waiting_for_provisioning', 'job_running'))} |",
        f"| 2a container start, image, pip install (-> our first line) | {fmt(span('job_running', 'our_first_line'))} |",
        f"| 2b tokenizer, data, model download, quantization, LoRA (-> trainable parameters) "
        f"| {fmt(span('our_first_line', 'trainable_parameters'))} |",
        f"| 3 training incl. validation (-> last training log) | {fmt(span('trainable_parameters', 'last_training_log'))} |",
        f"| 4 final evaluation + save (-> training done) | {fmt(span('last_training_log', 'training_done'))} |",
        f"| 5 teardown (-> step end) | {fmt(span('training_done', 'step_end'))} |",
        f"| Whole step | {fmt(span('step_start', 'step_end'))} |",
        "",
        "## Inside training (trainer's own figures)",
        "",
        f"- Updates: {steps}; trainer `train_runtime`: {fmt(train_runtime)}",
        f"- Validation runs during training: {n_evals_during} (from training_info.json eval_history), "
        f"plus 1 final evaluation",
        f"- `eval_runtime` values found in the logs: {', '.join(f'{x:.1f} s' for x in eval_runtimes) or 'none'} "
        f"({len(eval_runtimes)} of {n_evals_during + 1 if n_evals_during is not None else '?'} validations logged); "
        f"mean used per validation: {mean_eval:.1f} s" if mean_eval else "- Validation time: unknown",
        f"- Seconds per update, validation excluded: {update_seconds:.1f} s" if update_seconds else "- Seconds per update: unknown",
        "",
    ]
    if info:
        keep = ("train_cards", "validation_cards", "cards_compressed", "cards_dropped", "global_steps",
                "best_eval_loss", "final_train_loss", "train_seconds", "seconds_per_step", "peak_gpu_memory_gb",
                "eval_history", "versions", "prompt_versions", "base_model_revision")
        report += ["## training_info.json (selected fields)", "", "```json",
                   json.dumps({k: info.get(k) for k in keep}, indent=2), "```", ""]
    nan_lines = [text_of(e)[:200] for e in entries if re.search(r"'loss': nan|'eval_loss': nan", text_of(e))]
    report += [f"Log lines with a NaN loss: {len(nan_lines)}", ""]
    errors = [text_of(e)[:300] for e in entries if e.get("severity") == "ERROR" and "Traceback" in text_of(e)]
    if errors:
        report += ["## Errors", "", *[f"- `{x}`" for x in errors[:5]], ""]

    with open(args.out, "w", encoding="utf-8") as file:
        file.write("\n".join(report))
    print("\n".join(report))


if __name__ == "__main__":
    main()
