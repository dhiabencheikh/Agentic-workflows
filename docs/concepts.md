# Concepts revision sheet

Every concept we used in the project, explained so it can be reread before the oral and the written exam.
Organised by concept, not by date. The day-by-day story is in [learning-log.md](learning-log.md).

Each entry has the same parts:
- **In plain words:** the idea without jargon
- **How it works:** the technical layer
- **In this course:** where the LLMOps course covers it
- **Seen before:** where it appeared in other courses (marked "to confirm" when we do not know the details)
- **In our repo:** where to find it in the code
- **Check yourself:** an exam-style question, with the answer hidden below it

## Index

| # | Concept | Milestone | Course anchor |
|---|---|---|---|
| 1 | [Virtual environment, uv and the lock file](#1-virtual-environment-uv-and-the-lock-file) | M0 | Session 1 slides 21-22, Practice 1 section 1 |
| 2 | [Environment variables and `.env`](#2-environment-variables-and-env) | M0 | Session 1 slide 23, Practice 1 section 3 |
| 3 | [Cloud authentication: two logins, IAM, gcloud configurations](#3-cloud-authentication-two-logins-iam-gcloud-configurations) | M0 | Session 1 slides 27-28, Practice 1 section 3 |
| 4 | [Cloud Storage bucket](#4-cloud-storage-bucket) | M0 | Practice 1 section 2 |
| 5 | [Smoke test (setup validation)](#5-smoke-test-setup-validation) | M0 | Session 1 slide 27, Practice 1 section 3 |
| 6 | [Git branches and small commits](#6-git-branches-and-small-commits) | M0 | Session 1 slide 22 |
| 7 | [GPU quota](#7-gpu-quota) | M0 (used in M2) | Session 1 slide 28 |

---

## 1. Virtual environment, uv and the lock file

**In plain words.**
Every project needs libraries (pandas, kfp...). If all projects share one pile of libraries, two things go wrong:
project A needs pandas 1.5 while project B needs 2.3, and your teammate's machine has slightly different versions than yours.
A virtual environment is a private toolbox per project. uv is the tool that builds it.

**How it works.**
- `.venv/` is a folder with its own Python interpreter and its own installed libraries, isolated from the rest of the Mac.
- `pyproject.toml` is the shopping list: what we need, with minimum versions (`pandas>=2.3.3`).
- `uv.lock` is the receipt: the exact version of every package actually installed, including sub-dependencies.
- `uv sync` rebuilds `.venv/` from the receipt, so everyone gets an identical toolbox. `uv add X` adds to the list and updates the receipt.
- `.python-version` pins Python itself (3.11.6).
- Both `pyproject.toml` and `uv.lock` are committed. `.venv/` is not (it is rebuilt, and it is large: 409 MB on Dhia's Mac on 2026-11-10).

**In this course.**
- Session 1 slide 21, "Deployment, the problem": "But it works on my machine!" and the list of things that must match between environments (Python dependencies, credentials, GPU drivers...).
- Session 1 slide 22: Git and virtual environments, "we'll use uv".
- Practice 1 section 1: `uv init`, `uv add`, `uv sync`.
- Comes back bigger in Session 4: a Docker container is a toolbox that also includes the operating system (Session 1 slide 24 introduces it). The pins `peft==0.13.2` and `transformers==4.46.*` exist because the Vertex serving image has fixed versions.

**Seen before.**
MSA-DATI07-01 (syllabus prerequisite): "a Python project with version control, a requirements file, and a README". A `requirements.txt` is the older form of the shopping list, often without a receipt. Tool used there (pip, conda, Poetry): to confirm.

**In our repo.** [pyproject.toml](../pyproject.toml), [uv.lock](../uv.lock), [.python-version](../.python-version)

**Check yourself.** Why commit `uv.lock` if `pyproject.toml` already lists the dependencies?
<details><summary>Answer</summary>
`pyproject.toml` gives ranges (">= 2.3.3"), so two installs a month apart can get different versions. `uv.lock` fixes the exact version of every package, including indirect ones, so every machine (teammate, CI, cloud) reproduces the same environment.
</details>

---

## 2. Environment variables and `.env`

**In plain words.**
Some values must not be written in the code: secrets (an API key on a public GitHub repo gets scraped by bots and used) and per-person settings (project ID, bucket).
We keep them in a local file, `.env`, that Git ignores, and commit a template, `.env.example`, with fake values so a teammate knows what to fill in.

**How it works.**
- An environment variable is a named value the operating system hands to every program it starts. Python reads it with `os.getenv("GCP_PROJECT_ID")`.
- `.env` is only a text file. Something must read it and turn its lines into environment variables.
  We use the `python-dotenv` library: `load_dotenv()` in `src/constants.py` runs whenever the project code is imported.
- If a variable is already set in the shell, `load_dotenv` does not overwrite it. This matters in CI (M4): GitHub Actions injects secrets as variables and there is no `.env` file.
- Alternative we did not choose: `uv run --env-file .env ...` (no extra library, but every command needs the flag).

**In this course.**
- Session 1 slide 23: "store configuration, credentials or secrets outside of your code tracked by Git... Do not track it with Git! Instead, you can use a .env.example file".
- Practice 1 section 3: `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_BUCKET_NAME` read with `os.getenv()`.
- Session 5 (data exposure, security) is the "why": a leaked key is a security incident.

**Seen before.**
MSA-DATI07-03 (calling a REST API from Python) uses API keys, which raises the same problem. Whether `.env` was used there: to confirm.

**In our repo.** [src/constants.py](../src/constants.py), [.env.example](../.env.example), `.gitignore` line `.env`

**Check yourself.** A teammate clones the repo and the validation script fails with a bucket named `None`. What is the most likely cause?
<details><summary>Answer</summary>
They have no `.env` file (it is not in Git). `os.getenv("GCP_BUCKET_NAME")` returns `None`. Fix: `cp .env.example .env` and fill in the values.
</details>

---

## 3. Cloud authentication: two logins, IAM, gcloud configurations

**In plain words.**
Google must know who is asking before letting anyone read the bucket or start a GPU. There are two separate badges:
one for you typing commands, one for your Python programs.

**How it works.**
- `gcloud auth login`: credentials for the `gcloud` command line tool.
- `gcloud auth application-default login`: Application Default Credentials (ADC), a file on your Mac that Google's Python libraries find automatically. No key in the code.
- `gcloud auth application-default set-quota-project <id>`: tells Google which project to bill API usage to.
- IAM (Identity and Access Management): the roles saying what each account may do in a project.
- gcloud configurations are saved profiles (account + project). We created `llmops` so the Data Engineering profile (`default`, project `data-engineering-i1`) stays untouched.
  Switch with `gcloud config configurations activate <name>`.

**In this course.**
- Practice 1 section 3: both login commands, `gcloud config set project`.
- Session 1 slide 27: IAM roles and permissions, named as important but not covered in depth.
- Session 1 slide 28: why the cloud at all (GPUs, pay for use, managed services).

**Seen before.**
Data Engineering: Dhia already had gcloud configured on project `data-engineering-i1`, so GCP login was used there. The exact services used: to confirm.

**In our repo.** No file: credentials live outside the repo, by design.

**Check yourself.** The `gcloud storage ls` command works, but a Python script gets "default credentials not found". Why?
<details><summary>Answer</summary>
Only `gcloud auth login` was done. Python libraries use Application Default Credentials, which need `gcloud auth application-default login`.
</details>

---

## 4. Cloud Storage bucket

**In plain words.**
A bucket is a cloud hard drive for files. Our laptop and the Vertex AI machines do not share a disk, so the bucket is where they meet:
datasets go in, and every pipeline step writes its outputs (cleaned data, LoRA weights, scores) there.

**How it works.**
- Addresses look like `gs://benjosh-llmops/path/file.jsonl`.
- Names are global across all Google customers, lowercase only, and cannot be renamed. That is why `BenJosh-llmops` became `benjosh-llmops`.
- Location `EU` multi-region: copies kept in several EU data centres (availability, data stays in the EU, relevant to GDPR in Session 5).
- Uniform bucket-level access: permissions are set once for the whole bucket through IAM, not per file. Simpler and recommended by Google.
- Cost: you pay for stored data and operations. Our exact cost will be measured, not assumed.

**In this course.**
- Practice 1 section 2: create a bucket named `team_name-llmops`, multi-regional EU.
- Session 2: Vertex pipelines use the bucket as `pipeline_root`, where every component's artifacts are stored (`PIPELINE_ROOT_PATH` in `src/constants.py`).

**Seen before.**
Data Engineering (pipelines, storage, BigQuery/GCS per CLAUDE.md section 5). Details of the exercises: to confirm.

**In our repo.** Bucket name in `.env` (`GCP_BUCKET_NAME`), used in [src/constants.py](../src/constants.py).
Created with: `gcloud storage buckets create gs://benjosh-llmops --project=agentics-workflows-510809 --location=EU --uniform-bucket-level-access`

**Check yourself.** Why can the fine-tuning component not simply read the dataset from `~/Desktop` on Dhia's Mac?
<details><summary>Answer</summary>
The component runs on a Google machine in a data centre, which has no access to the laptop's disk. Inputs and outputs must be in shared storage both can reach: the GCS bucket.
</details>

---

## 5. Smoke test (setup validation)

**In plain words.**
An electrician flips the switch once before testing anything else. If it smokes, nothing else is worth testing.
Our validation script checks the two things everything else depends on: can Python reach Vertex AI, and can it open our bucket.

**How it works.**
- [scripts/validate_gcp_setup.py](../scripts/validate_gcp_setup.py) calls `aiplatform.init(...)` and `storage.Client(...).bucket(name).reload()`.
- Each check is wrapped in `try/except` and prints a check mark or a cross.
- Run with `uv run python -m scripts.validate_gcp_setup`. `-m` runs it as a module from the repo root, so `from src.constants import ...` works.
- Limit: `aiplatform.init` mostly stores settings, so the Vertex check is weaker than the bucket check, which really calls Google.

**In this course.**
- Practice 1 section 3 (writing this script).
- Session 1 slide 27: "Testing (unit, integration)" and "CI/CD" as components to be aware of.
- Our M4 eval harness is the full version: 100 automatic checks run on every push, failing the build on a regression.

**Seen before.**
MSA-DAT09-01 (MLOps) covered packaging a model as a REST API, which usually includes a health check endpoint: the same idea. To confirm.

**Check yourself.** What is the difference between a smoke test and the eval harness of M4?
<details><summary>Answer</summary>
The smoke test checks that the infrastructure is reachable (yes/no, seconds, no model involved). The eval harness checks the model's behaviour on 100 cases against quality thresholds and blocks a release if it gets worse.
</details>

---

## 6. Git branches and small commits

**In plain words.**
Git is a history of the project. A branch is a parallel draft: we work on `m0-setup` without touching `main`, then merge when the step is done and checked.
Small commits, one idea each, make the history readable (and it is graded).

**How it works.**
- `git switch -c m0-setup` creates and moves to the branch.
- We imported the teacher's code in its own commit, then adapted it in the next one, so `git diff` shows exactly what we changed.
- Nothing is pushed to GitHub without Dhia's confirmation.

**In this course.** Session 1 slide 22 (Git as the industry standard), Practice 1 section 1.

**Seen before.** MSA-DATI07-01 (version control). Branch workflow used there: to confirm.

**Check yourself.** Why commit the teacher's code unchanged before adapting it?
<details><summary>Answer</summary>
So the history separates borrowed code from our own work: the second commit's diff is exactly our contribution, which is honest and easy to defend.
</details>

---

## 7. GPU quota

**In plain words.**
A quota is a ceiling Google puts on each project: "you may use at most N T4 GPUs at once in this region". New projects often start at 0.
It is not about where data is stored (that is the bucket location). It is about where the training machines may run.

**How it works.**
- Quotas are per region: you can have 1 T4 allowed in `europe-west4` and 0 in `europe-west2`.
- Vertex AI training uses its own quota, named "Custom model training Nvidia T4 GPUs per region". Serving an endpoint (M5) uses a separate one.
- If a pipeline asks for a T4 in a region where the quota is 0, the job fails at launch with a quota error.
- `GCP_REGION` in `.env` must be a region where the quota is above 0. Status on 2026-11-10: Dhia confirmed our T4 quota is in `europe-west2`, which is our `GCP_REGION`.
- To check: Console, IAM & Admin, Quotas & System Limits, filter by that name, look at the "Value" column per region.

**In this course.** Session 1 slide 28 (cloud gives access to GPUs). The GPU task settings (`set_accelerator_type("NVIDIA_TESLA_T4")`) come in Practice 3.

**Seen before.** Neural Networks course: training on GPUs (environment used there, e.g. Colab: to confirm).

**Check yourself.** The bucket is in `EU`. Does that mean training can run in any EU region?
<details><summary>Answer</summary>
No. The bucket location is about storage. Training runs where the GPU quota exists and where `GCP_REGION` points. An EU multi-region bucket can be read from any EU region.
</details>
