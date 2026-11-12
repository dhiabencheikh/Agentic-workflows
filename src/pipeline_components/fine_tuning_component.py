"""Fine-tuning component for Vertex AI pipeline: QLoRA on Phi-3 (Session 3).

The base model is loaded in 4-bit (quantization) and frozen; only small LoRA
matrices are trained. Only the final tutor reply of each card is graded
(completion-only loss). The best checkpoint by validation loss is saved.
"""

from kfp.dsl import Dataset, Input, Metrics, Model, Output, component


@component(
    base_image="pytorch/pytorch:2.8.0-cuda12.9-cudnn9-devel",
    packages_to_install=[
        "transformers==4.46.3",
        "peft==0.13.2",
        "trl==0.12.2",
        "accelerate==1.15.0",
        "datasets==4.2.0",
        "bitsandbytes==0.47.0",
        "tensorboard==2.20.0",
    ],
)
def fine_tuning_component(
    train_dataset: Input[Dataset],
    validation_dataset: Input[Dataset],
    base_model_id: str,
    base_model_revision: str,
    hyperparameters: dict,
    use_quantization: bool,
    max_steps: int,
    max_train_cards: int,
    model: Output[Model],
    metrics: Output[Metrics],
) -> None:
    """Fine-tune the base model with LoRA and save the adapter.

    Args:
        train_dataset, validation_dataset: JSONL cards from the data component.
        base_model_id, base_model_revision: pinned Hugging Face model (a local
            folder also works, for tests; the revision is then ignored).
        hyperparameters: the FINE_TUNING_HYPERPARAMETERS dict from constants.py.
        use_quantization: True on GPU (4-bit QLoRA). False for CPU tests.
        max_steps: -1 for a full run; a small number for a smoke run.
        max_train_cards: 0 for all cards; N keeps the N LONGEST cards (smoke
            run: tests the worst case for GPU memory).
        model: output folder with the LoRA adapter, tokenizer, training_info.json.
        metrics: Kubeflow metrics; TensorBoard logs are written under its path.
    """
    import json
    import logging
    import os
    import tempfile
    import time

    import peft
    import torch
    import transformers
    import trl
    from datasets import Dataset as HFDataset
    from peft import LoraConfig, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
    from trl import DataCollatorForCompletionOnlyLM, SFTConfig, SFTTrainer

    function_start = time.time()  # after pip install: Kubeflow installs packages before calling us
    marks = {}  # phase name -> seconds since function_start

    def mark(name: str) -> None:
        marks[name] = round(time.time() - function_start, 1)

    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)
    hp = hyperparameters
    on_gpu = torch.cuda.is_available()
    is_local_model = os.path.isdir(base_model_id)
    revision = None if is_local_model else base_model_revision
    logger.info(f"GPU available: {on_gpu}, quantization: {use_quantization}, hyper-parameters: {hp}")

    # Tokenizer. Padding uses <unk> so that no real token (e.g. <|endoftext|>,
    # which is also the default pad token of Phi-3) is ever masked by padding.
    tokenizer = AutoTokenizer.from_pretrained(base_model_id, revision=revision)
    tokenizer.pad_token = tokenizer.unk_token
    tokenizer.pad_token_id = tokenizer.unk_token_id
    max_len = hp["max_seq_length"]

    def n_tokens(messages: list) -> int:
        return len(tokenizer.apply_chat_template(messages, tokenize=True))

    def fit_to_length(messages: list) -> list | None:
        """Context compression (LO7): never cut the start or the end of a card.

        Keeps system prompt, first student message (problem + buggy code) and the
        most recent turns; drops the oldest middle exchanges (tutor + student
        pair, so roles keep alternating) until the card fits. Returns None if
        even the shortest version does not fit.
        """
        messages = list(messages)
        while n_tokens(messages) > max_len:
            if len(messages) <= 4:  # system, first user, last user, target
                return None
            del messages[2:4]
        return messages

    def load_cards(path: str, limit: int = 0) -> tuple:
        with open(path, encoding="utf-8") as file:
            cards = [json.loads(line) for line in file]
        if limit:
            cards = sorted(cards, key=lambda c: n_tokens(c["messages"]), reverse=True)[:limit]
        texts, compressed, dropped = [], 0, 0
        for card in cards:
            messages = fit_to_length(card["messages"])
            if messages is None:
                dropped += 1
                continue
            compressed += len(messages) < len(card["messages"])
            texts.append(tokenizer.apply_chat_template(messages, tokenize=False))
        versions = sorted({c.get("prompt_version", "unknown") for c in cards})
        return HFDataset.from_dict({"text": texts}), compressed, dropped, versions

    train, train_compressed, train_dropped, prompt_versions = load_cards(train_dataset.path, max_train_cards)
    validation, val_compressed, val_dropped, _ = load_cards(validation_dataset.path)
    if len(train) == 0 or len(validation) == 0:
        raise ValueError(
            f"No cards left after fitting to max_seq_length={max_len}: "
            f"train {len(train)} (dropped {train_dropped}), validation {len(validation)} (dropped {val_dropped})"
        )
    mark("tokenizer_and_data_loaded")
    logger.info(
        f"Cards: train {len(train)} (compressed {train_compressed}, dropped {train_dropped}), "
        f"validation {len(validation)} (compressed {val_compressed}, dropped {val_dropped}), "
        f"prompt versions {prompt_versions}"
    )

    # Base model: 4-bit on GPU (QLoRA). T4 GPUs have no native bf16, so fp16.
    if use_quantization:
        quantization = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        base = AutoModelForCausalLM.from_pretrained(
            base_model_id, revision=revision, quantization_config=quantization, device_map={"": 0}
        )
        # Freezes the base weights, casts the small non-quantized layers (norms)
        # to fp32 for numerical stability, and enables gradient checkpointing.
        base = prepare_model_for_kbit_training(base, use_gradient_checkpointing=True)
    else:
        base = AutoModelForCausalLM.from_pretrained(base_model_id, revision=revision, torch_dtype=torch.float32)

    mark("base_model_loaded_and_quantized")

    lora_config = LoraConfig(
        r=hp["lora_r"],
        lora_alpha=hp["lora_alpha"],
        lora_dropout=hp["lora_dropout"],
        target_modules=hp["lora_target_modules"],
        bias="none",
        task_type="CAUSAL_LM",
    )

    # Completion-only loss: labels are masked (-100) up to the LAST <|assistant|>,
    # so only the final tutor reply and its <|end|> are graded.
    collator = DataCollatorForCompletionOnlyLM(response_template="<|assistant|>", tokenizer=tokenizer)

    output_dir = tempfile.mkdtemp()
    config = SFTConfig(
        output_dir=output_dir,
        dataset_text_field="text",
        max_seq_length=max_len,
        packing=False,  # incompatible with completion-only loss
        num_train_epochs=hp["num_train_epochs"],
        max_steps=max_steps,
        learning_rate=hp["learning_rate"],
        per_device_train_batch_size=hp["per_device_train_batch_size"],
        per_device_eval_batch_size=hp["per_device_eval_batch_size"],
        gradient_accumulation_steps=hp["gradient_accumulation_steps"],
        gradient_checkpointing=use_quantization,
        gradient_checkpointing_kwargs={"use_reentrant": False} if use_quantization else None,
        optim="paged_adamw_8bit" if use_quantization else "adamw_torch",
        fp16=on_gpu,
        bf16=False,
        eval_strategy="steps",
        eval_steps=hp["eval_steps"],
        save_strategy="steps",
        save_steps=hp["eval_steps"],
        save_total_limit=2,
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        logging_steps=hp["logging_steps"],
        logging_dir=metrics.path,
        report_to=["tensorboard"],
        seed=hp["seed"],
    )
    trainer = SFTTrainer(
        model=base,
        args=config,
        train_dataset=train,
        eval_dataset=validation,
        peft_config=lora_config,
        data_collator=collator,
        processing_class=tokenizer,
    )
    mark("trainer_ready")  # LoRA added, datasets tokenized
    trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in trainer.model.parameters())
    logger.info(f"Trainable parameters: {trainable:,} of {total:,}")

    start = time.time()
    result = trainer.train()
    train_seconds = time.time() - start
    mark("training_done")
    final_eval = trainer.evaluate()  # on the best checkpoint (load_best_model_at_end)
    mark("final_evaluation_done")

    # Save the adapter (best checkpoint), the tokenizer and a record of the run.
    os.makedirs(model.path, exist_ok=True)
    trainer.save_model(model.path)
    tokenizer.save_pretrained(model.path)
    eval_history = [
        {"step": e["step"], "eval_loss": e["eval_loss"]} for e in trainer.state.log_history if "eval_loss" in e
    ]
    info = {
        "base_model_id": base_model_id,
        "base_model_revision": revision,
        "prompt_versions": prompt_versions,
        "hyperparameters": hp,
        "use_quantization": use_quantization,
        "max_steps": max_steps,
        "train_cards": len(train),
        "validation_cards": len(validation),
        "cards_compressed": train_compressed + val_compressed,
        "cards_dropped": train_dropped + val_dropped,
        "trainable_parameters": trainable,
        "global_steps": trainer.state.global_step,
        "best_checkpoint": trainer.state.best_model_checkpoint,
        "best_eval_loss": final_eval["eval_loss"],
        "final_train_loss": result.training_loss,
        "train_seconds": train_seconds,
        "seconds_per_step": train_seconds / max(trainer.state.global_step, 1),
        "peak_gpu_memory_gb": torch.cuda.max_memory_allocated() / 1e9 if on_gpu else None,
        "eval_history": eval_history,
        "versions": {
            "torch": torch.__version__,
            "transformers": transformers.__version__,
            "peft": peft.__version__,
            "trl": trl.__version__,
        },
    }
    mark("saved")
    eval_runtimes = [e["eval_runtime"] for e in trainer.state.log_history if "eval_runtime" in e]
    evals_during_training = eval_runtimes[:-1]  # the last one is the final evaluate()
    steps = max(trainer.state.global_step, 1)
    info["timings_seconds"] = {
        "marks_since_function_start": marks,
        "setup_in_function": marks["trainer_ready"],
        "training_including_validation": round(train_seconds, 1),
        "validation_during_training": round(sum(evals_during_training), 1),
        "validation_runs_during_training": len(evals_during_training),
        "seconds_per_validation_run": round(sum(evals_during_training) / max(len(evals_during_training), 1), 1),
        "seconds_per_update_excluding_validation": round((train_seconds - sum(evals_during_training)) / steps, 1),
        "final_evaluation": round(final_eval["eval_runtime"], 1),
        "save": round(marks["saved"] - marks["final_evaluation_done"], 1),
        "note": "pip install, image pull and provisioning happen before this function: see Cloud Logging",
    }
    with open(os.path.join(model.path, "training_info.json"), "w", encoding="utf-8") as file:
        json.dump(info, file, indent=2)

    # Kubeflow metrics (numbers only), visible in the Vertex console.
    for key in ("lora_r", "lora_alpha", "lora_dropout", "learning_rate", "num_train_epochs", "max_seq_length"):
        metrics.log_metric(key, hp[key])
    for key in ("train_cards", "validation_cards", "cards_compressed", "global_steps", "best_eval_loss",
                "final_train_loss", "train_seconds", "seconds_per_step", "trainable_parameters"):
        metrics.log_metric(key, info[key])
    for key, value in info["timings_seconds"].items():
        if isinstance(value, (int, float)):
            metrics.log_metric(f"time_{key}", value)
    if info["peak_gpu_memory_gb"] is not None:
        metrics.log_metric("peak_gpu_memory_gb", info["peak_gpu_memory_gb"])
    model.metadata.update({"base_model_id": base_model_id, "base_model_revision": revision or "local",
                           "prompt_versions": ",".join(prompt_versions)})
    logger.info(f"Training done: {json.dumps({k: v for k, v in info.items() if k != 'eval_history'})}")
