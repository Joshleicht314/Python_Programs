#!/usr/bin/env python3
"""
tableplan v0.3 — vim-style terminal table organizer

Usage:
    python tableplan.py              # in-memory demo
    python tableplan.py myplan.yaml  # load or create YAML file
"""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Callable, Optional

import yaml
from textual import events
from textual.app import App, ComposeResult
from textual.strip import Strip
from textual.widget import Widget
from rich.segment import Segment
from rich.style import Style


# ─────────────────────────────────────────────────────────────────────────────
#  Color palette
# ─────────────────────────────────────────────────────────────────────────────

_BG_COLORS = [
    ("green",          "black"),
    ("blue",           "white"),
    ("dark_magenta",   "white"),
    ("dark_cyan",      "black"),
    ("red",            "white"),
    ("yellow",         "black"),
    ("bright_green",   "black"),
    ("dark_blue",      "white"),
    ("magenta",        "black"),
    ("cyan",           "black"),
    ("orange3",        "black"),
    ("purple",         "white"),
]

def _solid_style(cidx: int) -> Style:
    bg, fg = _BG_COLORS[cidx % len(_BG_COLORS)]
    return Style(bgcolor=bg, color=fg, bold=True)

def _transp_style(cidx: int) -> Style:
    bg, _ = _BG_COLORS[cidx % len(_BG_COLORS)]
    return Style(bgcolor=bg, color="bright_black")

def _cursor_style(cidx: int) -> Style:
    bg, fg = _BG_COLORS[cidx % len(_BG_COLORS)]
    return Style(bgcolor="white", color=bg, bold=True, underline=True)

def _conflict_style(cidx: int) -> Style:
    bg, _ = _BG_COLORS[cidx % len(_BG_COLORS)]
    return Style(bgcolor=bg, color="bright_white", bold=True, blink=True)

S_BORDER  = Style(color="bright_black")
S_HEADER  = Style(color="cyan", bold=True)
S_LABEL   = Style(color="white")
S_GRABBED = Style(color="black", bgcolor="yellow")
S_GHOST_X = Style(color="white", bgcolor="red")          # out-of-bounds ghost
S_GHOST_C = Style(color="black", bgcolor="dark_orange3") # conflict ghost
S_CURSOR  = Style(color="white", bgcolor="blue", bold=True)
S_EMPTY   = Style()
S_STATUS  = Style(color="bright_white")
S_ERR     = Style(color="red", bold=True)

_HINT = (
    "  hjkl:move  spc:grab  a:add  e:edit  x:del  v:transp  "
    "o/O:row  i/I:col  d/D:del  -/+:zoom  \":vim  ZZ/:w:save  :check"
)


# ─────────────────────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    name:        str
    height:      float        # units; multiples of (1/height_steps)
    width:       int          # columns spanned
    row:         float        # top-left row in units (0-based)
    col:         int          # top-left column index
    transparent: bool = False
    color_idx:   int  = 0


@dataclass
class TableData:
    name:    str
    columns: list[str]
    rows:    list[str]
    blocks:  list[Block] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
#  Settings  (saved per-file; these are the embedded defaults)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Settings:
    height_steps:     int            = 2     # subdivisions per row unit
    zoom_h:           float          = 1.0
    zoom_w:           float          = 1.0
    wrap_cursor:      bool           = False
    max_visible_cols: Optional[int]  = None  # :set width N
    max_visible_rows: Optional[int]  = None  # :set height N


# ─────────────────────────────────────────────────────────────────────────────
#  YAML persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_yaml(path: str) -> tuple[TableData, Settings]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    t  = data["table"]
    table = TableData(name=t["name"], columns=list(t["columns"]), rows=list(t["rows"]))
    for bd in data.get("blocks", []):
        table.blocks.append(Block(
            name        = str(bd["name"]),
            height      = float(bd.get("height", 1.0)),
            width       = int(bd.get("width", 1)),
            row         = float(bd.get("row", 0.0)),
            col         = int(bd.get("col", 0)),
            transparent = bool(bd.get("transparent", False)),
            color_idx   = int(bd.get("color_idx", 0)),
        ))
    sd = data.get("settings", {})
    settings = Settings(
        height_steps     = int(sd.get("height_steps", 2)),
        zoom_h           = float(sd.get("zoom_h", 1.0)),
        zoom_w           = float(sd.get("zoom_w", 1.0)),
        wrap_cursor      = bool(sd.get("wrap_cursor", False)),
        max_visible_cols = sd.get("max_visible_cols"),
        max_visible_rows = sd.get("max_visible_rows"),
    )
    return table, settings


def save_yaml(path: str, table: TableData, settings: Settings) -> None:
    sd: dict = {
        "height_steps": settings.height_steps,
        "zoom_h":       settings.zoom_h,
        "zoom_w":       settings.zoom_w,
        "wrap_cursor":  settings.wrap_cursor,
    }
    if settings.max_visible_cols is not None: sd["max_visible_cols"] = settings.max_visible_cols
    if settings.max_visible_rows is not None: sd["max_visible_rows"] = settings.max_visible_rows
    data = {
        "table":    {"name": table.name, "columns": table.columns, "rows": table.rows},
        "settings": sd,
        "blocks":   [
            {"name": b.name, "height": b.height, "width": b.width,
             "row": b.row, "col": b.col, "transparent": b.transparent,
             "color_idx": b.color_idx}
            for b in table.blocks
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _demo_table() -> tuple[TableData, Settings]:
    table = TableData(
        name    = "Weekly Schedule",
        columns = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        rows    = ["8:00am", "9:00am", "10:00am", "11:00am", "12:00pm"],
        blocks  = [
            Block("Dog Walk",  0.5, 1, 0.0, 0, color_idx=0),
            Block("Standup",   0.5, 5, 1.0, 0, color_idx=1),
            Block("Deep Work", 2.0, 2, 2.0, 2, color_idx=2),
            Block("Lunch",     1.0, 1, 4.0, 1, color_idx=3),
        ],
    )
    return table, Settings()


# ─────────────────────────────────────────────────────────────────────────────
#  Multi-step inline prompt
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Prompt:
    steps:    list[str]
    defaults: list[str]
    values:   list[str]
    step:     int
    buf:      str
    callback: Callable

    def display(self) -> str:
        label   = self.steps[self.step]
        default = self.defaults[self.step] if self.step < len(self.defaults) else ""
        hint    = f" [{default}]" if default else ""
        return f"  {label}{hint}: {self.buf}"

    def submit(self) -> bool:
        val = self.buf or (self.defaults[self.step] if self.step < len(self.defaults) else "")
        self.values.append(val); self.buf = ""; self.step += 1
        return self.step >= len(self.steps)


# ─────────────────────────────────────────────────────────────────────────────
#  Grid widget
# ─────────────────────────────────────────────────────────────────────────────

class GridWidget(Widget):
    can_focus = True

    def __init__(self, table: TableData, settings: Settings, filepath: Optional[str]) -> None:
        super().__init__()
        self.table          = table
        self.settings       = settings
        self.filepath       = filepath
        self.cursor_row     = 0     # absolute steps (1 step = 1/height_steps units)
        self.cursor_col     = 0     # absolute column index
        self.view_row_off   = 0     # first visible step
        self.view_col_off   = 0     # first visible column index
        self.grabbed: Optional[Block]  = None
        self.prompt:  Optional[Prompt] = None
        self.cmd_mode       = False
        self.cmd_buf        = ""
        self.status         = _HINT
        self.status_err     = False
        self.last_key       = ""
        # Conflict cache — dirty flag set whenever blocks change
        self._conflict_set: set[int]  = set()   # ids of conflicting blocks
        self._conflict_dirty          = True
        # Cached layout (populated by _layout(), used by scroll / mouse helpers)
        self._vis_cols:    list[int] = []
        self._n_vis_steps: int       = 0
        self._step_h:      int       = 1
        self._row_lw:      int       = 8
        self._col_widths:  list[int] = []

    # ── Layout ───────────────────────────────────────────────────────────────

    def _layout(self) -> tuple[int, int, list[int], list[int], int]:
        """
        Derive rendering geometry from terminal size + settings.
        Returns (step_h, row_lw, col_widths, vis_cols, n_vis_steps)
        and updates self._* cache fields.
        """
        W, H   = self.size.width, self.size.height
        n_rows = len(self.table.rows)
        n_cols = len(self.table.columns)
        s      = self.settings

        # ── Row-label column width ───────────────────────────────────────────
        row_lw = max((len(r) for r in self.table.rows), default=5) + 2

        # ── Vertical: step height ────────────────────────────────────────────
        n_steps  = n_rows * s.height_steps
        avail_h  = max(1, H - 2)           # header + status
        base_sh  = max(1, avail_h // max(1, n_steps))
        step_h   = max(1, int(base_sh * s.zoom_h))
        n_vis_s  = min(n_steps, avail_h // step_h)
        if s.max_visible_rows:
            n_vis_s = min(n_vis_s, s.max_visible_rows * s.height_steps)
        n_vis_s = max(1, n_vis_s)

        # ── Horizontal: per-column widths ────────────────────────────────────
        # Natural width per column (widest word in header or any spanning block)
        nat: list[int] = []
        for ci in range(n_cols):
            words = self.table.columns[ci].split()
            for b in self.table.blocks:
                if b.col <= ci < b.col + b.width:
                    words += b.name.split()
            nat.append(max((len(w) for w in words), default=3) + 2)

        # Apply zoom
        zoomed = [max(3, int(w * s.zoom_w)) for w in nat]

        # Greedy: how many columns fit starting at view_col_off?
        avail_w = W - row_lw - 1   # subtract the leftmost │
        vis_cols: list[int] = []
        rem = avail_w
        for ci in range(self.view_col_off, n_cols):
            needed = zoomed[ci] + 1     # +1 for trailing │
            if rem >= needed or not vis_cols:   # always show at least one
                vis_cols.append(ci); rem -= needed
            else:
                break
        if s.max_visible_cols:
            vis_cols = vis_cols[:s.max_visible_cols]

        # Scale visible columns to fill exactly avail_w (up OR down)
        n_sep       = len(vis_cols)                     # one │ per column (trailing)
        avail_data  = avail_w - n_sep                   # chars available for data cells
        nat_vis     = [zoomed[ci] for ci in vis_cols]
        total_nat   = sum(nat_vis)

        if total_nat > 0 and avail_data > 0:
            scale      = avail_data / total_nat
            col_widths = [max(3, int(w * scale)) for w in nat_vis]
            deficit    = avail_data - sum(col_widths)
            if deficit != 0:
                order = sorted(range(len(col_widths)), key=lambda i: -nat_vis[i])
                for idx in order:
                    if deficit == 0: break
                    adj = 1 if deficit > 0 else -1
                    col_widths[idx] = max(3, col_widths[idx] + adj)
                    deficit -= adj
        else:
            col_widths = nat_vis or [avail_data]

        # Cache
        self._step_h      = step_h
        self._row_lw      = row_lw
        self._col_widths  = col_widths
        self._vis_cols    = vis_cols
        self._n_vis_steps = n_vis_s

        return step_h, row_lw, col_widths, vis_cols, n_vis_s

    # ── Scroll ────────────────────────────────────────────────────────────────

    def _scroll_to_cursor(self) -> None:
        s       = self.settings
        n_rows  = len(self.table.rows)
        n_cols  = len(self.table.columns)
        n_steps = max(1, n_rows * s.height_steps)
        nvs     = max(1, self._n_vis_steps)

        self.cursor_row = max(0, min(self.cursor_row, n_steps - 1))
        self.cursor_col = max(0, min(self.cursor_col, n_cols - 1))

        # Vertical
        if self.cursor_row < self.view_row_off:
            self.view_row_off = self.cursor_row
        elif self.cursor_row >= self.view_row_off + nvs:
            self.view_row_off = self.cursor_row - nvs + 1
        self.view_row_off = max(0, min(self.view_row_off, n_steps - 1))

        # Horizontal
        if self.cursor_col < self.view_col_off:
            self.view_col_off = self.cursor_col
        elif self._vis_cols and self.cursor_col > self._vis_cols[-1]:
            # Shift view right so cursor is the last visible column
            self.view_col_off = self.cursor_col - len(self._vis_cols) + 1
        self.view_col_off = max(0, min(self.view_col_off, n_cols - 1))

    # ── Block helpers ─────────────────────────────────────────────────────────

    def _block_steps(self, b: Block) -> tuple[int, int]:
        hs = self.settings.height_steps
        return round(b.row * hs), round((b.row + b.height) * hs)

    def _block_at(self, abs_step: int, ci: int) -> Optional[Block]:
        """Return topmost solid block, then transparent, skipping grabbed."""
        found_t: Optional[Block] = None
        for b in self.table.blocks:
            if b is self.grabbed: continue
            if b.col <= ci < b.col + b.width:
                bs, be = self._block_steps(b)
                if bs <= abs_step < be:
                    if not b.transparent: return b
                    if found_t is None:   found_t = b
        return found_t

    def _in_bounds(self, b: Block, step: int, ci: int) -> bool:
        hs = self.settings.height_steps
        nr = len(self.table.rows); nc = len(self.table.columns)
        bh = round(b.height * hs)
        return 0 <= ci and ci + b.width <= nc and 0 <= step and step + bh <= nr * hs

    def _has_conflict(self, b: Block, step: int, ci: int) -> bool:
        """True if placing b at (step, ci) overlaps any solid non-transparent block."""
        hs = self.settings.height_steps
        bh = round(b.height * hs)
        for ob in self.table.blocks:
            if ob is b or ob.transparent: continue
            obs, obe = self._block_steps(ob)
            if (ci + b.width <= ob.col) or (ci >= ob.col + ob.width): continue
            if (step + bh <= obs)       or (step >= obe):              continue
            return True
        return False

    def _invalidate_conflicts(self) -> None:
        self._conflict_dirty = True

    def _get_conflict_ids(self) -> set[int]:
        if not self._conflict_dirty:
            return self._conflict_set
        result: set[int] = set()
        solid = [b for b in self.table.blocks if not b.transparent]
        for i in range(len(solid)):
            for j in range(i + 1, len(solid)):
                a, b = solid[i], solid[j]
                as_, ae = self._block_steps(a)
                bs_, be = self._block_steps(b)
                col_ok = (a.col + a.width <= b.col) or (a.col >= b.col + b.width)
                row_ok = (ae <= bs_) or (as_ >= be)
                if not col_ok and not row_ok:
                    result.add(id(a)); result.add(id(b))
        self._conflict_set   = result
        self._conflict_dirty = False
        return result

    def _next_color(self) -> int:
        used = {b.color_idx for b in self.table.blocks}
        for i in range(len(_BG_COLORS)):
            if i not in used: return i
        return len(self.table.blocks) % len(_BG_COLORS)

    # ── Rendering ────────────────────────────────────────────────────────────

    def render_line(self, y: int) -> Strip:  # noqa: C901
        if self.size.width == 0 or self.size.height == 0:
            return Strip([])

        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        n_rows = len(self.table.rows)
        H, W   = self.size.height, self.size.width
        hs     = self.settings.height_steps

        # ── Status / prompt / cmd bar ────────────────────────────────────────
        if y == H - 1:
            if self.prompt:
                txt = self.prompt.display().ljust(W)[:W]
                return Strip([Segment(txt, S_STATUS)])
            if self.cmd_mode:
                txt = self.cmd_buf.ljust(W)[:W]
                return Strip([Segment(txt, S_STATUS)])
            style = S_ERR if self.status_err else S_STATUS
            return Strip([Segment(self.status.ljust(W)[:W], style)])

        # ── Column header ────────────────────────────────────────────────────
        if y == 0:
            segs: list[Segment] = [Segment(" " * row_lw, S_EMPTY)]
            for i, ci in enumerate(vis_cols):
                segs.append(Segment("│", S_BORDER))
                segs.append(Segment(self.table.columns[ci][:col_widths[i]].center(col_widths[i]), S_HEADER))
            segs.append(Segment("│", S_BORDER))
            used = row_lw + sum(col_widths) + len(vis_cols) + 1
            if used < W: segs.append(Segment(" " * (W - used), S_EMPTY))
            return Strip(segs)

        # ── Grid body ────────────────────────────────────────────────────────
        body_y       = y - 1
        step_in_view = body_y // step_h
        line_in_step = body_y % step_h
        abs_step     = self.view_row_off + step_in_view

        if step_in_view >= n_vis_s or abs_step >= n_rows * hs:
            return Strip([Segment(" " * W, S_EMPTY)])

        unit_i   = abs_step // hs
        sub_step = abs_step % hs
        show_lbl = (sub_step == 0) and (line_in_step == 0)

        conflict_ids = self._get_conflict_ids()

        segs = []
        if show_lbl and unit_i < len(self.table.rows):
            segs.append(Segment(self.table.rows[unit_i].ljust(row_lw)[:row_lw], S_LABEL))
        else:
            segs.append(Segment(" " * row_lw, S_EMPTY))

        for i, ci in enumerate(vis_cols):
            cw        = col_widths[i]
            is_cursor = (abs_step == self.cursor_row and ci == self.cursor_col)
            segs.append(Segment("│", S_BORDER))

            # Ghost (grabbed block preview)
            cell_done = False
            if self.grabbed is not None:
                gs = self.cursor_row
                ge = gs + round(self.grabbed.height * hs)
                gc = self.cursor_col
                gce = gc + self.grabbed.width
                if gs <= abs_step < ge and gc <= ci < gce:
                    in_b     = self._in_bounds(self.grabbed, gs, gc)
                    conflict = self._has_conflict(self.grabbed, gs, gc)
                    if not in_b:         style = S_GHOST_X
                    elif conflict:       style = S_GHOST_C
                    else:                style = S_GRABBED
                    tot = round(self.grabbed.height * hs) * step_h
                    lig = (abs_step - gs) * step_h + line_in_step
                    txt = self.grabbed.name if lig == max(0, tot // 2) else ""
                    segs.append(Segment(txt[:cw].center(cw), style))
                    cell_done = True

            if not cell_done:
                block = self._block_at(abs_step, ci)
                if block:
                    bs, be = self._block_steps(block)
                    tot  = (be - bs) * step_h
                    lib  = (abs_step - bs) * step_h + line_in_step
                    txt  = block.name if lib == max(0, tot // 2) else ""
                    if is_cursor:
                        style = _cursor_style(block.color_idx)
                    elif block.transparent:
                        style = _transp_style(block.color_idx)
                    elif id(block) in conflict_ids:
                        style = _conflict_style(block.color_idx)
                    else:
                        style = _solid_style(block.color_idx)
                    segs.append(Segment(txt[:cw].center(cw), style))
                else:
                    style = S_CURSOR if (is_cursor and self.grabbed is None) else S_EMPTY
                    segs.append(Segment(" " * cw, style))

        segs.append(Segment("│", S_BORDER))
        used = row_lw + sum(col_widths) + len(vis_cols) + 1
        if used < W: segs.append(Segment(" " * (W - used), S_EMPTY))
        return Strip(segs)

    # ── Input dispatch ────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        if self.prompt:
            self._key_prompt(event)
        elif self.cmd_mode:
            self._key_cmd(event)
        else:
            self._key_normal(event)
        self._scroll_to_cursor()
        self.refresh()

    # ── Normal mode ───────────────────────────────────────────────────────────

    def _key_normal(self, event: events.Key) -> None:  # noqa: C901
        k  = event.key
        ch = event.character or ""
        s  = self.settings
        nc = len(self.table.columns)
        nr = len(self.table.rows)
        ns = nr * s.height_steps

        # ── ZZ write-quit ────────────────────────────────────────────────────
        if ch == "Z":
            if self.last_key == "Z":
                self._save(); self.app.exit(); return
            self.last_key = "Z"; return
        self.last_key = k

        # ── Movement ─────────────────────────────────────────────────────────
        if k == "h":
            if s.wrap_cursor and self.cursor_col == 0 and self.cursor_row > 0:
                self.cursor_col = nc - 1; self.cursor_row -= 1
            else:
                self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "l":
            if s.wrap_cursor and self.cursor_col == nc - 1 and self.cursor_row < ns - 1:
                self.cursor_col = 0; self.cursor_row += 1
            else:
                self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "j":
            self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif k == "k":
            self.cursor_row = max(0, self.cursor_row - 1)

        # ── Grab / cancel ─────────────────────────────────────────────────────
        elif k == "space":
            self._toggle_grab()
        elif k == "escape" and self.grabbed:
            self.grabbed = None; self.status = "  Grab cancelled."; self.status_err = False

        # ── Zoom ──────────────────────────────────────────────────────────────
        elif k == "minus" or ch == "-":
            s.zoom_h = max(0.25, round(s.zoom_h - 0.25, 2))
            s.zoom_w = max(0.25, round(s.zoom_w - 0.25, 2))
            self.status = f"  Zoom {s.zoom_h:.2f}×"
        elif ch in ("+", "="):
            s.zoom_h = min(6.0, round(s.zoom_h + 0.25, 2))
            s.zoom_w = min(6.0, round(s.zoom_w + 0.25, 2))
            self.status = f"  Zoom {s.zoom_h:.2f}×"

        # ── Vim edit ──────────────────────────────────────────────────────────
        elif ch == '"':
            self._open_in_vim()

        # ── Command mode ──────────────────────────────────────────────────────
        elif k == "colon" or ch == ":":
            self.cmd_mode = True; self.cmd_buf = ":"

        # ── Block commands ────────────────────────────────────────────────────
        elif k == "a": self._cmd_add_block()
        elif k == "e": self._cmd_edit_block()
        elif k == "x": self._cmd_delete_block()
        elif k == "v": self._cmd_toggle_transparent()

        # ── Row / column commands ─────────────────────────────────────────────
        elif k == "o": self._cmd_add_row(below=True)
        elif k == "O": self._cmd_add_row(below=False)
        elif k == "d": self._cmd_delete_row()
        elif k == "i": self._cmd_add_col(right=False)
        elif k == "I": self._cmd_add_col(right=True)
        elif k == "D": self._cmd_delete_col()

    # ── Command mode ──────────────────────────────────────────────────────────

    def _key_cmd(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        if k == "escape":
            self.cmd_mode = False; self.cmd_buf = ""; self.status = _HINT
        elif k == "enter":
            self._exec_cmd(); self.cmd_mode = False; self.cmd_buf = ""
        elif k == "backspace":
            self.cmd_buf = self.cmd_buf[:-1]
            if not self.cmd_buf: self.cmd_mode = False
        elif ch and ch.isprintable():
            self.cmd_buf += ch

    def _exec_cmd(self) -> None:  # noqa: C901
        raw   = self.cmd_buf.strip()
        parts = raw.split()
        s     = self.settings

        # ── Quit / save ───────────────────────────────────────────────────────
        if raw in (":q", ":wq", ":x"):
            self._save(); self.app.exit(); return
        if raw == ":q!":
            self.app.exit(); return
        if raw == ":w":
            self._save()
            self.status = f"  Saved → {self.filepath or '(no file)'}"; self.status_err = False; return

        # ── Check ─────────────────────────────────────────────────────────────
        if raw == ":check":
            self._cmd_check(); return

        # ── :set wrap / nowrap ────────────────────────────────────────────────
        if raw == ":set wrap":
            s.wrap_cursor = True; self.status = "  wrap cursor: on"; return
        if raw == ":set nowrap":
            s.wrap_cursor = False; self.status = "  wrap cursor: off"; return

        # ── :set width / height / tolerance ──────────────────────────────────
        if len(parts) == 3 and parts[0] == ":set":
            try:
                val = int(parts[2])
            except ValueError:
                self.status = f"  Bad value: {parts[2]}"; self.status_err = True; return

            if parts[1] == "width":
                s.max_visible_cols = max(1, val)
                self.status = f"  visible columns: {s.max_visible_cols}"; return
            if parts[1] == "height":
                s.max_visible_rows = max(1, val)
                self.status = f"  visible rows: {s.max_visible_rows}"; return
            if parts[1] == "tolerance":
                unit_pos        = self.cursor_row / s.height_steps
                s.height_steps  = max(1, val)
                self.cursor_row = round(unit_pos * s.height_steps)
                self.status = (
                    f"  tolerance: {s.height_steps} steps/unit "
                    f"(min {1/s.height_steps:.3g} units)"
                ); return

        # ── :set tolerance H W  (two values) ─────────────────────────────────
        if len(parts) == 4 and parts[0] == ":set" and parts[1] == "tolerance":
            try:
                hs = max(1, int(parts[2]))
            except ValueError:
                self.status = "  Bad value"; self.status_err = True; return
            unit_pos        = self.cursor_row / s.height_steps
            s.height_steps  = hs
            self.cursor_row = round(unit_pos * hs)
            self.status = f"  tolerance: {hs} steps/unit  (width arg ignored — cols are always whole)"; return

        self.status = f"  Unknown: {raw}"; self.status_err = True

    def _save(self) -> None:
        if self.filepath:
            save_yaml(self.filepath, self.table, self.settings)

    # ── Prompt mode ───────────────────────────────────────────────────────────

    def _key_prompt(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        p = self.prompt
        if k == "escape":
            self.prompt = None; self.status = "  Cancelled."; self.status_err = False
        elif k == "enter":
            if p.submit():
                cb = p.callback; vals = p.values[:]
                self.prompt = None; self.status = _HINT; cb(vals)
        elif k == "backspace":
            p.buf = p.buf[:-1]
        elif ch and ch.isprintable():
            p.buf += ch

    def _prompt(self, steps: list[str], cb: Callable[[list[str]], None],
                defaults: Optional[list[str]] = None) -> None:
        self.prompt = Prompt(steps=steps, defaults=defaults or [""] * len(steps),
                             values=[], step=0, buf="", callback=cb)

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_mouse_down(self, event: events.MouseDown) -> None:
        cell = self._mouse_to_cell(event.x, event.y)
        if cell is None: return
        abs_step, ci = cell
        if self.grabbed is not None:
            in_b = self._in_bounds(self.grabbed, abs_step, ci)
            if in_b:
                conflict = self._has_conflict(self.grabbed, abs_step, ci)
                self.grabbed.row = abs_step / self.settings.height_steps
                self.grabbed.col = ci
                msg = "  Placed (overlapping — :check to review)" if conflict else "  Placed."
                self.status = msg; self.status_err = False
                self._invalidate_conflicts()
                self.grabbed = None
            else:
                self.status = "  ✗ Out of bounds."; self.status_err = True
        else:
            block = self._block_at(abs_step, ci)
            if block:
                self.grabbed    = block
                self.cursor_row = abs_step
                self.cursor_col = ci
                self.status     = f"  Grabbed [{block.name}]  —  click to drop"
                self.status_err = False
        self._scroll_to_cursor()
        self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.grabbed is None: return
        cell = self._mouse_to_cell(event.x, event.y)
        if cell is None: return
        self.cursor_row, self.cursor_col = cell
        self._scroll_to_cursor()
        self.refresh()

    def _mouse_to_cell(self, x: int, y: int) -> Optional[tuple[int, int]]:
        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        H, hs, nr = self.size.height, self.settings.height_steps, len(self.table.rows)
        if y == 0 or y == H - 1: return None
        body_y = y - 1
        step_in_view = body_y // step_h
        abs_step     = self.view_row_off + step_in_view
        if step_in_view >= n_vis_s or abs_step >= nr * hs: return None
        if x < row_lw: return None
        cx = x - row_lw
        for i, ci in enumerate(vis_cols):
            cx -= 1   # skip │
            if cx < 0: return abs_step, ci
            if cx < col_widths[i]: return abs_step, ci
            cx -= col_widths[i]
        return None

    # ── Vim edit ──────────────────────────────────────────────────────────────

    def _open_in_vim(self) -> None:
        if not self.filepath:
            self.status = "  No file — save with :w first"; self.status_err = True; return
        self._save()
        self.run_worker(self._vim_worker)

    async def _vim_worker(self) -> None:
        import asyncio
        editor = os.environ.get("EDITOR", "vim")
        async with self.app.suspend():
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: subprocess.run([editor, self.filepath])
            )
        try:
            table, settings = load_yaml(self.filepath)
            self.table      = table
            self.settings   = settings
            self._invalidate_conflicts()
            self.status     = f"  Reloaded from {self.filepath}"
            self.status_err = False
        except Exception as e:
            self.status     = f"  Reload error: {e}"
            self.status_err = True
        self.refresh()

    # ── Check ─────────────────────────────────────────────────────────────────

    def _cmd_check(self) -> None:
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        if not cids:
            self.status = "  ✓ No overlapping solid blocks."; self.status_err = False; return
        names = [b.name for b in self.table.blocks if id(b) in cids]
        self.status     = "  ✗ Overlapping: " + "  ↔  ".join(dict.fromkeys(names))
        self.status_err = True

    # ── Grab / drop ───────────────────────────────────────────────────────────

    def _toggle_grab(self) -> None:
        if self.grabbed is not None:
            step, ci = self.cursor_row, self.cursor_col
            if not self._in_bounds(self.grabbed, step, ci):
                self.status = "  ✗ Out of bounds."; self.status_err = True; return
            conflict = self._has_conflict(self.grabbed, step, ci)
            self.grabbed.row = step / self.settings.height_steps
            self.grabbed.col = ci
            self._invalidate_conflicts()
            if conflict:
                self.status = f"  Placed [{self.grabbed.name}] (overlapping — :check to review)"
            else:
                self.status = "  Placed."
            self.status_err = False; self.grabbed = None
        else:
            block = self._block_at(self.cursor_row, self.cursor_col)
            if block:
                self.grabbed    = block
                self.status     = f"  Grabbed [{block.name}]  │  hjkl/mouse  │  space/click drop  │  esc cancel"
                self.status_err = False
            else:
                self.status = "  No block at cursor."; self.status_err = True

    # ── Block commands ────────────────────────────────────────────────────────

    def _cmd_add_block(self) -> None:
        step, ci, hs = self.cursor_row, self.cursor_col, self.settings.height_steps
        def done(v: list[str]) -> None:
            name = v[0] or "Unnamed"
            try:    h = max(1/hs, round(float(v[1]) * hs) / hs)
            except: h = 1.0
            try:    w = max(1, int(v[2]))
            except: w = 1
            cidx = self._next_color()
            nb   = Block(name=name, height=h, width=w, row=step/hs, col=ci, color_idx=cidx)
            if self._in_bounds(nb, step, ci):
                self.table.blocks.append(nb)
                self._invalidate_conflicts()
                self.status = f"  Added: {name}"; self.status_err = False
            else:
                self.status = "  ✗ Out of bounds."; self.status_err = True
        self._prompt(["Block name", f"Height (units, min {1/hs:.3g})", "Width (cols)"], done)

    def _cmd_edit_block(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        hs = self.settings.height_steps
        def done(v: list[str]) -> None:
            block.name = v[0] or block.name
            try:    block.height = max(1/hs, round(float(v[1]) * hs) / hs)
            except: pass
            try:    block.width  = max(1, int(v[2]))
            except: pass
            self._invalidate_conflicts()
            self.status = f"  Edited: {block.name}"; self.status_err = False
        self._prompt(["Name", "Height", "Width"], done,
                     [block.name, str(block.height), str(block.width)])

    def _cmd_delete_block(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        def done(v: list[str]) -> None:
            if v[0].lower() == "y":
                self.table.blocks.remove(block)
                self._invalidate_conflicts()
                self.status = f"  Deleted: {block.name}"; self.status_err = False
            else:
                self.status = "  Cancelled."
        self._prompt([f"Delete '{block.name}'? (y/n)"], done)

    def _cmd_toggle_transparent(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        block.transparent = not block.transparent
        self._invalidate_conflicts()
        self.status = f"  {block.name} → {'transparent' if block.transparent else 'solid'}"
        self.status_err = False

    # ── Row commands ──────────────────────────────────────────────────────────

    def _cmd_add_row(self, below: bool) -> None:
        hs     = self.settings.height_steps
        unit_i = self.cursor_row // hs
        n      = len(self.table.rows)
        ref    = self.table.rows[min(unit_i, n - 1)]
        ins    = unit_i + (1 if below else 0)
        def done(v: list[str]) -> None:
            label = v[0] or f"Row {ins + 1}"
            self.table.rows.insert(ins, label)
            for b in self.table.blocks:
                if b.row >= ins: b.row += 1.0
            if not below:
                self.cursor_row = min(self.cursor_row + hs, len(self.table.rows) * hs - 1)
            self._invalidate_conflicts()
            self.status = f"  Added row: {label}"; self.status_err = False
        self._prompt([f"Label ({'after' if below else 'before'} '{ref}')"], done)

    def _cmd_delete_row(self) -> None:
        hs     = self.settings.height_steps
        unit_i = self.cursor_row // hs
        if len(self.table.rows) <= 1:
            self.status = "  Cannot delete last row."; self.status_err = True; return
        label = self.table.rows[unit_i]
        def done(v: list[str]) -> None:
            if v[0].lower() != "y": self.status = "  Cancelled."; return
            self.table.rows.pop(unit_i)
            keep = []
            for b in self.table.blocks:
                if b.row < unit_i + 1 and b.row + b.height > unit_i: continue
                if b.row >= unit_i + 1: b.row -= 1.0
                keep.append(b)
            self.table.blocks = keep
            self.cursor_row   = min(self.cursor_row, len(self.table.rows) * hs - 1)
            self._invalidate_conflicts()
            self.status = f"  Deleted row: {label}"; self.status_err = False
        self._prompt([f"Delete row '{label}'? (y/n)"], done)

    # ── Column commands ───────────────────────────────────────────────────────

    def _cmd_add_col(self, right: bool) -> None:
        ci   = self.cursor_col
        nc   = len(self.table.columns)
        ref  = self.table.columns[min(ci, nc - 1)]
        ins  = ci + (1 if right else 0)
        def done(v: list[str]) -> None:
            label = v[0] or f"Col {ins + 1}"
            self.table.columns.insert(ins, label)
            for b in self.table.blocks:
                if b.col >= ins: b.col += 1
            if not right:
                self.cursor_col = min(self.cursor_col + 1, len(self.table.columns) - 1)
            self._invalidate_conflicts()
            self.status = f"  Added column: {label}"; self.status_err = False
        self._prompt([f"Label ({'right of' if right else 'left of'} '{ref}')"], done)

    def _cmd_delete_col(self) -> None:
        ci = self.cursor_col
        if len(self.table.columns) <= 1:
            self.status = "  Cannot delete last column."; self.status_err = True; return
        label = self.table.columns[ci]
        def done(v: list[str]) -> None:
            if v[0].lower() != "y": self.status = "  Cancelled."; return
            self.table.columns.pop(ci)
            keep = []
            for b in self.table.blocks:
                if b.col > ci:
                    b.col -= 1; keep.append(b)
                elif b.col <= ci < b.col + b.width:
                    b.width -= 1
                    if b.width >= 1: keep.append(b)
                else:
                    keep.append(b)
            self.table.blocks = keep
            self.cursor_col   = min(self.cursor_col, len(self.table.columns) - 1)
            self._invalidate_conflicts()
            self.status = f"  Deleted column: {label}"; self.status_err = False
        self._prompt([f"Delete column '{label}'? (y/n)"], done)


# ─────────────────────────────────────────────────────────────────────────────
#  Application
# ─────────────────────────────────────────────────────────────────────────────

class TablePlanApp(App):
    CSS = "Screen { background: $surface; } GridWidget { width: 100%; height: 100%; }"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, table: TableData, settings: Settings, filepath: Optional[str]) -> None:
        super().__init__()
        self._table    = table
        self._settings = settings
        self._filepath = filepath

    def compose(self) -> ComposeResult:
        yield GridWidget(self._table, self._settings, self._filepath)

    def on_mount(self) -> None:
        self.title = f"tableplan — {self._filepath}" if self._filepath else "tableplan (demo)"
        self.query_one(GridWidget).focus()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    filepath: Optional[str] = sys.argv[1] if len(sys.argv) > 1 else None
    if filepath and os.path.exists(filepath):
        table, settings = load_yaml(filepath)
    else:
        table, settings = _demo_table()
        if filepath:
            save_yaml(filepath, table, settings)
    TablePlanApp(table, settings, filepath).run()


if __name__ == "__main__":
    main()
