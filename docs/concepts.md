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
| 8 | [SFT training example and chat template](#8-sft-training-example-and-chat-template) | M1 | Session 2 slides 16-19, 21, 24 |
| 9 | [One dialogue becomes many examples](#9-one-dialogue-becomes-many-examples) | M1 | NEW |
| 10 | [Data leakage and splitting by problem](#10-data-leakage-and-splitting-by-problem) | M1 | Practice 2 section 1.4, Session 3 |
| 11 | [Tokens and the context window](#11-tokens-and-the-context-window) | M1 | Session 2 slide 23 |
| 12 | [Kubeflow component, artifact, pipeline, job](#12-kubeflow-component-artifact-pipeline-job) | M1 | Session 2 slides 4-14, 25 |
| 13 | [Data cleaning: deduplication and attribution](#13-data-cleaning-deduplication-and-attribution) | M1 | Session 2 slide 22 |
| 14 | [Prompt versioning and prompt drift](#14-prompt-versioning-and-prompt-drift) | M1 (used in M3-M7) | Syllabus LO5, Session 1 slides 18, 20 |
| 15 | [Pinning the model revision](#15-pinning-the-model-revision) | M1 (used in M2-M5) | Session 1 slide 21 |
| 16 | [Overfitting and the validation set](#16-overfitting-and-the-validation-set) | M2 | Session 3 slide 4 |
| 17 | [QLoRA: quantization + LoRA](#17-qlora-quantization--lora) | M2 | Session 3 slides 6-11 |
| 18 | [Completion-only loss](#18-completion-only-loss) | M2 | NEW (Session 2 slide 19 states the idea) |
| 19 | [Training hyper-parameters and the GPU step](#19-training-hyper-parameters-and-the-gpu-step) | M2 | Session 3 slide 12, Practice 3 |
| 20 | [Context compression](#20-context-compression) | M2 (used in M3-M5) | Syllabus LO7 |

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

---

## 8. SFT training example and chat template

**In plain words.**
Fine-tuning is learning from worked examples: "in this situation, a good answer is this".
The model reads the situation and tries to predict the answer token by token; each wrong prediction gives a small correction to its weights.
Show it hundreds of examples of a tutor asking instead of telling, and it picks up the habit.

**How it works.**
- One example is a list of messages with a role (`system`, `user`, `assistant`) and text.
- The **chat template** turns that list into one string with the special markers the model was trained with. For Phi-3: `<|system|>...<|end|>`, `<|user|>...<|end|>`, `<|assistant|>...<|end|>`, then `<|endoftext|>`.
- At inference, `add_generation_prompt=True` ends the string with `<|assistant|>` so the model writes the next tutor turn.
- Our data step outputs messages (model-agnostic). The template is applied by the tokenizer in fine-tuning (model-specific).
- Checked on 2026-11-12 at revision `f39ac1d`: the Phi-3 template keeps the `<|system|>` block, so the system prompt reaches the model.

**In this course.** Session 2 slides 16-19 (base model, instruct model, SFT as "expected input-output pairs"), slide 21 (keep the original format and tokenizer), slide 24 (Phi-3 template). Practice 2 section 1.3.

**Seen before.** Generative AI I (next-token prediction, syllabus). Neural Networks (backpropagation: the "small correction"). Exact models and datasets used there: to confirm.

**In our repo.** `build_examples` in [data_transformation_component.py](../src/pipeline_components/data_transformation_component.py); template check in [01_explore_dataset.py](../notebooks/01_explore_dataset.py).

**Check yourself.** Why must the fine-tuning data use Phi-3's own markers rather than, say, "Student:" and "Tutor:"?
<details><summary>Answer</summary>
Phi-3-instruct was already trained to follow conversations written with its own markers. Other markers look like a different format, so we would partly re-teach the format instead of only the tutoring behaviour, and the served model (which receives Phi-3 markers) would see a format it was not fine-tuned on.
</details>

---

## 9. One dialogue becomes many examples

**In plain words.**
A conversation is cut into flashcards. Front: the conversation so far. Back: the tutor's next line.
In the app the model always faces the front of a card, so training and test cards look exactly like real use.

**How it works.**
- For each tutor turn: input = system prompt + (problem + buggy code + first student message) + all later turns before it; target = that tutor turn.
- Raw counts (`docs/results/m1_dataset_stats.md`): 815 tutor turns in `train/`, 92 in `testset/`. After deduplication: train 566, validation 99, test 80.
- Test cards are also the base of the M3 comparison and of M4 triples.

**In this course.** NEW: the Yoda practice was single-turn (one sentence in, one out).

**Seen before.** Building supervised samples from a sequence with a sliding window (e.g. time series forecasting): to confirm in which course.

**Check yourself.** Why not train on whole dialogues and test on whole dialogues?
<details><summary>Answer</summary>
The app produces one tutor message at a time from the conversation so far. Cards in that shape let us feed the same input to the base and fine-tuned models and compare one reply each, which a whole-dialogue format does not give directly.
</details>

---

## 10. Data leakage and splitting by problem

**In plain words.**
An exam built from last week's homework with names changed: memorising gets 100% without understanding.
If cards from the same conversation land in both train and test, the test score says nothing about a new student's new bug.

**How it works.**
- Hierarchy: problem > conversation files > cards. All cards of a problem go to one split.
- Test = the authors' `testset/` (4 problems). Validation = 4 of the 34 train problems, drawn with seed 42 (problems 1, 9, 18, 20).
- The component raises an error if a problem appears in two splits.
- Validation is for watching over-fitting during training (M2); test is touched only for the final comparison (M3).
- The teacher's `train_test_split(test_size=0.1)` splits by row: fine for independent Yoda sentences, leaky for dialogues.
- Limit to state at the oral: 4 test problems and 80 cards is small; differences of a few points can be chance.

**In this course.** Practice 2 section 1.4 (`train_test_split`). Validation and over-fitting: Session 3 (exact slide to cite in M2).

**Seen before.** Train/test splits and grouped splits (scikit-learn `GroupKFold`) in an earlier ML course; look-ahead bias in finance backtests. Which course: to confirm.

**In our repo.** End of [data_transformation_component.py](../src/pipeline_components/data_transformation_component.py); test `test_no_problem_is_shared_between_splits`.

**Check yourself.** A random 90/10 split by card gives a much better test score than the split by problem. Which number do you report, and why?
<details><summary>Answer</summary>
The split by problem. With a random split, cards of the same conversation are in train and test, so the model is tested on bugs and dialogues it has seen: the higher score measures memorisation, not generalisation to a new student's code.
</details>

---

## 11. Tokens and the context window

**In plain words.**
The model reads tokens (chunks of words mapped to numbers), not letters. Phi-3-mini-4k can look at 4,096 tokens at once.
Every card (prompt + problem + code + history + reply) must fit, or the start gets cut off.

**How it works.**
- Lengths must be measured with the model's own tokenizer and chat template; a word count is not enough.
- Measured on 2026-11-12 (prompt v1.0.0, revision `f39ac1d`): longest card 2,066 tokens, 0 cards over 4,096. The prompt alone is 120 tokens.
- Tutor replies are short: median 13 to 21 tokens depending on the split.
- If cards were too long, the fix would be trimming or summarising the middle of the history (LO7, context compression).

**In this course.** Session 2 slide 23 (tokenization, "use the same tokenizer as the base model"). Session 1 slide 12.

**Seen before.** Generative AI I (self-attention compares every token with every other, hence a fixed window). Neural Networks museum-guide project (embeddings start from tokens).

**Check yourself.** Why did we measure lengths before training rather than after a failed run?
<details><summary>Answer</summary>
Too-long cards are silently truncated by the trainer, cutting the problem statement or code. Measuring first (cheap, on a laptop) tells us whether trimming is needed before paying for GPU time.
</details>

---

## 12. Kubeflow component, artifact, pipeline, job

**In plain words.**
A pipeline is an assembly line. Each component is a workstation that takes inputs, does one job, and puts outputs in labelled boxes (artifacts) in the bucket.
Vertex AI runs each workstation on a rented machine and draws the line in the console.

**How it works.**
- `@component(base_image=..., packages_to_install=[...])` packages a function to run in a container; all imports must be inside the function.
- `OutputPath("Dataset")` declares an output file; Vertex picks its location under the pipeline root in the bucket.
- `@pipeline` wires components; `pipeline_runner.py` compiles to JSON and submits a `PipelineJob` with parameter values.
- `component.python_func` is the plain function behind a component: our tests and notebook call it locally, so they test the exact code Vertex runs.
- Our data component has 5 inputs (raw data URI, system prompt, prompt version, number of validation problems, seed) and 3 outputs (train, validation, test JSONL).
- Slide 25: keep model-agnostic steps (parsing, cleaning) apart from model-specific ones (template, tokens).

**In this course.** Session 2 slides 4-14 (Kubernetes, Kubeflow, component, artifact, pipeline, job, Vertex), slide 25. Practice 2 sections 2 and 3. Session 1 slides 15-16 (orchestration).

**Seen before.** Data Engineering pipelines as DAGs of steps (tool used there, e.g. Airflow: to confirm).

**Check yourself.** The component needs `re` and `fsspec`. Why are they imported inside the function and not at the top of the file?
<details><summary>Answer</summary>
Kubeflow ships only the function's source code to a fresh container. Imports at the top of the file are not part of that source, so the function would fail on Vertex with a NameError.
</details>

---

## 13. Data cleaning: deduplication and attribution

**In plain words.**
"A soup is only as good as its ingredients": look at the data. Two problems found by looking:
1. Some flashcards were printed several times (thread files repeat the dialogue's opening, sometimes with only formatting changes). Copies get extra weight in training and in the test score.
2. In 8 train files, a student's corrected function sat right after a tutor line. Our first parser gave it to the tutor, so 7 training targets taught the tutor to output corrected code: the exact behaviour we forbid.

**How it works.**
- Exact dedup removed 136 train-folder cards (815 to 679) and 9 testset cards (92 to 83).
- Normalised dedup compares all messages after ignoring spacing, backticks and end-of-word `, . ! ? ; :`. It keeps letter case, operators and in-word punctuation, because code is case-sensitive and `n - 1`, `n + 1`, `1.5`, `15` differ. It removed 14 more (679 to 665) and 3 more (83 to 80). Checked: no merged group differed in letter case.
- Fuzzy matching (similarity threshold) was rejected: at a 95% threshold it would remove 30 more cards than exact matching (measured before the attribution fix), including cards whose earlier conversation really differs, with an arbitrary threshold.
- Copies are always within one problem, hence within one split: dedup is about weighting, not leakage.
- Attribution fix: a `<code>` block after a tutor line goes to the next student turn. After the fix, 0 tutor targets contain a code block, and the longest validation target fell from 223 to 49 tokens.

**In this course.** Session 2 slide 22 (data cleaning, "look at your data"). Deduplication itself: NEW.

**Seen before.** pandas `drop_duplicates()`, SQL `SELECT DISTINCT` (Data Engineering: to confirm). This is the same idea with a looser definition of "same".

**In our repo.** `parse_dialogue`, `comparison_key`, `deduplicate` in [data_transformation_component.py](../src/pipeline_components/data_transformation_component.py); tests `test_code_block_after_a_tutor_line_goes_to_the_next_student_turn`, `test_near_copies_merge_only_on_formatting_differences`.

**Check yourself.** Why does lowercasing everything for dedup carry a risk on this dataset, even if it merged nothing extra here?
<details><summary>Answer</summary>
Python is case-sensitive: `Total` and `total` are different variables. Two cards differing only in such a name may describe different code, and merging them would delete a real example. We therefore keep case.
</details>

---

## 14. Prompt versioning and prompt drift

**In plain words.**
The system prompt is part of the product, like code. If it changes, the product changes, and old test results describe a product that no longer exists.
So it gets a version number, one file per version, and every result says which version it used.

**How it works.**
- Single source of truth: `prompts/tutor_system_v1.0.0.txt`, loaded by `src/prompts.py`. Vertex components receive it as a pipeline parameter; the handler gets the file copied next to it; local apps import it. A guard test fails if the text is pasted into code.
- Semantic versioning, MAJOR.MINOR.PATCH (as in `pandas 2.3.3`, concept 1):
  - MAJOR: promised behaviour changes (e.g. tutor may give fixes): rebuild data, retrain, re-evaluate.
  - MINOR: instruction added, old ones kept: rebuild data, retrain, re-evaluate.
  - PATCH: wording only: re-evaluate.
- Why a change invalidates past evaluation: a score measures model + prompt + generation settings + test cards together; LLMs are sensitive to wording; and here the prompt is inside every training card, so serving a different prompt creates a gap between training and serving.
- Every card stores `prompt_version`; scores are compared only within one version.
- The prompt's rules on asking for the answer, injection and off-topic have NO training examples: that behaviour comes only from the prompt and is tested explicitly in M4.

**In this course.** Syllabus topic "semantic-versioning conventions for prompts; how prompt drift invalidates prior evaluation results" and learning outcome 5. Session 1 slides 18 and 20 (experiment tracking and registry should also store prompts). Not in the practice guides: NEW in implementation.

**Seen before.** Version numbers of packages in `uv.lock` (concept 1). Semantic versioning in software: possibly MSA-DATI07-01, to confirm.

**In our repo.** [prompts/](../prompts/), [src/prompts.py](../src/prompts.py), [tests/test_prompts.py](../tests/test_prompts.py).

**Check yourself.** You fix a typo in the prompt (v1.0.1). Can you keep last week's evaluation score in your report as the current one?
<details><summary>Answer</summary>
No. The score was measured with v1.0.0. Even a wording change can change outputs, so the system must be re-evaluated with v1.0.1 and the report must state which version each score belongs to.
</details>

---

## 15. Pinning the model revision

**In plain words.**
`microsoft/Phi-3-mini-4k-instruct` is a name, not a fixed object: Microsoft can push new weights or a new chat template under the same name.
Pinning a revision is like citing a book's edition and page instead of just its title.

**How it works.**
- A Hugging Face repository is a Git repository; every change has a commit hash.
- We pin `BASE_MODEL_REVISION = f39ac1d...` (head of `main` on 2026-11-12, last modified 2025-12-10) in `src/constants.py`.
- `from_pretrained(BASE_MODEL_ID, revision=BASE_MODEL_REVISION)` must be used for both tokenizer and weights in every step: data checks, fine-tuning, inference, serving.

**In this course.** Session 1 slide 21 ("items that need to match between environments: code and data (model weights)..."). The pins `peft==0.13.2` and `transformers==4.46.*` follow the same logic for libraries.

**Seen before.** Lock files and package pins (concept 1); dataset provenance by commit (`3f77f89`, README).

**Check yourself.** The fine-tuning step loads Phi-3 without a revision, serving loads it with one. What can go wrong?
<details><summary>Answer</summary>
If `main` changed between the two, the LoRA adapter would be trained on one set of base weights (or template) and applied to another. The adapter's learned corrections assume the original weights, so quality can drop silently.
</details>

---

## 16. Overfitting and the validation set

**In plain words.**
A student who memorises last year's exam answers looks perfect on those questions and fails new ones.
Training loss always goes down; the question is whether the loss on cards the model never trains on (validation loss) also goes down. When it stops falling and rises, the model is memorising: stop there.

**How it works.**
- Every 10 updates, the trainer computes the loss on the 99 validation cards (problems 1, 9, 18, 20, never trained on).
- `load_best_model_at_end=True` with `metric_for_best_model="eval_loss"`: the saved adapter is the checkpoint with the lowest validation loss, not the last one.
- Both curves go to TensorBoard (`report_to=["tensorboard"]`, `logging_dir` = the component's metrics path).
- **A low validation loss does not prove Socratic behaviour.** Loss measures how well the model predicts the human tutor's exact words. A model can score a good loss and still leak a fix on some cards, or ask a question that is fluent but useless. That is why M3 measures behaviour directly: leak checks, similarity to the best reference, and an LLM judge of Socratic quality.

**In this course.** Session 3 slide 4: "you need to be sure your model is fitting, but not over-fitting! For this you need a validation dataset, and regular evaluation along the epochs that can be visualized. Remember to log key hyper-parameters". Practice 3 section 1 steps 2, 3, 6.

**Seen before.** Neural Networks: training and validation curves, early stopping (details to confirm).

**Check yourself.** The fine-tuned model has a lower validation loss than the base model. Can you claim it is a better Socratic tutor?
<details><summary>Answer</summary>
No. Validation loss only says it predicts the human tutors' words better. Being a good Socratic tutor means not leaking fixes and asking useful questions, which must be measured on generated replies (M3), and the base model with the system prompt must be compared on the same cards.
</details>

---

## 17. QLoRA: quantization + LoRA

**In plain words.**
Two tricks combined so a 3.8-billion-parameter model can be fine-tuned on one T4 GPU (16 GB):
1. **Quantization:** store the frozen model in 4 bits per number, like a compressed JPEG instead of a raw photo: much smaller, nearly the same.
2. **LoRA:** do not retrain the textbook; add thin sticky notes to some pages and train only the notes.

**How it works.**
- Quantization: `BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float16)`. NF4 is a 4-bit format suited to weights that follow a bell curve; double quantization also compresses the scaling constants. Calculations run in fp16 because **T4 GPUs have no native bf16** (the article used float32).
- `prepare_model_for_kbit_training(model)`: before adding LoRA to a quantized model, it (1) freezes all base weights, (2) casts the few small non-quantized layers, such as layer norms, to float32 for numerical stability (the article measured the footprint going from 2206 MB to 2651 MB because of this), and (3) enables gradient checkpointing, which recomputes activations during the backward pass instead of storing them, saving memory at the cost of time.
- LoRA: for a frozen weight W (d_out x d_in), learn B (d_out x r) and A (r x d_in). The layer uses **W' = W + (alpha / r) x BA**: alpha / r scales the update. With r = 8 and alpha = 16 the scale is 2.0 (measured: `scaling alpha/r = 2.0` in `docs/results/m2_finetuning_prep.md`).
- Example measured on Phi-3 layer 0 `qkv_proj`: W is (9216, 3072) = 28,311,552 numbers; A is (8, 3072) and B is (9216, 8) = 98,304 numbers.
- Our config: r = 8, alpha = 16, dropout 0.05, targets `o_proj, qkv_proj, gate_up_proj, down_proj` (attention and feed-forward projections). Measured: **12,582,912 trainable parameters of 3,833,662,464 (0.33%)**.
- Output: only the adapter (A and B for every targeted layer) plus a config, saved next to the tokenizer and `training_info.json`.
- B starts at zero, so at step 0 the model is exactly the base model.

**In this course.** Session 3 slide 6 (quantization trade-off), slides 7-10 (backpropagation cost, intrinsic rank "d*d > 2*d*r", W' = W + BA, merge at inference), slide 11 (rank, target modules, alpha, task type). Practice 3 section 1 step 4.

**Seen before.** Neural Networks: backpropagation, fine-tuning. LoRA and quantization themselves: likely NEW (to confirm).

**In our repo.** [fine_tuning_component.py](../src/pipeline_components/fine_tuning_component.py), hyper-parameters in [constants.py](../src/constants.py), counts in [m2_finetuning_prep.md](results/m2_finetuning_prep.md).

**Check yourself.** You double r from 8 to 16 and keep alpha = 16. What happens to the number of trainable parameters and to the scale of the update?
<details><summary>Answer</summary>
Trainable parameters double (each A and B gets twice as many rows or columns). The scale alpha / r halves from 2.0 to 1.0, so each unit of BA counts half as much; this is why people often keep alpha = 2r when changing r.
</details>

---

## 18. Completion-only loss

**In plain words.**
Each card is long and its answer is short. If the model is graded on every token, almost all its effort goes into predicting problem statements and student messages, and it partly learns to talk like a confused student. We grade only the tutor's final reply.

**How it works.**
- Each token has a label = the token the model should predict there. Context tokens get label -100, which means "do not grade".
- TRL 0.12.2 `DataCollatorForCompletionOnlyLM(response_template="<|assistant|>")` masks every label up to the **last** `<|assistant|>` marker, so only the final tutor reply and its `<|end|>` are graded. It cannot be combined with packing.
- Measured on the real data: **665 of 665** train and validation cards grade exactly the final reply plus `<|end|>`; median share of graded tokens **2.5%** (min 0.2%, max 19.1%). Without masking, 100% of tokens would be graded.
- Grading `<|end|>` teaches the model to stop: `<|end|>` (id 32007) is one of Phi-3's stop tokens in its `generation_config.json`.
- Padding uses `<unk>`: Phi-3's default pad token is `<|endoftext|>`, the same as its end-of-text token, and padded positions are not graded.
- The validation loss is computed the same way, so it also measures only tutor replies.
- The course article does not mask: it shows labels "exactly the same as the inputs". Fine for one-sentence Yoda prompts, wrong for our long cards.

**In this course.** NEW in implementation. Session 2 slide 19 states the principle: SFT trains "only on the output tokens".

**Seen before.** Masked losses in sequence models (Neural Networks or Generative AI I, to confirm).

**Check yourself.** Why does the collator mask up to the LAST `<|assistant|>` and not the first?
<details><summary>Answer</summary>
A card contains earlier tutor turns as context. Masking only up to the first marker would also grade those earlier replies, which already appear as targets of their own cards, so they would be learned several times; the card's own target is the final reply.
</details>

---

## 19. Training hyper-parameters and the GPU step

**In plain words.**
Learning rate is the size of each correction, batch size is how many cards are graded before each correction, epochs is how many times the model sees the training set. Too big or too many and the model memorises or becomes unstable; too small and it barely changes.

**How it works.**
- One dictionary, `FINE_TUNING_HYPERPARAMETERS` in `constants.py`, passed to the component, logged to Vertex as metrics and saved in `training_info.json`.
- Starting values: learning rate 3e-4 (article), 3 epochs (article: 10, on shorter data), batch 2 per device x 8 accumulation steps = 16 cards per update, `max_seq_length` 2304 (above the longest card, 2066 tokens), validation every 10 updates.
- **Trap found in TRL 0.12.2**: if `max_seq_length` is not set, it defaults to `min(model_max_length, 1024)` and cuts the END of longer cards, which is exactly the reply we want to teach. 55 train cards are over 1024 tokens.
- GPU step: `set_accelerator_type("NVIDIA_TESLA_T4")`, `set_cpu_limit("16")`, `set_memory_limit("50G")`, image `pytorch/pytorch:2.8.0-cuda12.9-cudnn9-devel`. Optimizer `paged_adamw_8bit`, fp16 mixed precision.
- Caching: Vertex reuses the data step output when its inputs are unchanged (`enable_caching=True`).
- Smoke run before the full run: 20 updates on the 40 longest cards (worst case for memory) to check that it fits and to measure seconds per update. The full run cost is then measured time x the official hourly price.

**In this course.** Session 3 slide 12 (learning rate, batch size, epochs). Practice 3 section 1 ("Adding it to the pipeline", "Checking the results"). Session 2 slide 25 (caching).

**Seen before.** Neural Networks: learning rate, batch size, epochs.

**Check yourself.** Why are the smoke run's cards the LONGEST ones rather than a random sample?
<details><summary>Answer</summary>
GPU memory grows with sequence length. If the longest cards fit, every card fits; the measured seconds per update is also an upper bound, so the cost estimate for the full run is conservative.
</details>

---

## 20. Context compression

**In plain words.**
A card or a live conversation can outgrow the model's window. Cutting the start would remove the instructions, the problem and the code; cutting the end would remove the question being answered. We remove the oldest middle exchanges instead, like skipping the middle pages of a meeting's minutes while keeping the agenda and the latest decisions.

**How it works.**
- `fit_to_length` in the fine-tuning component: while the rendered card is longer than `max_seq_length`, delete the oldest tutor + student pair after the first student message (so roles keep alternating). Keeps: system prompt, problem + buggy code, recent turns, target.
- If even system + first message + last student turn + target do not fit, the card is dropped and counted.
- At 2304 tokens, no training or validation card needs it (measured). It is a safety net now and will matter in M3 and M5, where live conversations can grow.
- A more advanced version replaces the removed middle with a short summary (LO7 "context compression via summarisation"), at the cost of an extra model call.

**In this course.** Syllabus learning outcome 7 (context compression). Not in the practice: NEW.

**Seen before.** Generative AI I: RAG and context windows (to confirm).

**In our repo.** `fit_to_length` in [fine_tuning_component.py](../src/pipeline_components/fine_tuning_component.py); tests `test_long_cards_are_compressed_in_the_middle_never_at_the_ends`, `test_a_card_that_cannot_fit_even_compressed_is_dropped_and_counted`.

**Check yourself.** Why does the compression delete messages in pairs?
<details><summary>Answer</summary>
Chat templates expect user and assistant turns to alternate. Deleting one message would put two student or two tutor messages in a row, a format the model never saw in training.
</details>
