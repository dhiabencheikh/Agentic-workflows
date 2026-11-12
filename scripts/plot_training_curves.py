"""Training and validation loss curves of a fine-tuning run, from its TensorBoard event files.

Writes the plotted values to a CSV (the source of every point) and a PNG for slides.
Run: uv run --with "setuptools<81" --with matplotlib python -m scripts.plot_training_curves \
        --logdir logs/m2_full_run --csv docs/results/m2_full_run_curves.csv --png docs/figures/m2_loss_curves.png
"""

import argparse
import csv

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

# Reference palette of the dataviz guidelines: categorical slots 1 (blue) and 2 (orange), light surface.
SURFACE, TEXT, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#6b6a63", "#e4e3de"
TRAIN_COLOR, VAL_COLOR = "#2a78d6", "#eb6834"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logdir", required=True)
    parser.add_argument("--csv", required=True)
    parser.add_argument("--png", required=True)
    parser.add_argument("--final-step", type=int, default=105, help="step of the final re-evaluation, not plotted")
    args = parser.parse_args()

    acc = EventAccumulator(args.logdir)
    acc.Reload()
    train = [(e.step, e.value) for e in acc.Scalars("train/loss")]
    # The last eval point is the re-evaluation of the best checkpoint after training, not a training-time point.
    val = [(e.step, e.value) for e in acc.Scalars("eval/loss") if e.step != args.final_step]

    with open(args.csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["series", "update", "loss"])
        writer.writerows([("train", s, round(v, 4)) for s, v in train] + [("validation", s, round(v, 4)) for s, v in val])

    best_step, best_val = min(val, key=lambda p: p[1])
    base_val = val[0][1]
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 13})
    fig, ax = plt.subplots(figsize=(10, 5.6), dpi=200)
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    ax.plot(*zip(*train), color=TRAIN_COLOR, linewidth=2, label="Training loss (566 cards)")
    ax.plot(*zip(*val), color=VAL_COLOR, linewidth=2, linestyle="--", marker="o", markersize=6,
            markeredgecolor=SURFACE, markeredgewidth=1.5, label="Validation loss (99 cards, unseen problems)")
    ax.axvline(best_step, color=MUTED, linewidth=1, linestyle=":")
    ax.annotate(f"Base model: {base_val:.2f}", (0, base_val), xytext=(8, 4), textcoords="offset points", color=TEXT)
    ax.annotate(f"Best checkpoint kept\nupdate {best_step}: {best_val:.2f}", (best_step, best_val),
                xytext=(10, -42), textcoords="offset points", color=TEXT)
    ax.annotate("over-fitting", (90, max(v for s, v in val if s > best_step)), xytext=(-10, 10),
                textcoords="offset points", color=MUTED, ha="right")
    ax.text(train[-1][0] + 1, train[-1][1], "training", color=TEXT, va="center")
    ax.text(val[-1][0] + 1, val[-1][1], "validation", color=TEXT, va="center")
    ax.set_xlabel("Update (16 cards each)", color=TEXT)
    ax.set_ylabel("Loss (tutor reply tokens only)", color=TEXT)
    ax.set_title(f"Validation loss falls {100 * (base_val - best_val) / base_val:.0f}% from the base model, "
                 f"then rises: update {best_step} kept", color=TEXT, loc="left", fontsize=14, pad=12)
    ax.set_xlim(-3, 118)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.legend(frameon=False, loc="upper right", labelcolor=TEXT)
    fig.tight_layout()
    fig.savefig(args.png, facecolor=SURFACE)
    print(f"{len(train)} training points, {len(val)} validation points -> {args.csv}, {args.png}")


if __name__ == "__main__":
    main()
