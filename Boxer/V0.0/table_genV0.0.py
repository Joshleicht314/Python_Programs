i#!/usr/bin/env python3
"""
tableplan_gen.py  —  CSV → tableplan YAML generator

Reads a CSV with columns:  name, height, width
Produces a tableplan-compatible YAML file with:
  - randomized unique colors per block
  - greedy non-overlapping placement (row-major order)
  - user-supplied or auto-generated row/column labels

Usage:
    python tableplan_gen.py input.csv [output.yaml] [OPTIONS]

Options:
    --rows   R1,R2,...    comma-separated row labels (or a count like 5)
    --cols   C1,C2,...    comma-separated column labels (or a count like 7)
    --name   "My Table"   table name (default: derived from filename)
    --wrap                enable block_wrap in settings
    --steps  N            height_steps per row unit (default: 2)
    --seed   N            random seed for reproducibility

Examples:
    python tableplan_gen.py blocks.csv schedule.yaml \\
        --rows "8am,9am,10am,11am,12pm" --cols "Mon,Tue,Wed,Thu,Fri"

    python tableplan_gen.py blocks.csv out.yaml --rows 10 --cols 7 --seed 42
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import random
import sys
from dataclasses import dataclass, field
from typing import Optional

import yaml


# ── Colour palette (mirrors tableplan.py) ─────────────────────────────────────

_PALETTE_BG = [
    "green", "blue", "dark_magenta", "dark_cyan", "red3", "yellow",
    "spring_green2", "dark_blue", "magenta", "cyan", "orange3", "purple",
    "deep_sky_blue3", "chartreuse3", "hot_pink3", "gold3", "steel_blue",
    "dark_olive_green3", "indian_red", "slate_blue1", "turquoise2", "rosy_brown",
]
_PALETTE_FG = [
    "black", "white", "white", "black", "white", "black",
    "black", "white", "black", "black", "black", "white",
    "black", "black", "black", "black", "white",
    "black", "white", "white", "black", "white",
]


# ── Data structures ───────────────────────────────────────────────────────────

@dataclass
class BlockSpec:
    name:   str
    height: float
    width:  int


@dataclass
class PlacedBlock:
    name:        str
    height:      float
    width:       int
    row:         float
    col:         int
    color_idx:   int
    transparent: bool = False
    group:       Optional[str] = None


# ── CSV parsing ───────────────────────────────────────────────────────────────

def parse_csv(path: str) -> list[BlockSpec]:
    blocks: list[BlockSpec] = []
    with open(path, newline="", encoding="utf-8") as f:
        # Auto-detect if there's a header
        sample = f.read(1024); f.seek(0)
        has_header = csv.Sniffer().has_header(sample)
        reader = csv.reader(f)
        if has_header:
            next(reader)           # skip header row
        for lineno, row in enumerate(reader, 2):
            if not row or all(c.strip() == "" for c in row):
                continue
            if len(row) < 3:
                print(f"  Warning: line {lineno} has fewer than 3 columns — skipping: {row}",
                      file=sys.stderr)
                continue
            name   = row[0].strip() or f"Block{lineno}"
            try:
                height = float(row[1].strip())
            except ValueError:
                print(f"  Warning: bad height '{row[1]}' on line {lineno}, defaulting to 1.0",
                      file=sys.stderr)
                height = 1.0
            try:
                width  = max(1, int(row[2].strip()))
            except ValueError:
                print(f"  Warning: bad width '{row[2]}' on line {lineno}, defaulting to 1",
                      file=sys.stderr)
                width = 1
            blocks.append(BlockSpec(name=name, height=height, width=width))
    return blocks


# ── Axis label generation ─────────────────────────────────────────────────────

def parse_axis(spec: Optional[str], fallback_count: int) -> list[str]:
    """Parse --rows / --cols argument.  Either 'A,B,C' or a plain integer."""
    if spec is None:
        return [str(i + 1) for i in range(fallback_count)]
    spec = spec.strip()
    if spec.isdigit():
        return [str(i + 1) for i in range(int(spec))]
    return [s.strip() for s in spec.split(",") if s.strip()]


# ── Greedy non-overlapping placement ─────────────────────────────────────────

def place_blocks(specs: list[BlockSpec],
                 n_rows: int, n_cols: int,
                 height_steps: int,
                 rng: random.Random) -> list[PlacedBlock]:
    """
    Greedy row-major placement.
    Tries to place each block without overlapping previously placed blocks.
    Falls back to first available cell if no clean spot found.
    """
    placed:  list[PlacedBlock] = []
    used_colors: set[int] = set()
    total_colors = len(_PALETTE_BG)

    # Occupancy grid: (step_row, col) -> bool
    occupied: dict[tuple[int, int], bool] = {}

    def is_free(row_s: int, col: int, bh_s: int, bw: int) -> bool:
        for r in range(row_s, row_s + bh_s):
            for c in range(col, col + bw):
                if occupied.get((r, c), False):
                    return False
        return True

    def mark(row_s: int, col: int, bh_s: int, bw: int) -> None:
        for r in range(row_s, row_s + bh_s):
            for c in range(col, col + bw):
                occupied[(r, c)] = True

    def next_color() -> int:
        for i in range(total_colors):
            if i not in used_colors:
                used_colors.add(i); return i
        # All used — pick random
        idx = rng.randint(0, total_colors - 1)
        return idx

    for spec in specs:
        bh_s = max(1, round(spec.height * height_steps))
        bw   = spec.width
        placed_at: Optional[tuple[int, int]] = None

        # Scan row-major for a free spot
        for r in range(n_rows * height_steps - bh_s + 1):
            for c in range(n_cols - bw + 1):
                if is_free(r, c, bh_s, bw):
                    placed_at = (r, c); break
            if placed_at: break

        if placed_at is None:
            # No free spot — stack at (0, 0) with a warning
            print(f"  Warning: no free spot for '{spec.name}' — placing at (0,0), may overlap",
                  file=sys.stderr)
            placed_at = (0, 0)

        row_s, col = placed_at
        mark(row_s, col, bh_s, bw)
        cidx = next_color()
        placed.append(PlacedBlock(
            name      = spec.name,
            height    = spec.height,
            width     = spec.width,
            row       = row_s / height_steps,
            col       = col,
            color_idx = cidx,
        ))

    return placed


# ── YAML output ───────────────────────────────────────────────────────────────

def write_yaml(path: str, table_name: str,
               rows: list[str], cols: list[str],
               blocks: list[PlacedBlock],
               height_steps: int,
               block_wrap: bool) -> None:
    settings: dict = {"height_steps": height_steps, "zoom_h": 1.0, "zoom_w": 1.0,
                      "block_wrap": block_wrap}
    blocks_data = []
    for b in blocks:
        bd = {"name": b.name, "height": b.height, "width": b.width,
              "row": b.row, "col": b.col,
              "transparent": b.transparent, "color_idx": b.color_idx}
        if b.group: bd["group"] = b.group
        blocks_data.append(bd)

    data = {
        "table":    {"name": table_name, "columns": cols, "rows": rows},
        "settings": settings,
        "blocks":   blocks_data,
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(
        description="Generate a tableplan YAML from a CSV (name, height, width).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("csv",   help="Input CSV file (name, height, width)")
    p.add_argument("yaml",  nargs="?", help="Output YAML file (default: <csv>.yaml)")
    p.add_argument("--rows",  default=None,
                   help="Row labels: 'A,B,C' or an integer count")
    p.add_argument("--cols",  default=None,
                   help="Column labels: 'A,B,C' or an integer count")
    p.add_argument("--name",  default=None, help="Table name")
    p.add_argument("--wrap",  action="store_true", help="Enable block_wrap")
    p.add_argument("--steps", type=int, default=2,
                   help="height_steps (subdivisions per row, default 2 → 0.5 units)")
    p.add_argument("--seed",  type=int, default=None, help="Random seed")
    args = p.parse_args()

    if not os.path.isfile(args.csv):
        print(f"Error: '{args.csv}' not found.", file=sys.stderr); sys.exit(1)

    out_path   = args.yaml or os.path.splitext(args.csv)[0] + ".yaml"
    table_name = args.name or os.path.splitext(os.path.basename(args.csv))[0].replace("_", " ").title()
    rng        = random.Random(args.seed)

    print(f"Reading: {args.csv}")
    specs = parse_csv(args.csv)
    if not specs:
        print("Error: no valid blocks found in CSV.", file=sys.stderr); sys.exit(1)
    print(f"  {len(specs)} block(s) loaded")

    # Determine grid size
    total_h_units = sum(s.height for s in specs)
    max_w         = max(s.width for s in specs)

    # Default grid: enough rows to hold all blocks stacked, enough cols for widest
    default_rows = max(1, math.ceil(total_h_units))
    default_cols = max(1, max_w)

    rows = parse_axis(args.rows, default_rows)
    cols = parse_axis(args.cols, default_cols)
    n_rows, n_cols = len(rows), len(cols)
    print(f"  Grid: {n_rows} rows × {n_cols} cols  (steps={args.steps})")

    # Cap block widths to n_cols
    for s in specs:
        if s.width > n_cols:
            print(f"  Warning: '{s.name}' width {s.width} > {n_cols} cols — clamped",
                  file=sys.stderr)
            s.width = n_cols

    placed = place_blocks(specs, n_rows, n_cols, args.steps, rng)
    print(f"  {len(placed)} block(s) placed")

    write_yaml(out_path, table_name, rows, cols, placed, args.steps, args.wrap)
    print(f"Written: {out_path}")
    print(f"\nOpen with:  python tableplan.py {out_path}")


if __name__ == "__main__":
    main()
