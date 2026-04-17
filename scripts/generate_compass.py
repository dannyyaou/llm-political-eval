#!/usr/bin/env python3
"""Generate a political compass chart from benchmark results."""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from pathlib import Path

# Model data: (name, economic, social, color, marker)
MODELS = [
    ("KIMI K2",        +0.276, +0.361, "#e74c3c", "o"),
    ("Claude Opus 4.6", +0.121, +0.245, "#8e44ad", "s"),
    ("Grok-3",         +0.089, +0.217, "#2c3e50", "D"),
    ("GPT-5.3",        -0.066, -0.030, "#27ae60", "^"),
]

OUTPUT_DIR = Path(__file__).resolve().parent.parent / "assets"


def generate_compass():
    fig, ax = plt.subplots(figsize=(10, 10), dpi=150)

    # Quadrant background colors (soft pastels)
    ax.fill_between([0, 1], [0, 0], [1, 1], color="#fce4e4", alpha=0.5)   # Right-Progressive
    ax.fill_between([0, 1], [-1, -1], [0, 0], color="#e4f0fc", alpha=0.5) # Right-Conservative
    ax.fill_between([-1, 0], [0, 0], [1, 1], color="#e4fce4", alpha=0.5)  # Left-Progressive
    ax.fill_between([-1, 0], [-1, -1], [0, 0], color="#fcf4e4", alpha=0.5) # Left-Conservative

    # Quadrant labels
    quad_style = dict(fontsize=10, color="#999999", ha="center", va="center", style="italic")
    ax.text(-0.5, +0.5, "Left-Progressive", **quad_style)
    ax.text(+0.5, +0.5, "Right-Progressive", **quad_style)
    ax.text(-0.5, -0.5, "Left-Conservative", **quad_style)
    ax.text(+0.5, -0.5, "Right-Conservative", **quad_style)

    # Axes lines
    ax.axhline(0, color="#cccccc", linewidth=1, zorder=1)
    ax.axvline(0, color="#cccccc", linewidth=1, zorder=1)

    # Grid
    ax.set_xlim(-1.05, 1.05)
    ax.set_ylim(-1.05, 1.05)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.2, linestyle="--")

    # Plot models
    for name, econ, social, color, marker in MODELS:
        # Note: economic axis is inverted in display (left = positive value, but
        # on a standard compass left is on the left side of the chart)
        # Economic: +1.0 = interventionist/left, -1.0 = free market/right
        # So we negate economic to put left on the left side of the chart
        x = -econ  # negate so left-leaning appears on the left
        y = social
        ax.scatter(x, y, c=color, marker=marker, s=200, zorder=5, edgecolors="white", linewidths=1.5)
        ax.annotate(
            name,
            (x, y),
            textcoords="offset points",
            xytext=(12, 8),
            fontsize=11,
            fontweight="bold",
            color=color,
            zorder=6,
        )

    # Axis labels
    ax.set_xlabel("← Economic Left          Economic Right →", fontsize=12, fontweight="bold", labelpad=12)
    ax.set_ylabel("← Social Conservative          Social Progressive →", fontsize=12, fontweight="bold", labelpad=12)

    # Title
    ax.set_title(
        "LLM Political Compass\n102 structured questions across 14 policy areas",
        fontsize=16,
        fontweight="bold",
        pad=20,
    )

    # Tick labels
    ax.set_xticks([-1.0, -0.5, 0, 0.5, 1.0])
    ax.set_xticklabels(["-1.0\n(Left)", "-0.5", "0", "+0.5", "+1.0\n(Right)"])
    ax.set_yticks([-1.0, -0.5, 0, 0.5, 1.0])
    ax.set_yticklabels(["-1.0\n(Conservative)", "-0.5", "0", "+0.5", "+1.0\n(Progressive)"])

    # Legend
    legend_handles = [
        mpatches.Patch(color=color, label=f"{name}  (E:{econ:+.3f}, S:{social:+.3f})")
        for name, econ, social, color, _ in MODELS
    ]
    ax.legend(
        handles=legend_handles,
        loc="lower left",
        fontsize=10,
        framealpha=0.9,
        edgecolor="#cccccc",
        title="Model  (Economic, Social)",
        title_fontsize=10,
    )

    # Subtitle / footer
    fig.text(
        0.5, 0.01,
        "Refusals scored as most conservative position  ·  github.com/dannyyaou/llm-political-eval",
        ha="center", fontsize=9, color="#999999",
    )

    plt.tight_layout(rect=[0, 0.03, 1, 1])

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_png = OUTPUT_DIR / "political_compass.png"
    fig.savefig(out_png, bbox_inches="tight", facecolor="white")
    print(f"Saved: {out_png}")

    plt.close(fig)


if __name__ == "__main__":
    generate_compass()
