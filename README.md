# Socratic Python Debugger

An AI tutor for beginner programmers. A student pastes buggy Python and says it does not work.
The tutor asks guiding questions so the student finds the bug, and never hands over the fix.

Course project for LLMOps (MSA-DATI09-04), Albert School x Mines Paris PSL.
Built on the course practice architecture: Kubeflow pipelines on Vertex AI, LoRA fine-tuning of
`microsoft/Phi-3-mini-4k-instruct`, a Vertex AI endpoint, a Chainlit app and Langfuse monitoring.

> Status: M0 (setup). Sections marked TODO are filled in as milestones are completed.

## Project structure

```
src/
  constants.py                  # configuration read from .env
  pipeline_components/          # Kubeflow components (data, fine-tuning, inference, evaluation)
  pipelines/                    # pipeline definitions
scripts/
  validate_gcp_setup.py         # checks Vertex AI and bucket access
  pipeline_runner.py            # compiles and submits the pipeline to Vertex AI
docs/
  learning-log.md               # what we built, why, and what went wrong
```

## Setup

### 1. Python environment

Install [uv](https://github.com/astral-sh/uv), then from the repo root:

```bash
uv sync
```

This creates `.venv/` with Python 3.11.6 and the exact package versions in `uv.lock`.

### 2. Google Cloud access

Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install), then:

```bash
gcloud auth login
gcloud auth application-default login
```

The project needs the Vertex AI, Cloud Storage and Cloud Resource Manager APIs enabled.

### 3. Environment variables

Copy the template and fill in your values:

```bash
cp .env.example .env
```

`.env` is git-ignored. `src/constants.py` loads it automatically.

### 4. Check the setup

```bash
uv run python -m scripts.validate_gcp_setup
```

Expected output ends with `All validations passed! GCP setup is ready.`

## Pipeline

TODO (M1 to M3)

## Evaluation and CI

TODO (M4)

## Serving and demo

TODO (M5)

## Monitoring

TODO (M7)

## Dataset and citation

We use the Socratic Debugging Benchmark (`v2_sigcse`):
https://github.com/taisazero/socratic-debugging-benchmark

The repository has no license file, so we treat it as academic research data and cite the authors:

- Erfan Al-Hossami, Razvan Bunescu, Ryan Teehan, Laurel Powell, Khyati Mahajan, Mohsen Dorodchi. 2023.
  *Socratic Questioning of Novice Debuggers: A Benchmark Dataset and Preliminary Evaluations.*
  Proceedings of the 18th Workshop on Innovative Use of NLP for Building Educational Applications (BEA 2023), pages 709 to 726.
  https://aclanthology.org/2023.bea-1.57
- Erfan Al-Hossami, Razvan Bunescu, Justin Smith, Ryan Teehan. 2024.
  *Can Language Models Employ the Socratic Method? Experiments with Code Debugging.*
  SIGCSE 2024, pages 53 to 59. https://doi.org/10.1145/3626252.3630799

## Acknowledgements

The starting code (Sessions 1 and 2) comes from the course practice solution by Mathieu Soul.
