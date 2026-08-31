"""LinkedIn feed graphic for Pattern Forge hero (2025 clean PIT)."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "models" / "pattern_forge" / "v2_latest.json"
OUT = ROOT / "models" / "pattern_forge" / "plots" / "linkedin_pattern_forge_hero.png"


def main() -> None:
  payload = json.loads(SRC.read_text(encoding="utf-8"))
  months = payload["months"]
  labels = [m["month"][:3].title() for m in months]
  caps = [months[0]["capital_start"]] + [m["capital_end"] for m in months]

  fig = plt.figure(figsize=(12, 6.28), dpi=180, facecolor="#0B0F14")
  gs = fig.add_gridspec(
    2,
    3,
    height_ratios=[1.15, 3.2],
    hspace=0.35,
    wspace=0.08,
    left=0.06,
    right=0.97,
    top=0.88,
    bottom=0.12,
  )

  fig.text(
    0.06,
    0.955,
    "Free money?",
    fontsize=22,
    fontweight="700",
    color="#F4F7FB",
    fontfamily="DejaVu Sans",
    va="top",
  )
  fig.text(
    0.245,
    0.955,
    "Not quite.",
    fontsize=22,
    fontweight="600",
    color="#7DD3A0",
    fontfamily="DejaVu Sans",
    va="top",
  )
  fig.text(
    0.06,
    0.905,
    "GodFather  ·  Pattern Forge  ·  clean PIT backtest 2025  ·  automated paper path",
    fontsize=10,
    color="#8B9AAB",
    fontfamily="DejaVu Sans",
    va="top",
  )

  stats = [
    ("+103%", "year return", "#7DD3A0"),
    ("10 / 12", "green months", "#7EC8E3"),
    ("−5.7%", "worst month", "#F0B27A"),
  ]
  for i, (big, sub, color) in enumerate(stats):
    ax = fig.add_subplot(gs[0, i])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    box = FancyBboxPatch(
      (0.02, 0.08),
      0.96,
      0.84,
      boxstyle="round,pad=0.02,rounding_size=0.08",
      linewidth=1.2,
      edgecolor="#1E2A38",
      facecolor="#121A24",
    )
    ax.add_patch(box)
    ax.text(0.08, 0.58, big, fontsize=26, fontweight="700", color=color, va="center")
    ax.text(0.08, 0.28, sub, fontsize=11, color="#8B9AAB", va="center")

  ax = fig.add_subplot(gs[1, :])
  ax.set_facecolor("#121A24")
  for spine in ax.spines.values():
    spine.set_color("#1E2A38")
  ax.tick_params(colors="#8B9AAB", labelsize=9)
  ax.grid(True, color="#1E2A38", linewidth=0.8, alpha=0.9)
  ax.set_axisbelow(True)

  path_x = np.arange(len(caps))
  path_y = np.array(caps)
  ax.fill_between(path_x, path_y, 10000, where=path_y >= 10000, color="#7DD3A0", alpha=0.16, interpolate=True)
  ax.fill_between(path_x, path_y, 10000, where=path_y < 10000, color="#E07A5F", alpha=0.16, interpolate=True)
  ax.plot(path_x, path_y, color="#7DD3A0", linewidth=2.8)
  ax.scatter([0, len(caps) - 1], [caps[0], caps[-1]], c=["#8B9AAB", "#7DD3A0"], s=36, zorder=5)
  ax.axhline(10000, color="#3A4A5C", linestyle="--", linewidth=1)

  ax.set_xticks(np.arange(1, 13))
  ax.set_xticklabels(labels)
  ax.set_xlim(-0.15, 12.15)
  ax.set_ylim(min(caps) * 0.93, max(caps) * 1.08)
  ax.set_ylabel("equity (₹)", fontsize=10, color="#8B9AAB")
  ax.annotate(
    "₹10,000 start",
    xy=(0, 10000),
    xytext=(12, -22),
    textcoords="offset points",
    color="#8B9AAB",
    fontsize=9,
  )
  ax.annotate(
    "₹20,325 end",
    xy=(12, caps[-1]),
    xytext=(-78, 12),
    textcoords="offset points",
    color="#7DD3A0",
    fontsize=11,
    fontweight="700",
  )

  fig.text(
    0.06,
    0.035,
    "Hero method: daily swing + mistake ledger + profit guard  ·  ~20 specialist agents (veto / size-down only)",
    fontsize=8.5,
    color="#6B7C8F",
    fontfamily="DejaVu Sans",
  )

  OUT.parent.mkdir(parents=True, exist_ok=True)
  fig.savefig(OUT, facecolor=fig.get_facecolor(), edgecolor="none")
  plt.close(fig)
  print(OUT)


if __name__ == "__main__":
  main()
