#!/usr/bin/env python3
"""
tableplan v0.7  —  vim-style terminal table organizer

Usage:
    python tableplan.py              # in-memory demo
    python tableplan.py myplan.yaml  # load or create YAML file
"""
from __future__ import annotations

import copy, math, os, subprocess, sys, textwrap
from dataclasses import dataclass, field
from typing import Callable, Optional

import yaml
from textual import events
from textual.app import App, ComposeResult, Screen
from textual.strip import Strip
from textual.widget import Widget
from textual.widgets import Static
from rich.segment import Segment
from rich.style import Style


# ─────────────────────────────────────────────────────────────────────────────
#  Colour palette
# ─────────────────────────────────────────────────────────────────────────────

_PALETTE: list[tuple[str, str]] = [
    ("green",           "black"),   # 0
    ("blue",            "white"),   # 1
    ("dark_magenta",    "white"),   # 2
    ("dark_cyan",       "black"),   # 3
    ("red3",            "white"),   # 4
    ("yellow",          "black"),   # 5
    ("spring_green2",   "black"),   # 6
    ("dark_blue",       "white"),   # 7
    ("magenta",         "black"),   # 8
    ("cyan",            "black"),   # 9
    ("orange3",         "black"),   # a
    ("purple",          "white"),   # b
    ("deep_sky_blue3",  "black"),   # c
    ("chartreuse3",     "black"),   # d
    ("hot_pink3",       "black"),   # e
    ("gold3",           "black"),   # f
    ("steel_blue",      "white"),   # g
    ("dark_olive_green3","black"),  # h
    ("indian_red",      "white"),   # i
    ("slate_blue1",     "white"),   # j
    ("turquoise2",      "black"),   # k
    ("rosy_brown",      "white"),   # l
]
_PAL_KEYS = "0123456789abcdefghijkl"

def _solid(ci: int) -> Style:
    bg, fg = _PALETTE[ci % len(_PALETTE)]; return Style(bgcolor=bg, color=fg, bold=True)
def _dim(ci: int) -> Style:
    bg, _  = _PALETTE[ci % len(_PALETTE)]; return Style(bgcolor=bg, color="bright_black")
def _cursor_on(ci: int) -> Style:
    bg, fg = _PALETTE[ci % len(_PALETTE)]
    return Style(bgcolor="white", color=bg, bold=True, underline=True)
def _selected_style(ci: int) -> Style:
    bg, fg = _PALETTE[ci % len(_PALETTE)]
    return Style(bgcolor=bg, color=fg, bold=True, underline=True, overline=True)
def _group_style(ci: int) -> Style:
    bg, fg = _PALETTE[ci % len(_PALETTE)]
    return Style(bgcolor=bg, color=fg, bold=True, italic=True)

S_CONFLICT = Style(bgcolor="red",         color="bright_white", bold=True)
S_GHOST_OK = Style(bgcolor="yellow",      color="black")
S_GHOST_CF = Style(bgcolor="dark_orange3",color="white")
S_GHOST_OB = Style(bgcolor="red",         color="white")
S_BORDER   = Style(color="bright_black")
S_HEADER   = Style(color="cyan", bold=True)
S_LABEL    = Style(color="white")
S_CURSOR   = Style(bgcolor="blue",color="white", bold=True)
S_EMPTY    = Style()
S_STATUS   = Style(color="bright_white")
S_ERR      = Style(color="red",  bold=True)
S_SEARCH   = Style(bgcolor="bright_yellow", color="black", bold=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    name:        str
    height:      float          # row units; multiples of 1/height_steps
    width:       int            # column steps (multiples of 1/width_steps)
    row:         float          # top-left in row units
    col:         float          # top-left in column step units
    transparent: bool           = False
    color_idx:   int            = 0
    group:       Optional[str]  = None   # group name (None = ungrouped)


@dataclass
class TableData:
    name:    str
    columns: list[str]
    rows:    list[str]
    blocks:  list[Block] = field(default_factory=list)


@dataclass
class Settings:
    height_steps:     int           = 2
    width_steps:      int           = 1
    zoom_h:           float         = 1.0
    zoom_w:           float         = 1.0
    block_wrap:       bool          = False
    transposed:       bool          = False  # axes swapped via T
    max_visible_cols: Optional[int] = None
    max_visible_rows: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
#  YAML I/O
# ─────────────────────────────────────────────────────────────────────────────

def load_yaml(path: str) -> tuple[TableData, Settings]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    t = data["table"]
    table = TableData(
        name    = str(t["name"]),
        columns = [str(c) for c in t["columns"]],
        rows    = [str(r) for r in t["rows"]],
    )
    for bd in data.get("blocks", []):
        table.blocks.append(Block(
            name        = str(bd["name"]),
            height      = float(bd.get("height", 1.0)),
            width       = int(bd.get("width",  1)),
            row         = float(bd.get("row",   0.0)),
            col         = float(bd.get("col",   0.0)),
            transparent = bool(bd.get("transparent", False)),
            color_idx   = int(bd.get("color_idx",  0)),
            group       = bd.get("group") or None,
        ))
    sd = data.get("settings", {})
    return table, Settings(
        height_steps    =int(sd.get("height_steps", 2)),
        width_steps     =int(sd.get("width_steps",  1)),
        zoom_h          =float(sd.get("zoom_h", 1.0)),
        zoom_w          =float(sd.get("zoom_w", 1.0)),
        block_wrap      =bool(sd.get("block_wrap", False)),
        transposed      =bool(sd.get("transposed", False)),
        max_visible_cols=sd.get("max_visible_cols"),
        max_visible_rows=sd.get("max_visible_rows"),
    )


def save_yaml(path: str, table: TableData, settings: Settings) -> None:
    sd = {k: v for k, v in {
        "height_steps": settings.height_steps,
        "width_steps":  settings.width_steps,
        "zoom_h":  settings.zoom_h,  "zoom_w": settings.zoom_w,
        "block_wrap": settings.block_wrap,
        "transposed": settings.transposed,
        "max_visible_cols": settings.max_visible_cols,
        "max_visible_rows": settings.max_visible_rows,
    }.items() if v is not None}
    blocks_data = []
    for b in table.blocks:
        bd = {"name": b.name, "height": b.height, "width": b.width,
              "row": b.row, "col": b.col, "transparent": b.transparent,
              "color_idx": b.color_idx}
        if b.group: bd["group"] = b.group
        blocks_data.append(bd)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({
            "table": {"name": str(table.name),
                      "columns": [str(c) for c in table.columns],
                      "rows":    [str(r) for r in table.rows]},
            "settings": sd, "blocks": blocks_data,
        }, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _demo_table() -> tuple[TableData, Settings]:
    return TableData(
        name="Weekly Schedule",
        columns=["Monday","Tuesday","Wednesday","Thursday","Friday"],
        rows=["8:00am","9:00am","10:00am","11:00am","12:00pm"],
        blocks=[
            Block("Dog Walk",  0.5,1,0.0,0,color_idx=0),
            Block("Standup",   0.5,5,1.0,0,color_idx=1),
            Block("Deep Work", 2.0,2,2.0,2,color_idx=2),
            Block("Lunch",     1.0,1,4.0,1,color_idx=3),
        ],
    ), Settings()


# ─────────────────────────────────────────────────────────────────────────────
#  Help
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
#  Shelf picker screen
# ─────────────────────────────────────────────────────────────────────────────

class ShelfScreen(Screen):
    """Vertical vim-register-style shelf overlay. Press 0-9 to pick, Esc cancel."""
    CSS = """
    ShelfScreen         { align: center middle; background: rgba(0,0,0,0.85); }
    ShelfScreen Static  { background: #1e2030; padding: 1 3; border: round cyan;
                          width: 62; height: auto; }
    """

    def __init__(self, shelf: list, callback) -> None:
        super().__init__()
        self._shelf    = shelf
        self._callback = callback

    def compose(self) -> ComposeResult:
        lines = ["  ── Shelf ─────────────────────────────────────", ""]
        for i, entry in enumerate(self._shelf[:10]):
            names = ", ".join(b.name for b in entry[:4])
            if len(entry) > 4: names += f"  … +{len(entry)-4} more"
            count = f"{len(entry)} block{'s' if len(entry) != 1 else ' '}"
            lines.append(f"  {i}  [{count:9s}]  {names}")
        lines += ["", "  Press 0–9 to place  •  Esc to cancel"]
        yield Static("\n".join(lines))

    def on_key(self, event: events.Key) -> None:
        ch = event.character or ""
        if event.key == "escape":
            self.app.pop_screen()
        elif ch.isdigit():
            idx = int(ch)
            if 0 <= idx < len(self._shelf):
                self.app.pop_screen()
                self._callback(idx)


HELP_TEXT = """\
╔══════════════════════════════════════════════════════════════════════╗
║                    tableplan  v0.7  —  controls                      ║
╠════════════════════════════════╦═════════════════════════════════════╣
║  NAVIGATION                    ║  BLOCKS                             ║
║  h/l      left/right           ║  space    grab / drop               ║
║  j/k      down/up              ║  a        add new block             ║
║  (scrolls automatically)       ║  e        edit block (resize)       ║
╠════════════════════════════════║  E        rename block              ║
║  SIZING MODE  (after a / e)    ║  x        delete block              ║
║  l / h    wider / narrower     ║  v        toggle transparent        ║
║  j / k    taller / shorter     ║  y        yank (copy)               ║
║  H/J/K/L  move anchor          ║  p        paste copy                ║
║  Enter    confirm              ║  c        change colour             ║
║  Esc      cancel               ╠═════════════════════════════════════╣
╠════════════════════════════════║  GROUPS & SHELF                     ║
║  ZOOM                          ║  g        group selected blocks     ║
║  + / -    zoom all             ║  G        ungroup current group     ║
║  [ / ]    zoom width only      ║  s        send to shelf             ║
║  { / }    zoom height only     ║  S        pull from shelf           ║
╠════════════════════════════════╠═════════════════════════════════════╣
║  SEARCH                        ║  MULTI-SELECT                       ║
║  /        search blocks        ║  V        visual mode (auto-sel.)   ║
║  n / N    next / prev match    ║  hjkl     move + paint select       ║
╠════════════════════════════════║  space    grab selection            ║
║  UNDO / REDO                   ║  Esc      exit visual mode          ║
║  u        undo                 ╠═════════════════════════════════════╣
║  R        redo                 ║  ROWS & COLUMNS                     ║
╠════════════════════════════════║  o/O      add row below/above       ║
║  COMMANDS                      ║  i/I      add col left/right        ║
║  :w / :q / ZZ / "  / ?         ║  d        delete row                ║
║  :set home   reset zoom/view   ║  D        delete column             ║
║  :set wrap / nowrap            ╠═════════════════════════════════════╣
║  :set transpose  swap axes     ║  MOUSE                              ║
║  :set width N   visible cols   ║  click    grab/drop block           ║
║  :set height N  visible rows   ║  drag     move while held           ║
║  :set tolerance H [W]          ║  scroll   vertical scroll           ║
║  :set zoom h/w N.N             ║  shift+scroll  horizontal scroll    ║
║  :flash   reveal hidden blocks ║  Overlap → always solid red         ║
║  :check   list overlapping     ║  :check   list overlapping blocks   ║
╚════════════════════════════════╩═════════════════════════════════════╝
  Press any key to close."""


class HelpScreen(Screen):
    CSS = "Screen{align:center middle;}Static{width:auto;}"
    def compose(self) -> ComposeResult: yield Static(HELP_TEXT)
    def on_key(self, _: events.Key) -> None: self.app.pop_screen()


# ─────────────────────────────────────────────────────────────────────────────
#  Inline prompt
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
#  Modes
# ─────────────────────────────────────────────────────────────────────────────

MODE_NORMAL = "normal"
MODE_GRAB   = "grab"
MODE_MGRB   = "multi_grab"
MODE_VISUAL = "visual"
MODE_SIZING = "sizing"
MODE_COLOR  = "color"
MODE_FLASH  = "flash"
MODE_CMD    = "cmd"
MODE_PROMPT = "prompt"

_CMD_COMPLETIONS = sorted([
    ":check", ":export ", ":flash", ":noh", ":q", ":q!", ":w", ":wq", ":x",
    ":set home", ":set nowrap", ":set transpose", ":set wrap",
    ":set width ", ":set height ", ":set tolerance ", ":set zoom h ",
    ":set zoom w ",
])

_HINT = ("  hjkl:move  spc:grab  a:add  e:edit  E:rename  x:del  /:search  "
         "v:transp  V:visual  g:group  G:ungrp  s:shelf  S:pull  "
         "y:yank  p:paste  c:color  f:flash  T:transpose  u:undo  r:redo  "
         "o/O:row  i/I:col  d/D:del  +/-:zoom  [/]:W-zoom  {/}:H-zoom  "
         "\":vim  ?:help  ZZ/:w:save")


# ─────────────────────────────────────────────────────────────────────────────
#  Text-wrap helper
# ─────────────────────────────────────────────────────────────────────────────

def _wrap_label(name: str, cell_w: int, n_lines: int) -> list[str]:
    """Word-wrap 'name' into lines of width cell_w.
    Returns a list of strings centred in n_lines (blank-padded)."""
    if cell_w <= 0: return [""] * n_lines
    words = name.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if not cur:
            cur = w[:cell_w]
        elif len(cur) + 1 + len(w) <= cell_w:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w[:cell_w]
    if cur: lines.append(cur)
    if not lines: lines = [""]
    # Vertical centre inside n_lines
    result: list[str] = [""] * n_lines
    start = max(0, (n_lines - len(lines)) // 2)
    for i, l in enumerate(lines):
        if start + i < n_lines:
            result[start + i] = l
    return result


# ─────────────────────────────────────────────────────────────────────────────
#  Grid widget
# ─────────────────────────────────────────────────────────────────────────────

class GridWidget(Widget):
    can_focus = True

    def __init__(self, table: TableData, settings: Settings,
                 filepath: Optional[str]) -> None:
        super().__init__()
        self.table        = table
        self.settings     = settings
        self.filepath     = filepath
        # Cursor / viewport
        self.cursor_row   = 0   # absolute row-steps
        self.cursor_col   = 0   # absolute col-steps
        self.view_row_off = 0
        self.view_col_off = 0
        # Modes
        self.mode         = MODE_NORMAL
        self.flash_mode   = False
        # Single grab
        self.grabbed:          Optional[Block] = None
        self.grab_offset_row:  int             = 0
        self.grab_offset_col:  int             = 0
        # Multi-grab
        self.grabbed_group: list[Block]           = []
        self.grp_offsets:   list[tuple[int,int]]  = []
        # Visual / select
        self.selected_ids: set[int] = set()
        # Sizing
        self.sizing_block:  Optional[Block] = None
        self.sizing_target: Optional[Block] = None
        # Colour picker
        self.color_block: Optional[Block] = None
        # Clipboard
        self.clipboard: Optional[list[Block]] = None  # list for group yank
        # Shelf  — each entry is a list of blocks (possibly grouped)
        self.shelf: list[list[Block]] = []
        self._shelf_pick_mode: bool = False
        # Search
        self._search_matches: list[Block] = []
        self._search_idx:     int         = 0
        self._search_query:   str         = ""
        # Prompt
        self.prompt: Optional[Prompt] = None
        # Command
        self.cmd_buf         = ""
        self._in_tab_cycle   = False
        self._tab_candidates: list[str] = []
        self._tab_idx        = 0
        # Undo / redo — each entry: {"blocks": ..., "rows": ..., "cols": ...}
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        # Status
        self.status     = _HINT
        self.status_err = False
        self.last_key   = ""
        # Conflict cache
        self._conflict_set: set[int] = set()
        self._conflict_dirty         = True
        # Layout cache
        self._step_h      = 1
        self._row_lw      = 8
        self._col_widths: list[int] = []
        self._vis_cols:   list[int] = []
        self._n_vis_steps = 1

    # ── Undo helpers ──────────────────────────────────────────────────────────

    def _snapshot(self) -> None:
        snap = {
            "blocks":  copy.deepcopy(self.table.blocks),
            "rows":    list(self.table.rows),
            "columns": list(self.table.columns),
        }
        self._undo_stack.append(snap)
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def _undo(self) -> None:
        if not self._undo_stack:
            self.status = "  Nothing to undo."; self.status_err = False; return
        redo = {"blocks": copy.deepcopy(self.table.blocks),
                "rows": list(self.table.rows), "columns": list(self.table.columns)}
        self._redo_stack.append(redo)
        snap = self._undo_stack.pop()
        self.table.blocks  = snap["blocks"]
        self.table.rows    = snap["rows"]
        self.table.columns = snap["columns"]
        self._invalidate_conflicts()
        self.status = f"  Undo ({len(self._undo_stack)} left)"; self.status_err = False

    def _redo(self) -> None:
        if not self._redo_stack:
            self.status = "  Nothing to redo."; self.status_err = False; return
        undo = {"blocks": copy.deepcopy(self.table.blocks),
                "rows": list(self.table.rows), "columns": list(self.table.columns)}
        self._undo_stack.append(undo)
        snap = self._redo_stack.pop()
        self.table.blocks  = snap["blocks"]
        self.table.rows    = snap["rows"]
        self.table.columns = snap["columns"]
        self._invalidate_conflicts()
        self.status = f"  Redo ({len(self._redo_stack)} left)"; self.status_err = False

    # ── Layout ───────────────────────────────────────────────────────────────

    def _layout(self) -> tuple[int, int, list[int], list[int], int]:
        W, H   = self.size.width, self.size.height
        n_rows = len(self.table.rows)
        n_cols = len(self.table.columns)
        s      = self.settings

        rows_s = [str(r) for r in self.table.rows]
        cols_s = [str(c) for c in self.table.columns]
        row_lw = max((len(r) for r in rows_s), default=5) + 2

        all_words: list[str] = []
        for c in cols_s: all_words += c.split()
        for b in self.table.blocks: all_words += b.name.split()
        nat_w   = max((len(w) for w in all_words), default=3) + 2
        base_cw = max(3, int(nat_w * s.zoom_w))

        avail_w   = W - row_lw - 1
        max_fit   = max(1, avail_w // (base_cw + 1))
        vis_count = min(max_fit, n_cols - self.view_col_off)
        if s.max_visible_cols is not None:
            vis_count = min(vis_count, s.max_visible_cols)
        vis_count = max(1, vis_count)
        vis_cols  = list(range(self.view_col_off,
                               min(self.view_col_off + vis_count, n_cols)))

        # Only expand columns to fill the full width when the entire table
        # is visible (no horizontal scroll). When scrolled, use natural width.
        all_cols_visible = (len(vis_cols) == n_cols)
        if all_cols_visible:
            avail_d  = max(len(vis_cols) * 3, avail_w - len(vis_cols))
            col_w    = max(3, avail_d // len(vis_cols))
            leftover = avail_d - col_w * len(vis_cols)
            col_widths = [col_w + (1 if i < leftover else 0) for i in range(len(vis_cols))]
        else:
            # Use natural width so columns don't artificially enlarge when scrolling
            col_widths = [base_cw] * len(vis_cols)

        n_steps  = max(1, n_rows * s.height_steps)
        n_vis_s  = n_steps
        if s.max_visible_rows is not None:
            n_vis_s = min(n_vis_s, s.max_visible_rows * s.height_steps)
        n_vis_s  = max(1, n_vis_s)

        avail_h  = max(1, H - 2)
        base_sh  = max(1, avail_h // n_vis_s)
        step_h   = max(1, int(base_sh * s.zoom_h))

        self._step_h      = step_h
        self._row_lw      = row_lw
        self._col_widths  = col_widths
        self._vis_cols    = vis_cols
        self._n_vis_steps = n_vis_s
        return step_h, row_lw, col_widths, vis_cols, n_vis_s

    # ── Scroll ────────────────────────────────────────────────────────────────

    def _scroll_to_cursor(self) -> None:
        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        s       = self.settings
        n_steps = max(1, len(self.table.rows) * s.height_steps)
        n_cols  = len(self.table.columns)

        self.cursor_row = max(0, min(self.cursor_row, n_steps - 1))
        self.cursor_col = max(0, min(self.cursor_col, n_cols - 1))

        if self.cursor_row < self.view_row_off:
            self.view_row_off = self.cursor_row
        elif self.cursor_row >= self.view_row_off + n_vis_s:
            self.view_row_off = self.cursor_row - n_vis_s + 1
        self.view_row_off = max(0, min(self.view_row_off, n_steps - 1))

        if self.cursor_col < self.view_col_off:
            self.view_col_off = self.cursor_col
        elif vis_cols and self.cursor_col > vis_cols[-1]:
            self.view_col_off = self.cursor_col - len(vis_cols) + 1
        self.view_col_off = max(0, min(self.view_col_off, n_cols - 1))

    def _clamp_cursor_for_grab(self) -> None:
        if self.settings.block_wrap: return
        hs = self.settings.height_steps
        nr = len(self.table.rows); nc = len(self.table.columns)
        if self.mode == MODE_GRAB and self.grabbed is not None:
            bh = round(self.grabbed.height * hs)
            bw = self.grabbed.width
            self.cursor_row = max(self.grab_offset_row,
                min((nr * hs - bh) + self.grab_offset_row, self.cursor_row))
            self.cursor_col = max(self.grab_offset_col,
                min((nc - bw) + self.grab_offset_col, self.cursor_col))
        elif self.mode == MODE_MGRB and self.grabbed_group:
            min_cr = min_cc = None; max_cr = max_cc = None
            for i, gb in enumerate(self.grabbed_group):
                ro, co = self.grp_offsets[i]
                bh = round(gb.height * hs)
                lo_r = -ro; hi_r = nr * hs - bh - ro
                lo_c = -co; hi_c = nc - gb.width - co
                if min_cr is None:
                    min_cr, max_cr, min_cc, max_cc = lo_r, hi_r, lo_c, hi_c
                else:
                    min_cr = max(min_cr, lo_r); max_cr = min(max_cr, hi_r)
                    min_cc = max(min_cc, lo_c); max_cc = min(max_cc, hi_c)
            if min_cr is not None:
                self.cursor_row = max(min_cr, min(max_cr, self.cursor_row))
                self.cursor_col = max(min_cc, min(max_cc, self.cursor_col))

    # ── Block helpers ─────────────────────────────────────────────────────────

    def _block_steps(self, b: Block) -> tuple[int, int]:
        hs = self.settings.height_steps
        return round(b.row * hs), round((b.row + b.height) * hs)

    def _block_col_steps(self, b: Block) -> tuple[int, int]:
        ws = self.settings.width_steps
        return round(float(b.col) * ws), round((float(b.col) + b.width) * ws)

    def _iter_block_cells(self, b: Block) -> list[tuple[int,int]]:
        """Return all (abs_step, col) cells for block b, respecting wrap mode and transposed flag."""
        hs = self.settings.height_steps
        nr = len(self.table.rows); nc = len(self.table.columns)
        bs, be = self._block_steps(b)
        bc = int(b.col); bw = b.width
        cells: list[tuple[int,int]] = []

        if not self.settings.block_wrap:
            for step in range(bs, be):
                for c in range(bc, bc + bw):
                    if 0 <= step < nr * hs and 0 <= c < nc:
                        cells.append((step, c))
            return cells

        if not self.settings.transposed:
            # Normal wrap: vertical overflow → next column
            rows_per_col = nr * hs
            remaining = be - bs; cur_row = bs; col_off = 0
            while remaining > 0:
                cur_col = bc + col_off
                if cur_col >= nc: break
                avail = rows_per_col - cur_row; seg = min(remaining, avail)
                for step in range(cur_row, cur_row + seg):
                    if 0 <= step < nr * hs:
                        cells.append((step, cur_col))
                remaining -= seg; cur_row = 0; col_off += 1
        else:
            # Transposed wrap: horizontal overflow → next row (left side of row below)
            cur_col = bc; row_off = 0
            remaining = bw
            while remaining > 0:
                avail = nc - cur_col; seg = min(remaining, avail)
                row_bs = bs + row_off * round(b.height * hs)
                row_be = row_bs + round(b.height * hs)
                for c in range(cur_col, cur_col + seg):
                    if 0 <= c < nc:
                        for step in range(row_bs, row_be):
                            if 0 <= step < nr * hs:
                                cells.append((step, c))
                remaining -= seg; cur_col = 0; row_off += 1
                if row_off * round(b.height * hs) + bs >= nr * hs:
                    break

        return cells

    def _all_blocks_at(self, abs_step: int, ci: int) -> list[Block]:
        """Return all blocks at (abs_step, ci), accounting for wrap."""
        skip = {id(self.grabbed), id(self.sizing_target)} | {id(g) for g in self.grabbed_group}
        solid: list[Block] = []; transp: list[Block] = []
        for b in self.table.blocks:
            if id(b) in skip: continue
            if (abs_step, ci) in set(self._iter_block_cells(b)):
                (transp if b.transparent else solid).append(b)
        return solid + transp

    def _block_at(self, abs_step: int, ci: int) -> Optional[Block]:
        blks = self._all_blocks_at(abs_step, ci)
        return blks[0] if blks else None

    def _in_bounds(self, b: Block, step: int, ci: int) -> bool:
        hs = self.settings.height_steps
        nr = len(self.table.rows); nc = len(self.table.columns)
        bh = round(b.height * hs)
        if self.settings.block_wrap:
            if not (0 <= ci < nc and 0 <= step < nr * hs):
                return False
            if not self.settings.transposed:
                rows_per_col = nr * hs
                avail_first  = rows_per_col - step
                extra         = bh - avail_first
                if extra > 0:
                    return ci + 1 + math.ceil(extra / rows_per_col) <= nc
                return True
            else:
                avail_first = nc - ci
                extra       = b.width - avail_first
                if extra > 0:
                    extra_rows = math.ceil(extra / nc)
                    row_unit   = step // hs
                    return row_unit + extra_rows < nr
                return True
        return 0 <= ci and ci + b.width <= nc and 0 <= step and step + bh <= nr * hs

    def _has_conflict(self, b: Block, step: int, ci: int) -> bool:
        """True if placing b at (step, ci) overlaps any placed solid block (wrap-aware)."""
        skip = {id(self.grabbed), id(self.sizing_target)} | {id(g) for g in self.grabbed_group}
        tmp = copy.copy(b)
        tmp.row = step / self.settings.height_steps; tmp.col = float(ci)
        tmp_cells = set(self._iter_block_cells(tmp))
        for ob in self.table.blocks:
            if id(ob) in skip or ob.transparent: continue
            if set(self._iter_block_cells(ob)) & tmp_cells:
                return True
        return False

    def _invalidate_conflicts(self) -> None:
        self._conflict_dirty = True

    def _get_conflict_ids(self) -> set[int]:
        """Return ids of all solid blocks overlapping another (wrap-aware)."""
        if not self._conflict_dirty: return self._conflict_set
        result: set[int] = set()
        solid = [b for b in self.table.blocks if not b.transparent]
        cell_sets = [set(self._iter_block_cells(b)) for b in solid]
        for i in range(len(solid)):
            for j in range(i + 1, len(solid)):
                if cell_sets[i] & cell_sets[j]:
                    result.add(id(solid[i])); result.add(id(solid[j]))
        self._conflict_set = result; self._conflict_dirty = False
        return result

    def _next_color(self) -> int:
        used = {b.color_idx for b in self.table.blocks}
        for i in range(len(_PALETTE)):
            if i not in used: return i
        return len(self.table.blocks) % len(_PALETTE)

    def _group_members(self, group_name: str) -> list[Block]:
        return [b for b in self.table.blocks if b.group == group_name]

    # ── Ghost list ────────────────────────────────────────────────────────────

    def _get_ghosts(self) -> list[tuple[Block, int, int]]:
        hs     = self.settings.height_steps
        ghosts: list[tuple[Block, int, int]] = []
        if self.mode == MODE_GRAB and self.grabbed is not None:
            ghosts.append((self.grabbed,
                           self.cursor_row - self.grab_offset_row,
                           self.cursor_col - self.grab_offset_col))
        elif self.mode == MODE_MGRB:
            for i, gb in enumerate(self.grabbed_group):
                ro, co = self.grp_offsets[i]
                ghosts.append((gb, self.cursor_row + ro, self.cursor_col + co))
        elif self.mode == MODE_SIZING and self.sizing_block is not None:
            ghosts.append((self.sizing_block, self.cursor_row, self.cursor_col))
        return ghosts

    # ── Rendering ────────────────────────────────────────────────────────────

    def _block_line_abs(self, b: Block, abs_step: int, ci: int,
                        step_h: int, line_in_step: int) -> int:
        """
        Compute the terminal-line index within a block's wrapped label,
        accounting for column wrapping when :set wrap is on.

        Without wrap: line_abs = (abs_step - bs) * step_h + line_in_step
        With wrap:    abs_step may be in a later column; compute steps already
                      consumed by earlier column segments and add them in.
        """
        hs = self.settings.height_steps
        nr = len(self.table.rows)
        bs, _ = self._block_steps(b)
        bc    = int(b.col)

        if not self.settings.block_wrap or ci == bc:
            # Normal case: block hasn't wrapped, or we're in its home column
            return (abs_step - bs) * step_h + line_in_step

        # Wrap case: figure out how many steps of the block lived in earlier columns
        rows_per_col = nr * hs
        # Steps consumed in block's home column
        avail_first  = rows_per_col - bs
        col_offset   = ci - bc
        # Steps consumed in full intermediate columns (between home and current)
        middle_steps = (col_offset - 1) * rows_per_col
        # Steps into this (current) column = abs_step (cur_row=0 for wrapped cols)
        steps_here   = abs_step
        total_offset = avail_first + middle_steps + steps_here
        return total_offset * step_h + line_in_step

    def render_line(self, y: int) -> Strip:  # noqa: C901
        if self.size.width == 0 or self.size.height == 0:
            return Strip([])
        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        n_rows = len(self.table.rows)
        H, W   = self.size.height, self.size.width
        hs     = self.settings.height_steps

        if y == H - 1: return self._render_status(W)

        if y == 0:
            cols_s = [str(c) for c in self.table.columns]
            segs: list[Segment] = [Segment(" " * row_lw, S_EMPTY)]
            for i, ci in enumerate(vis_cols):
                segs.append(Segment("│", S_BORDER))
                segs.append(Segment(cols_s[ci][:col_widths[i]].center(col_widths[i]), S_HEADER))
            segs.append(Segment("│", S_BORDER))
            used = row_lw + sum(col_widths) + len(vis_cols) + 1
            if used < W: segs.append(Segment(" " * (W - used), S_EMPTY))
            return Strip(segs)

        body_y       = y - 1
        step_in_view = body_y // step_h
        line_in_step = body_y % step_h
        abs_step     = self.view_row_off + step_in_view

        if step_in_view >= n_vis_s or abs_step >= n_rows * hs:
            return Strip([Segment(" " * W, S_EMPTY)])

        rows_s   = [str(r) for r in self.table.rows]
        unit_i   = abs_step // hs
        sub_step = abs_step % hs
        show_lbl = (sub_step == 0) and (line_in_step == 0)

        conflict_ids = self._get_conflict_ids()
        ghosts       = self._get_ghosts()
        search_ids   = {id(b) for b in self._search_matches}

        segs = []
        if show_lbl and unit_i < len(rows_s):
            segs.append(Segment(rows_s[unit_i].ljust(row_lw)[:row_lw], S_LABEL))
        else:
            segs.append(Segment(" " * row_lw, S_EMPTY))

        for i, ci in enumerate(vis_cols):
            cw        = col_widths[i]
            is_cursor = (abs_step == self.cursor_row and ci == self.cursor_col
                         and self.mode not in (MODE_GRAB, MODE_MGRB, MODE_SIZING))
            segs.append(Segment("│", S_BORDER))
            cell_done = False

            # Ghost rendering
            for ghost_block, gs, gc in ghosts:
                ge  = gs + round(ghost_block.height * hs)
                gce = gc + ghost_block.width
                if gs <= abs_step < ge and gc <= ci < gce:
                    in_b  = self._in_bounds(ghost_block, gs, gc)
                    cf    = self._has_conflict(ghost_block, gs, gc)
                    gstyle = S_GHOST_OB if not in_b else (S_GHOST_CF if cf else S_GHOST_OK)
                    n_lines  = round(ghost_block.height * hs) * step_h
                    line_abs = max(0, (abs_step - gs) * step_h + line_in_step)
                    if self.mode == MODE_SIZING:
                        sb   = self.sizing_block
                        label = f"{sb.name}  {sb.height:.3g}u\xd7{sb.width}c"
                    else:
                        label = ghost_block.name
                    wrapped = _wrap_label(label, cw, n_lines)
                    txt = wrapped[line_abs] if line_abs < len(wrapped) else ""
                    segs.append(Segment(txt[:cw].center(cw), gstyle))
                    cell_done = True; break

            if not cell_done:
                all_blks = self._all_blocks_at(abs_step, ci)
                if all_blks:
                    top = all_blks[0]; n = len(all_blks)

                    if self.flash_mode:
                        show_blk = all_blks[line_in_step % n]
                        if id(show_blk) in conflict_ids: style = S_CONFLICT
                        elif show_blk.transparent: style = _dim(show_blk.color_idx)
                        else: style = _solid(show_blk.color_idx)
                        txt = show_blk.name
                    elif n == 1:
                        bs, be = self._block_steps(top)
                        n_lines = (be - bs) * step_h
                        line_abs = self._block_line_abs(top, abs_step, ci,
                                                        step_h, line_in_step)
                        # Clamp to valid range (safety for edge cases / wrapping)
                        line_abs = max(0, min(line_abs, n_lines - 1))
                        wrapped  = _wrap_label(top.name, cw, n_lines)
                        txt = wrapped[line_abs] if 0 <= line_abs < len(wrapped) else ""
                        if id(top) in search_ids: style = S_SEARCH
                        elif is_cursor:            style = _cursor_on(top.color_idx)
                        elif id(top) in self.selected_ids: style = _selected_style(top.color_idx)
                        elif top.transparent:      style = _dim(top.color_idx)
                        elif top.group:            style = (_solid(top.color_idx) if id(top) not in conflict_ids
                                                            else S_CONFLICT)
                        elif id(top) in conflict_ids: style = S_CONFLICT
                        else:                      style = _solid(top.color_idx)
                    else:
                        # Multiple overlapping — stripe names per line
                        show_blk = all_blks[line_in_step % n]
                        pfx = "►" if id(show_blk) in self.selected_ids else ""
                        txt = (pfx + show_blk.name) if line_in_step < n else ""
                        if is_cursor:                    style = _cursor_on(top.color_idx)
                        elif id(top) in self.selected_ids: style = _selected_style(top.color_idx)
                        elif id(top) in conflict_ids:    style = S_CONFLICT
                        elif top.transparent:            style = _dim(top.color_idx)
                        else:                            style = _solid(top.color_idx)

                    if id(top) in self.selected_ids and n == 1:
                        pfx = "►"; txt = pfx + txt.lstrip()
                    segs.append(Segment(txt[:cw].center(cw), style))
                else:
                    style = S_CURSOR if is_cursor else S_EMPTY
                    segs.append(Segment(" " * cw, style))

        segs.append(Segment("│", S_BORDER))
        used = row_lw + sum(col_widths) + len(vis_cols) + 1
        if used < W: segs.append(Segment(" " * (W - used), S_EMPTY))
        return Strip(segs)

    def _render_status(self, W: int) -> Strip:
        if self._shelf_pick_mode:
            segs = self._render_shelf_picker(W)
            return Strip(segs)
        if self.flash_mode:
            nc = len(self._get_conflict_ids())
            msg = (f"  ◼ FLASH — {len(self.table.blocks)} blocks  "
                   f"{'⚠ ' + str(nc//2) + ' overlap pairs' if nc else '✓ no overlaps'}  "
                   f"│  f/Esc exit")
            return Strip([Segment(msg.ljust(W)[:W],
                                  Style(bgcolor="dark_red", color="bright_white", bold=True))])
        if self.mode == MODE_COLOR and self.color_block is not None:
            segs: list[Segment] = [Segment("  Colour: ", S_STATUS)]
            for i, (bg, fg) in enumerate(_PALETTE):
                key = _PAL_KEYS[i]
                cur = "►" if i == self.color_block.color_idx else " "
                segs.append(Segment(f"{cur}{key}", Style(bgcolor=bg, color=fg, bold=True)))
                segs.append(Segment(" ", S_EMPTY))
            segs.append(Segment("  press key  Esc cancel", S_STATUS))
            return Strip(segs)
        if self.mode == MODE_PROMPT and self.prompt is not None:
            return Strip([Segment(self.prompt.display().ljust(W)[:W], S_STATUS)])
        if self.mode == MODE_CMD:
            return Strip([Segment(self.cmd_buf.ljust(W)[:W], S_STATUS)])
        if self.mode == MODE_SIZING and self.sizing_block is not None:
            sb  = self.sizing_block
            msg = (f"  SIZING [{sb.name}]  h:{sb.height:.3g}u  w:{sb.width}col  │  "
                   f"j/k height  l/h width  H/J/K/L anchor  Enter confirm  Esc cancel")
            return Strip([Segment(msg.ljust(W)[:W], S_STATUS)])
        if self.mode == MODE_GRAB:
            name = self.grabbed.name if self.grabbed else "?"
            cids = self._get_conflict_ids()
            extra = "  ⚠ OVERLAP" if id(self.grabbed) in cids else ""
            msg  = f"  GRAB [{name}]  hjkl/mouse move  space/click drop  Esc cancel{extra}"
            return Strip([Segment(msg.ljust(W)[:W], S_STATUS)])
        if self.mode == MODE_MGRB:
            n   = len(self.grabbed_group)
            msg = f"  MULTI-GRAB [{n} blocks]  hjkl move  space drop  Esc cancel"
            return Strip([Segment(msg.ljust(W)[:W], S_STATUS)])
        if self.mode == MODE_VISUAL:
            n   = len(self.selected_ids)
            msg = (f"  VISUAL  {n} selected  hjkl move+select  space grab-all  "
                   f"g group  Esc exit")
            return Strip([Segment(msg.ljust(W)[:W], S_STATUS)])

        cids = self._get_conflict_ids()
        shelf_note = f"  [shelf:{len(self.shelf)}]" if self.shelf else ""
        search_note = f"  search:'{self._search_query}'" if self._search_query else ""
        overlap_note = "  ⚠ OVERLAPPING" if cids else ""
        style = S_ERR if (self.status_err or cids) else S_STATUS
        txt   = (self.status + shelf_note + search_note + overlap_note).ljust(W)[:W]
        return Strip([Segment(txt, style)])

    # ── Input dispatch ────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        # Shelf pick mode — intercept digit/escape keys
        if self._shelf_pick_mode:
            k = event.key; ch = event.character or ""
            if k == "escape":
                self._shelf_pick_mode = False; self.status = _HINT
                self.refresh(); return
            if ch and ch.isdigit():
                idx = int(ch)
                self._shelf_pick_mode = False
                if 0 <= idx < len(self.shelf):
                    self._shelf_place(idx)
                else:
                    self.status = f"  No shelf item {idx}."; self.status_err = True
                self.refresh(); return
            self.refresh(); return
        if self.flash_mode and event.key == "escape":
            self.flash_mode = False; self.status = _HINT; self.status_err = False
            self._scroll_to_cursor(); self.refresh(); return
        if   self.mode == MODE_PROMPT: self._key_prompt(event)
        elif self.mode == MODE_CMD:    self._key_cmd(event)
        elif self.mode == MODE_SIZING: self._key_sizing(event)
        elif self.mode == MODE_COLOR:  self._key_color(event)
        elif self.mode == MODE_VISUAL: self._key_visual(event)
        else:                          self._key_normal(event)
        self._clamp_cursor_for_grab()
        self._scroll_to_cursor()
        self.refresh()

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        if event.shift:
            self.view_col_off = min(self.view_col_off + 1,
                                    max(0, len(self.table.columns) - 1))
        else:
            n_steps = max(1, len(self.table.rows) * self.settings.height_steps)
            self.view_row_off = min(self.view_row_off + 1, n_steps - 1)
        self.refresh()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        if event.shift:
            self.view_col_off = max(0, self.view_col_off - 1)
        else:
            self.view_row_off = max(0, self.view_row_off - 1)
        self.refresh()

    # ── Normal / grab / multi-grab ────────────────────────────────────────────

    def _key_normal(self, event: events.Key) -> None:  # noqa: C901
        k  = event.key; ch = event.character or ""
        s  = self.settings
        nc = len(self.table.columns)
        nr = len(self.table.rows)
        ns = nr * s.height_steps

        # ZZ
        if ch == "Z":
            if self.last_key == "Z":
                self._save(); self.app.exit(); return
            self.last_key = "Z"; return
        self.last_key = k

        # Movement
        if k == "h":
            self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "l":
            self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "j":
            self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif k == "k":
            self.cursor_row = max(0, self.cursor_row - 1)
        # Grab / drop / cancel
        elif k == "space":
            if self.mode == MODE_GRAB:        self._drop_single()
            elif self.mode == MODE_MGRB:      self._drop_multi()
            elif self.selected_ids:           self._start_multi_grab()
            else:                             self._pickup_single()
        elif k == "escape":
            if self.mode == MODE_GRAB:
                self.table.blocks.append(self.grabbed)
                self.grabbed = None; self.mode = MODE_NORMAL
                self.status = "  Grab cancelled."; self.status_err = False
            elif self.mode == MODE_MGRB:
                for b in self.grabbed_group: self.table.blocks.append(b)
                self.grabbed_group = []; self.grp_offsets = []
                self.mode = MODE_NORMAL; self.status = "  Multi-grab cancelled."
            self.selected_ids.clear()
        # Escape also exits flash
        elif k == "escape" and self.flash_mode:
            self.flash_mode = False; self.status = _HINT
        # Block ops (NORMAL only)
        elif self.mode == MODE_NORMAL:
            if   k == "a": self._cmd_start_sizing(new=True)
            elif k == "e": self._cmd_start_sizing(new=False)
            elif ch == "E": self._cmd_rename_block()
            elif k == "x": self._cmd_delete_block()
            elif k == "v": self._cmd_toggle_transparent()
            elif k == "y": self._cmd_yank()
            elif k == "p": self._cmd_paste()
            elif k == "c": self._cmd_color_pick()
            elif k == "f": self._cmd_toggle_flash()
            elif ch == "T": self._cmd_transpose()
            elif ch == "V": self._enter_visual_mode()
            elif k == "g" or ch == "g": self._cmd_group()
            elif ch == "G": self._cmd_ungroup()
            elif k == "s" or ch == "s": self._cmd_shelf_send()
            elif ch == "S": self._cmd_shelf_pull()
            elif k == "u": self._undo()
            elif k == "r": self._redo()
            elif k == "slash" or ch == "/": self._cmd_search_start()
            elif k == "n": self._cmd_search_next(forward=True)
            elif ch == "N": self._cmd_search_next(forward=False)
            elif k == "z": self._cmd_clear_search()
            elif k == "o": self._cmd_add_row(below=True)
            elif k == "O": self._cmd_add_row(below=False)
            elif k == "d": self._cmd_delete_row()
            elif k == "i": self._cmd_add_col(right=False)
            elif k == "I": self._cmd_add_col(right=True)
            elif k == "D": self._cmd_delete_col()
            elif k == "minus" or ch == "-":
                s.zoom_h = max(0.25, round(s.zoom_h - 0.25, 2))
                s.zoom_w = max(0.25, round(s.zoom_w - 0.25, 2))
                self.status = f"  Zoom {s.zoom_h:.2f}\xd7"
            elif ch in ("+", "="):
                s.zoom_h = min(8.0, round(s.zoom_h + 0.25, 2))
                s.zoom_w = min(8.0, round(s.zoom_w + 0.25, 2))
                self.status = f"  Zoom {s.zoom_h:.2f}\xd7"
            elif ch == "[":
                s.zoom_w = max(0.25, round(s.zoom_w - 0.25, 2))
                self.status = f"  Zoom W:{s.zoom_w:.2f}\xd7"
            elif ch == "]":
                s.zoom_w = min(8.0, round(s.zoom_w + 0.25, 2))
                self.status = f"  Zoom W:{s.zoom_w:.2f}\xd7"
            elif ch == "{":
                s.zoom_h = max(0.25, round(s.zoom_h - 0.25, 2))
                self.status = f"  Zoom H:{s.zoom_h:.2f}\xd7"
            elif ch == "}":
                s.zoom_h = min(8.0, round(s.zoom_h + 0.25, 2))
                self.status = f"  Zoom H:{s.zoom_h:.2f}\xd7"
            elif ch == '"': self._open_in_vim()
            elif k == "question_mark" or ch == "?":
                self.app.push_screen(HelpScreen())
            elif k == "colon" or ch == ":":
                self.mode = MODE_CMD; self.cmd_buf = ":"
                self._in_tab_cycle = False

    # ── Visual mode ───────────────────────────────────────────────────────────

    def _enter_visual_mode(self) -> None:
        self.mode = MODE_VISUAL
        # Auto-select block under cursor
        block = self._block_at(self.cursor_row, self.cursor_col)
        if block: self.selected_ids.add(id(block))
        self.status = "  Visual selection — hjkl to extend  space grab  g group  Esc exit"

    def _key_visual(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        nc = len(self.table.columns)
        nr = len(self.table.rows)
        ns = nr * self.settings.height_steps

        if k == "h":   self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "l": self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "j": self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif k == "k": self.cursor_row = max(0, self.cursor_row - 1)
        elif k == "space" and self.selected_ids:
            self._start_multi_grab(); return
        elif k == "g" or ch == "g": self._cmd_group(); return
        elif k == "escape" or ch == "V":
            self.selected_ids.clear(); self.mode = MODE_NORMAL
            self.status = "  Selection cleared."; self.status_err = False; return

        # Paint block at current position
        block = self._block_at(self.cursor_row, self.cursor_col)
        if block: self.selected_ids.add(id(block))

    # ── Command mode ──────────────────────────────────────────────────────────

    def _key_cmd(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        if k == "tab":
            self._do_tab_complete(); return
        self._in_tab_cycle = False
        if k == "escape":
            self.mode = MODE_NORMAL; self.cmd_buf = ""; self.status = _HINT
        elif k == "enter":
            self._exec_cmd(); self.mode = MODE_NORMAL; self.cmd_buf = ""
        elif k == "backspace":
            self.cmd_buf = self.cmd_buf[:-1]
            if not self.cmd_buf: self.mode = MODE_NORMAL
        elif ch and ch.isprintable():
            self.cmd_buf += ch

    def _do_tab_complete(self) -> None:
        if not self._in_tab_cycle:
            prefix = self.cmd_buf
            self._tab_candidates = [c for c in _CMD_COMPLETIONS if c.startswith(prefix)]
            self._tab_idx = 0; self._in_tab_cycle = True
        if self._tab_candidates:
            self.cmd_buf = self._tab_candidates[self._tab_idx % len(self._tab_candidates)]
            self._tab_idx += 1

    def _exec_cmd(self) -> None:  # noqa: C901
        raw = self.cmd_buf.strip(); parts = raw.split(); s = self.settings
        if raw in (":q",":wq",":x"):    self._save(); self.app.exit(); return
        if raw == ":q!":                 self.app.exit(); return
        if raw == ":w":
            self._save(); self.status = f"  Saved \u2192 {self.filepath or '(no file)'}"; return
        if raw == ":check":              self._cmd_check(); return
        if raw.startswith(":export"):     self._cmd_export(parts); return
        if raw == ":noh":               self._cmd_clear_search(); return
        if raw == ":flash":              self._cmd_toggle_flash(); return
        if raw == ":set transpose":      self._cmd_transpose(); return
        if raw == ":set wrap":
            s.block_wrap = True; self.status = "  Block wrap ON"; return
        if raw == ":set nowrap":
            s.block_wrap = False; self.status = "  Block wrap OFF"; return
        if raw == ":set home":
            s.zoom_h = 1.0; s.zoom_w = 1.0
            s.max_visible_cols = None; s.max_visible_rows = None
            self.view_row_off = 0; self.view_col_off = 0
            self.status = "  Home: zoom reset"; return
        # :set zoom h/w N.N
        if len(parts) == 4 and parts[0] == ":set" and parts[1] == "zoom":
            try: val = float(parts[3])
            except ValueError:
                self.status = f"  Bad value: {parts[3]}"; self.status_err = True; return
            val = max(0.25, min(8.0, val))
            if parts[2] == "h":
                s.zoom_h = val; self.status = f"  Zoom H:{val:.2f}\xd7"; return
            if parts[2] == "w":
                s.zoom_w = val; self.status = f"  Zoom W:{val:.2f}\xd7"; return
        if len(parts) == 3 and parts[0] == ":set":
            try: val = int(parts[2])
            except ValueError:
                self.status = f"  Bad value: {parts[2]}"; self.status_err = True; return
            if parts[1] == "width":
                s.max_visible_cols = max(1, val); self.view_col_off = 0
                self.status = f"  Visible cols: {s.max_visible_cols}"; return
            if parts[1] == "height":
                s.max_visible_rows = max(1, val); self.view_row_off = 0
                self.status = f"  Visible rows: {s.max_visible_rows}"; return
            if parts[1] == "tolerance":
                up = self.cursor_row / s.height_steps
                s.height_steps = max(1, val); self.cursor_row = round(up * s.height_steps)
                self.status = f"  H-tolerance: {s.height_steps}/unit"; return
        # :set tolerance H W
        if len(parts) == 4 and parts[0] == ":set" and parts[1] == "tolerance":
            try: hs = max(1, int(parts[2])); ws = max(1, int(parts[3]))
            except ValueError:
                self.status = "  Bad values"; self.status_err = True; return
            up = self.cursor_row / s.height_steps
            s.height_steps = hs; s.width_steps = ws
            self.cursor_row = round(up * hs)
            self.status = f"  Tolerance: H={hs}/unit  W={ws}/col"; return
        self.status = f"  Unknown: {raw}"; self.status_err = True

    def _save(self) -> None:
        if self.filepath: save_yaml(self.filepath, self.table, self.settings)

    # ── Prompt mode ───────────────────────────────────────────────────────────

    def _key_prompt(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        p = self.prompt
        if p is None:
            self.mode = MODE_NORMAL; return
        if k == "escape":
            if self.sizing_target is not None and self.sizing_target not in self.table.blocks:
                self.table.blocks.append(self.sizing_target)
                self.sizing_target = None
            self.sizing_block = None
            self.prompt = None; self.mode = MODE_NORMAL
            self.status = "  Cancelled."; self.status_err = False
        elif k == "enter":
            if p.submit():
                cb = p.callback; vals = p.values[:]
                self.prompt = None; self.mode = MODE_NORMAL; self.status = _HINT
                try:
                    cb(vals)
                except Exception as exc:
                    self.status = f"  Error: {exc}"; self.status_err = True
        elif k == "backspace": p.buf = p.buf[:-1]
        elif ch and ch.isprintable(): p.buf += ch

    def _prompt(self, steps: list[str], cb: Callable,
                defaults: Optional[list[str]] = None) -> None:
        self.prompt = Prompt(steps=steps, defaults=defaults or [""] * len(steps),
                             values=[], step=0, buf="", callback=cb)
        self.mode = MODE_PROMPT

    # ── Sizing mode ───────────────────────────────────────────────────────────

    def _cmd_start_sizing(self, new: bool) -> None:
        hs = self.settings.height_steps; min_h = 1 / hs
        if new:
            cidx = self._next_color()
            self.sizing_block  = Block(name="New Block", height=min_h, width=1,
                                       row=self.cursor_row / hs, col=self.cursor_col,
                                       color_idx=cidx)
            self.sizing_target = None
            def got_name(vals: list[str]) -> None:
                self.sizing_block.name = vals[0] or "New Block"
                self.mode = MODE_SIZING
            self._prompt(["Block name (hjkl to resize, Enter to place)"], got_name)
        else:
            block = self._block_at(self.cursor_row, self.cursor_col)
            if block is None:
                self.status = "  No block at cursor."; self.status_err = True; return
            self.sizing_target = block
            self.sizing_block  = copy.copy(block)
            self.table.blocks.remove(block)
            self.cursor_row = round(block.row * hs)
            self.cursor_col = int(block.col)
            self.mode = MODE_SIZING

    def _key_sizing(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        sb = self.sizing_block; hs = self.settings.height_steps
        min_h = 1 / hs; nc = len(self.table.columns); ns = len(self.table.rows) * hs
        if k == "escape":
            if self.sizing_target is not None: self.table.blocks.append(self.sizing_target)
            self.sizing_block = None; self.sizing_target = None
            self.mode = MODE_NORMAL; self.status = "  Cancelled."; self.status_err = False
        elif k == "enter":
            step, ci = self.cursor_row, self.cursor_col
            if not self._in_bounds(sb, step, ci) and not self.settings.block_wrap:
                self.status = "  \u2717 Out of bounds."; self.status_err = True; return
            self._snapshot()
            cf = self._has_conflict(sb, step, ci)
            if self.sizing_target is not None:
                self.sizing_target.name   = sb.name
                self.sizing_target.height = sb.height
                self.sizing_target.width  = sb.width
                self.sizing_target.row    = step / hs
                self.sizing_target.col    = ci
                self.table.blocks.append(self.sizing_target)
                msg = f"  Edited: {sb.name}"
            else:
                sb.row = step / hs; sb.col = ci
                self.table.blocks.append(sb)
                msg = f"  Added: {sb.name}"
            self._invalidate_conflicts()
            if cf: msg += "  \u26a0 (overlapping)"
            self.sizing_block = None; self.sizing_target = None
            self.mode = MODE_NORMAL; self.status = msg; self.status_err = cf
        elif k == "l": sb.width = min(nc - self.cursor_col, sb.width + 1)
        elif k == "h": sb.width = max(1, sb.width - 1)
        elif k == "j": sb.height = round(sb.height + min_h, 10)
        elif k == "k": sb.height = max(min_h, round(sb.height - min_h, 10))
        elif ch == "H": self.cursor_col = max(0, self.cursor_col - 1)
        elif ch == "L": self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif ch == "J": self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif ch == "K": self.cursor_row = max(0, self.cursor_row - 1)

    # ── Colour pick ───────────────────────────────────────────────────────────

    def _cmd_color_pick(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        self.color_block = block; self.mode = MODE_COLOR

    def _key_color(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        if k == "escape":
            self.color_block = None; self.mode = MODE_NORMAL; self.status = _HINT
        elif ch and ch in _PAL_KEYS:
            self.color_block.color_idx = _PAL_KEYS.index(ch)
            self.color_block = None; self.mode = MODE_NORMAL
            self.status = "  Colour updated."; self.status_err = False

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_mouse_down(self, event: events.MouseDown) -> None:
        cell = self._mouse_to_cell(event.x, event.y)
        if cell is None: return
        abs_step, ci = cell
        if self.mode == MODE_GRAB and self.grabbed is not None:
            self.cursor_row = abs_step; self.cursor_col = ci
            self._clamp_cursor_for_grab()
            gs = self.cursor_row - self.grab_offset_row
            gc = self.cursor_col - self.grab_offset_col
            self.grabbed.row = gs / self.settings.height_steps; self.grabbed.col = gc
            self._snapshot()
            self.table.blocks.append(self.grabbed)
            self._invalidate_conflicts()
            cids = self._get_conflict_ids()
            self.status = ("  Placed \u26a0 OVERLAPPING" if id(self.grabbed) in cids
                           else "  Placed.")
            self.status_err = bool(cids and id(self.grabbed) in cids)
            self.grabbed = None; self.mode = MODE_NORMAL
        elif self.mode == MODE_MGRB:
            self.cursor_row = abs_step; self.cursor_col = ci
            self._drop_multi()
        elif self.mode == MODE_NORMAL:
            block = self._block_at(abs_step, ci)
            if block:
                # Group-grab if block belongs to a group
                if block.group:
                    members = self._group_members(block.group)
                    self.grabbed_group = members
                    hs = self.settings.height_steps
                    self.grp_offsets = [(round(b.row * hs) - abs_step, int(b.col) - ci)
                                        for b in members]
                    for b in members: self.table.blocks.remove(b)
                    self.cursor_row = abs_step; self.cursor_col = ci
                    self.mode = MODE_MGRB
                    self.status = f"  Grabbed group [{block.group}] ({len(members)} blocks)"
                else:
                    hs = self.settings.height_steps
                    self.grabbed          = block
                    self.grab_offset_row  = abs_step - round(block.row * hs)
                    self.grab_offset_col  = ci - int(block.col)
                    self.cursor_row = abs_step; self.cursor_col = ci
                    self.table.blocks.remove(block)
                    self.mode = MODE_GRAB
                    self.status = f"  Grabbed [{block.name}]"; self.status_err = False
        self._clamp_cursor_for_grab(); self._scroll_to_cursor(); self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.mode not in (MODE_GRAB, MODE_MGRB): return
        cell = self._mouse_to_cell(event.x, event.y)
        if cell is None: return
        self.cursor_row, self.cursor_col = cell
        self._clamp_cursor_for_grab(); self._scroll_to_cursor(); self.refresh()

    def _mouse_to_cell(self, x: int, y: int) -> Optional[tuple[int, int]]:
        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        H = self.size.height; hs = self.settings.height_steps; nr = len(self.table.rows)
        if y == 0 or y == H - 1: return None
        body_y = y - 1; step_in_view = body_y // step_h
        abs_step = self.view_row_off + step_in_view
        if step_in_view >= n_vis_s or abs_step >= nr * hs: return None
        if x < row_lw: return None
        cx = x - row_lw
        for i, ci in enumerate(vis_cols):
            cx -= 1
            if cx < 0: return abs_step, ci
            if cx < col_widths[i]: return abs_step, ci
            cx -= col_widths[i]
        return None

    # ── Single grab / drop ────────────────────────────────────────────────────

    def _pickup_single(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        # Group-grab?
        if block.group:
            members = self._group_members(block.group)
            hs = self.settings.height_steps
            self.grabbed_group = members
            self.grp_offsets   = [(round(b.row * hs) - self.cursor_row,
                                   int(b.col) - self.cursor_col) for b in members]
            for b in members: self.table.blocks.remove(b)
            self.mode = MODE_MGRB
            self.status = f"  Grabbed group [{block.group}] ({len(members)} blocks)"
        else:
            hs = self.settings.height_steps
            self.grabbed          = block
            self.grab_offset_row  = self.cursor_row - round(block.row * hs)
            self.grab_offset_col  = self.cursor_col - int(block.col)
            self.table.blocks.remove(block)
            self.mode = MODE_GRAB
            self.status = f"  Grabbed [{block.name}]"; self.status_err = False

    def _drop_single(self) -> None:
        gs = self.cursor_row - self.grab_offset_row
        gc = self.cursor_col - self.grab_offset_col
        hs = self.settings.height_steps
        self.grabbed.row = gs / hs; self.grabbed.col = gc
        self._snapshot()
        self.table.blocks.append(self.grabbed)
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        cf   = id(self.grabbed) in cids
        self.status = (f"  Placed [{self.grabbed.name}]  \u26a0 OVERLAPPING" if cf
                       else f"  Placed [{self.grabbed.name}]")
        self.status_err = cf; self.grabbed = None; self.mode = MODE_NORMAL

    # ── Multi-grab / drop ─────────────────────────────────────────────────────

    def _start_multi_grab(self) -> None:
        selected = [b for b in self.table.blocks if id(b) in self.selected_ids]
        if not selected: return
        hs = self.settings.height_steps
        self.grabbed_group = selected
        self.grp_offsets   = [(round(b.row * hs) - self.cursor_row,
                               int(b.col) - self.cursor_col) for b in selected]
        for b in selected: self.table.blocks.remove(b)
        self.selected_ids.clear(); self.mode = MODE_MGRB
        self.status = f"  Grabbed {len(selected)} blocks"

    def _drop_multi(self) -> None:
        hs = self.settings.height_steps
        self._snapshot()
        for i, gb in enumerate(self.grabbed_group):
            ro, co = self.grp_offsets[i]
            gb.row = (self.cursor_row + ro) / hs
            gb.col =  self.cursor_col + co
            self.table.blocks.append(gb)
        self.grabbed_group = []; self.grp_offsets = []
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        self.status = ("  Group placed  \u26a0 OVERLAPPING" if cids else "  Group placed.")
        self.status_err = bool(cids); self.mode = MODE_NORMAL

    # ── Search ────────────────────────────────────────────────────────────────

    def _cmd_clear_search(self) -> None:
        self._search_matches = []; self._search_query = ""
        self.status = "  Search highlight cleared."; self.status_err = False

    def _cmd_search_start(self) -> None:
        def done(vals: list[str]) -> None:
            q = vals[0].strip()
            if not q:
                self._search_matches = []; self._search_query = ""; return
            self._search_query   = q
            self._search_matches = [b for b in self.table.blocks
                                     if q.lower() in b.name.lower()]
            self._search_idx = 0
            if self._search_matches:
                self._jump_to_match(0)
                self.status = (f"  Found {len(self._search_matches)} match(es) for '{q}'  "
                               f"n/N next/prev")
            else:
                self.status = f"  No match for '{q}'"; self.status_err = True
        self._prompt([f"Search blocks"], done)

    def _cmd_search_next(self, forward: bool) -> None:
        if not self._search_matches:
            self.status = "  No search active — press / to search"; self.status_err = True; return
        n = len(self._search_matches)
        self._search_idx = (self._search_idx + (1 if forward else -1)) % n
        self._jump_to_match(self._search_idx)
        self.status = (f"  Match {self._search_idx + 1}/{n}: '{self._search_matches[self._search_idx].name}'")

    def _jump_to_match(self, idx: int) -> None:
        b = self._search_matches[idx]
        hs = self.settings.height_steps
        self.cursor_row = round(b.row * hs)
        self.cursor_col = int(b.col)

    # ── Group / ungroup ───────────────────────────────────────────────────────

    def _cmd_group(self) -> None:
        # Collect blocks to group: selection or current block
        targets = [b for b in self.table.blocks if id(b) in self.selected_ids]
        if not targets:
            block = self._block_at(self.cursor_row, self.cursor_col)
            if block: targets = [block]
        if not targets:
            self.status = "  No blocks to group."; self.status_err = True; return
        def done(vals: list[str]) -> None:
            name = vals[0].strip() or "group1"
            self._snapshot()
            for b in targets: b.group = name
            self.selected_ids.clear()
            self.status = f"  Grouped {len(targets)} blocks as '{name}'"
            self.status_err = False
        self._prompt(["Group name"], done)

    def _cmd_ungroup(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block or not block.group:
            self.status = "  No grouped block at cursor."; self.status_err = True; return
        grp = block.group
        members = self._group_members(grp)
        self._snapshot()
        for b in members: b.group = None
        self.status = f"  Ungrouped {len(members)} blocks from '{grp}'"
        self.status_err = False

    # ── Shelf ─────────────────────────────────────────────────────────────────

    def _cmd_shelf_send(self) -> None:
        targets = [b for b in self.table.blocks if id(b) in self.selected_ids]
        if not targets:
            block = self._block_at(self.cursor_row, self.cursor_col)
            # If block is grouped, send whole group
            if block and block.group:
                targets = self._group_members(block.group)
            elif block:
                targets = [block]
        if not targets:
            self.status = "  No block at cursor."; self.status_err = True; return
        self._snapshot()
        shelf_entry = copy.deepcopy(targets)
        for b in targets: self.table.blocks.remove(b)
        self.shelf.append(shelf_entry)
        self.selected_ids.clear()
        self._invalidate_conflicts()
        names = ", ".join(b.name for b in shelf_entry[:3])
        if len(shelf_entry) > 3: names += f" +{len(shelf_entry)-3} more"
        self.status = f"  Shelved: {names}  [shelf now has {len(self.shelf)} item(s)]"
        self.status_err = False

    def _cmd_shelf_pull(self) -> None:
        if not self.shelf:
            self.status = "  Shelf is empty. (s to send blocks to shelf)"; self.status_err = True; return
        if len(self.shelf) == 1:
            self._shelf_place(0); return
        # Show full-screen vertical shelf picker (vim :reg style)
        self._shelf_pick_mode = False
        self.app.push_screen(ShelfScreen(self.shelf, self._shelf_place))

    def _render_shelf_picker(self, W: int):
        """Fallback inline display for single-item fast-path (not normally reached)."""
        entry = self.shelf[0] if self.shelf else []
        names = ", ".join(b.name for b in entry[:4])
        msg   = f"  SHELF[0]: [{len(entry)} blocks] {names}  | press 0  Esc cancel"
        return [Segment(msg.ljust(W)[:W], Style(bgcolor="dark_blue", color="bright_white", bold=True))]

    def _shelf_place(self, idx: int) -> None:
        entry  = self.shelf.pop(idx)
        if not entry: return
        hs     = self.settings.height_steps
        s      = self.settings
        # Anchor: first block in entry goes exactly at cursor top-left.
        # All other blocks maintain their relative positions.
        anchor_row = min(b.row for b in entry)
        anchor_col = min(int(b.col) for b in entry)
        cursor_unit_row = self.cursor_row / hs
        cursor_unit_col = self.cursor_col
        dr = cursor_unit_row - anchor_row
        dc = cursor_unit_col - anchor_col
        self._snapshot()
        for b in entry:
            new_row = b.row + dr
            new_col = int(b.col) + dc
            # If wrap is off, clamp to table bounds
            if not s.block_wrap:
                nr = len(self.table.rows); nc = len(self.table.columns)
                bh = round(b.height * hs)
                new_row = max(0.0, min(new_row, (nr * hs - bh) / hs))
                new_col = max(0, min(new_col, nc - b.width))
            b.row = new_row; b.col = float(new_col)
            self.table.blocks.append(b)
        self._invalidate_conflicts()
        names = ", ".join(b.name for b in entry[:3])
        if len(entry) > 3: names += f" +{len(entry)-3} more"
        self.status = f"  Placed from shelf: {names}"; self.status_err = False

    # ── Yank / paste ──────────────────────────────────────────────────────────

    def _cmd_yank(self) -> None:
        targets = [b for b in self.table.blocks if id(b) in self.selected_ids]
        if not targets:
            block = self._block_at(self.cursor_row, self.cursor_col)
            if block: targets = [block]
        if not targets:
            self.status = "  No block at cursor."; self.status_err = True; return
        self.clipboard = copy.deepcopy(targets)
        self.status = f"  Yanked {len(targets)} block(s)"; self.status_err = False

    def _cmd_paste(self) -> None:
        if not self.clipboard:
            self.status = "  Nothing in clipboard."; self.status_err = True; return
        hs   = self.settings.height_steps
        orig = self.clipboard[0]
        dr   = self.cursor_row / hs - orig.row
        dc   = self.cursor_col - int(orig.col)
        self._snapshot()
        for bc in self.clipboard:
            nb = copy.copy(bc)
            nb.row = max(0.0, bc.row + dr)
            nb.col = max(0, int(bc.col) + dc)
            nb.color_idx = self._next_color()
            self.table.blocks.append(nb)
        self._invalidate_conflicts()
        self.status = f"  Pasted {len(self.clipboard)} block(s)"; self.status_err = False

    # ── Block delete / rename / transparent ───────────────────────────────────

    def _cmd_rename_block(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        def done(vals: list[str]) -> None:
            self._snapshot(); block.name = vals[0] or block.name
            self.status = f"  Renamed: {block.name}"; self.status_err = False
        self._prompt(["New name"], done, [block.name])

    def _cmd_delete_block(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        def done(vals: list[str]) -> None:
            if vals[0].lower() == "y":
                self._snapshot(); self.table.blocks.remove(block)
                self._invalidate_conflicts()
                self.status = f"  Deleted: {block.name}"; self.status_err = False
            else: self.status = "  Cancelled."
        self._prompt([f"Delete '{block.name}'? (y/n)"], done)

    def _cmd_toggle_transparent(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        self._snapshot(); block.transparent = not block.transparent
        self._invalidate_conflicts()
        self.status = f"  {block.name} \u2192 {'transparent' if block.transparent else 'solid'}"
        self.status_err = False

    # ── Flash / transpose / check ─────────────────────────────────────────────

    def _cmd_toggle_flash(self) -> None:
        self.flash_mode = not self.flash_mode
        self.status = (f"  FLASH ON  │  f/Esc exit" if self.flash_mode else _HINT)
        if self.flash_mode: self._invalidate_conflicts()
        self.status_err = False

    def _cmd_transpose(self) -> None:
        hs = self.settings.height_steps
        self._snapshot()
        self.table.rows, self.table.columns = self.table.columns, self.table.rows
        nc_new = len(self.table.columns)
        for b in self.table.blocks:
            old_row, old_col = b.row, float(b.col)
            old_h,   old_w   = b.height, b.width
            b.row    = old_col
            b.col    = float(max(0, min(nc_new - 1, int(old_row))))
            b.height = float(old_w)
            # Use ceil not round: avoids banker's rounding (round(0.5)=0 in Python3)
            b.width  = max(1, math.ceil(old_h))
        self.settings.transposed = not self.settings.transposed
        # Fix cursor: save both before updating either
        old_cr, old_cc   = self.cursor_row, self.cursor_col
        self.cursor_row  = old_cc * hs
        self.cursor_col  = min(nc_new - 1, old_cr // hs)
        self.view_row_off = 0; self.view_col_off = 0
        self._invalidate_conflicts()
        flag = 'transposed' if self.settings.transposed else 'normal'
        self.status = (f"  Transposed — {len(self.table.rows)} rows × "
                       f"{len(self.table.columns)} cols ({flag}, T to restore)")
    def _cmd_export(self, parts: list[str]) -> None:
        """:export [file.svg] — render the table to an SVG file."""
        import xml.etree.ElementTree as ET

        stem  = self.filepath.rsplit(".", 1)[0] if self.filepath else "table"
        fname = parts[1] if len(parts) > 1 else stem + ".svg"

        hs = self.settings.height_steps
        nr = len(self.table.rows)
        nc = len(self.table.columns)

        CELL_W = 120; CELL_H = 44 // hs * hs   # px per column / row-unit
        HDR_H  = 34;  LBL_W  = 96;  PAD = 8
        FONT   = "monospace"

        svg_w = LBL_W + nc * CELL_W + 1
        svg_h = HDR_H + nr * (CELL_H // hs * hs) + 1

        ns_svg = "http://www.w3.org/2000/svg"
        root = ET.Element("svg", {
            "xmlns": ns_svg,
            "width": str(svg_w), "height": str(svg_h),
            "viewBox": f"0 0 {svg_w} {svg_h}",
            "style": f"font-family:{FONT};background:#1e1e1e;",
        })

        def rect(x, y, w, h, fill, rx="0", opacity="1", stroke=None, sw="1"):
            attrs = {"x":str(x),"y":str(y),"width":str(w),"height":str(h),
                     "fill":fill,"rx":rx,"opacity":opacity}
            if stroke: attrs["stroke"] = stroke; attrs["stroke-width"] = sw
            return ET.SubElement(root, "rect", attrs)

        def text(x, y, txt, fill, size="12", anchor="middle", bold=False, italic=False):
            style = f"font-size:{size}px;fill:{fill};text-anchor:{anchor};"
            if bold: style += "font-weight:bold;"
            if italic: style += "font-style:italic;"
            el = ET.SubElement(root, "text", {"x":str(x),"y":str(y),"style":style})
            el.text = str(txt); return el

        def line(x1,y1,x2,y2,stroke="#444"):
            ET.SubElement(root,"line",{"x1":str(x1),"y1":str(y1),"x2":str(x2),"y2":str(y2),
                "stroke":stroke,"stroke-width":"1"})

        # Background + header band
        rect(0,0,svg_w,svg_h,"#1e1e1e")
        rect(0,0,svg_w,HDR_H,"#2a2a2a")
        rect(0,0,LBL_W,svg_h,"#252525")

        # Column headers
        for ci, col in enumerate(self.table.columns):
            cx = LBL_W + ci * CELL_W + CELL_W // 2
            text(cx, HDR_H - PAD, str(col), "#58d1eb", size="13", bold=True)
            line(LBL_W + ci * CELL_W, 0, LBL_W + ci * CELL_W, svg_h, "#555")
        line(LBL_W + nc * CELL_W, 0, LBL_W + nc * CELL_W, svg_h, "#555")

        # Row labels + horizontal lines
        step_h_px = CELL_H // hs
        for ri, row in enumerate(self.table.rows):
            y = HDR_H + ri * CELL_H
            line(0, y, svg_w, y, "#444")
            text(LBL_W - PAD, y + CELL_H // 2 + 5, str(row), "#cccccc",
                 size="12", anchor="end")
        line(0, HDR_H + nr * CELL_H, svg_w, HDR_H + nr * CELL_H, "#444")

        # Palette name → hex
        _HEX = {"green":"#008000","blue":"#0000cd","dark_magenta":"#8b008b",
                "dark_cyan":"#008b8b","red3":"#cd0000","yellow":"#cdcd00",
                "spring_green2":"#00cd66","dark_blue":"#00008b",
                "magenta":"#cd00cd","cyan":"#00cdcd","orange3":"#cd8b00",
                "purple":"#800080","deep_sky_blue3":"#0087af",
                "chartreuse3":"#5faf00","hot_pink3":"#af5f87","gold3":"#afaf00",
                "steel_blue":"#5f87af","dark_olive_green3":"#87af5f",
                "indian_red":"#af5f5f","slate_blue1":"#875fff",
                "turquoise2":"#00d7d7","rosy_brown":"#af8787"}
        _FG  = {"black":"#111","white":"#f0f0f0","bright_white":"#fff"}

        # Draw blocks
        for b in self.table.blocks:
            bs_s, be_s = self._block_steps(b)
            bc = int(b.col)
            bx = LBL_W + bc * CELL_W + 2
            by = HDR_H + (bs_s / hs) * step_h_px + 2
            bw_px = b.width * CELL_W - 4
            bh_px = ((be_s - bs_s) / hs) * step_h_px - 4
            if bw_px <= 0 or bh_px <= 0: continue
            bg_n, fg_n = _PALETTE[b.color_idx % len(_PALETTE)]
            bg = _HEX.get(bg_n, "#004400")
            fg = _FG.get(fg_n, "#f0f0f0")
            op = "0.40" if b.transparent else "0.88"
            g  = ET.SubElement(root, "g")
            ET.SubElement(g, "rect", {"x":str(bx),"y":str(by),
                "width":str(bw_px),"height":str(bh_px),
                "rx":"4","fill":bg,"opacity":op,
                "stroke":"#ffffff20","stroke-width":"1"})
            # Name — simple single-line centred
            ty = by + bh_px / 2 + 5
            lbl = b.name if len(b.name) * 7 < bw_px else b.name[:max(1, int(bw_px/7))] + "…"
            ET.SubElement(g,"text",{
                "x":str(bx + bw_px/2), "y":str(ty),
                "style":f"font-size:12px;fill:{fg};text-anchor:middle;font-weight:bold;"
            }).text = lbl
            if b.group:
                ET.SubElement(g,"rect",{"x":str(bx+2),"y":str(by+2),
                    "width":"7","height":"7","rx":"2","fill":fg,"opacity":"0.5"})

        # Outer border
        ET.SubElement(root,"rect",{"x":"0","y":"0",
            "width":str(svg_w-1),"height":str(svg_h-1),
            "fill":"none","stroke":"#666","stroke-width":"1"})

        tree = ET.ElementTree(root)
        try:
            ET.indent(tree, space="  ")
        except AttributeError:
            pass  # Python < 3.9 has no indent()
        try:
            tree.write(fname, encoding="unicode", xml_declaration=True)
            self.status = (f"  Exported → {fname}  "
                           f"({nr}r×{nc}c, {len(self.table.blocks)} blocks)")
            self.status_err = False
        except Exception as e:
            self.status = f"  Export failed: {e}"; self.status_err = True

    def _cmd_check(self) -> None:
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        if not cids:
            self.status = "  \u2713 No overlapping solid blocks."; self.status_err = False; return
        names = list(dict.fromkeys(b.name for b in self.table.blocks if id(b) in cids))
        self.status = "  \u2717 Overlapping: " + "  \u2194  ".join(names); self.status_err = True

    # ── Row / column commands ─────────────────────────────────────────────────

    def _cmd_add_row(self, below: bool) -> None:
        hs = self.settings.height_steps; unit_i = self.cursor_row // hs
        n  = len(self.table.rows); ref = self.table.rows[min(unit_i, n - 1)]
        ins = unit_i + (1 if below else 0)
        def done(vals: list[str]) -> None:
            label = vals[0] or f"Row {ins + 1}"
            self._snapshot()
            self.table.rows.insert(ins, label)
            for b in self.table.blocks:
                if b.row >= ins: b.row += 1.0
            if not below:
                self.cursor_row = min(self.cursor_row + hs, len(self.table.rows) * hs - 1)
            self._invalidate_conflicts()
            self.status = f"  Added row: {label}"; self.status_err = False
        self._prompt([f"Label ({'after' if below else 'before'} '{ref}')"], done)

    def _cmd_delete_row(self) -> None:
        hs = self.settings.height_steps; unit_i = self.cursor_row // hs
        if len(self.table.rows) <= 1:
            self.status = "  Cannot delete last row."; self.status_err = True; return
        label = self.table.rows[unit_i]
        def done(vals: list[str]) -> None:
            if vals[0].lower() != "y": self.status = "  Cancelled."; return
            self._snapshot()
            self.table.rows.pop(unit_i)
            keep = []
            for b in self.table.blocks:
                if b.row < unit_i + 1 and b.row + b.height > unit_i: continue
                if b.row >= unit_i + 1: b.row -= 1.0
                keep.append(b)
            self.table.blocks = keep
            self.cursor_row = min(self.cursor_row, len(self.table.rows) * hs - 1)
            self._invalidate_conflicts()
            self.status = f"  Deleted row: {label}"; self.status_err = False
        self._prompt([f"Delete row '{label}'? (y/n)"], done)

    def _cmd_add_col(self, right: bool) -> None:
        ci = self.cursor_col; nc = len(self.table.columns)
        ref = self.table.columns[min(ci, nc - 1)]; ins = ci + (1 if right else 0)
        def done(vals: list[str]) -> None:
            label = vals[0] or f"Col {ins + 1}"
            self._snapshot()
            self.table.columns.insert(ins, label)
            for b in self.table.blocks:
                if int(b.col) >= ins: b.col = int(b.col) + 1
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
        def done(vals: list[str]) -> None:
            if vals[0].lower() != "y": self.status = "  Cancelled."; return
            self._snapshot()
            self.table.columns.pop(ci)
            keep = []
            for b in self.table.blocks:
                bc = int(b.col)
                if bc > ci:             b.col = bc - 1; keep.append(b)
                elif bc <= ci < bc + b.width:
                    b.width -= 1
                    if b.width >= 1: keep.append(b)
                else: keep.append(b)
            self.table.blocks = keep
            self.cursor_col = min(self.cursor_col, len(self.table.columns) - 1)
            self._invalidate_conflicts()
            self.status = f"  Deleted column: {label}"; self.status_err = False
        self._prompt([f"Delete column '{label}'? (y/n)"], done)

    # ── Vim edit ──────────────────────────────────────────────────────────────

    def _open_in_vim(self) -> None:
        if not self.filepath:
            self.status = "  No file \u2014 save with :w first."; self.status_err = True; return
        self._save(); self.run_worker(self._vim_worker)

    async def _vim_worker(self) -> None:
        editor = os.environ.get("EDITOR", "vim")
        with self.app.suspend():
            subprocess.run([editor, self.filepath])
        try:
            table, settings = load_yaml(self.filepath)
            self.table = table; self.settings = settings
            self._invalidate_conflicts()
            self.status = f"  Reloaded from {self.filepath}"; self.status_err = False
        except Exception as e:
            self.status = f"  Reload error: {e}"; self.status_err = True
        self.refresh()


# ─────────────────────────────────────────────────────────────────────────────
#  Application
# ─────────────────────────────────────────────────────────────────────────────

class TablePlanApp(App):
    CSS = """
    Screen     { background: $surface; }
    GridWidget { width: 100%; height: 100%; }
    HelpScreen  { align: center middle; background: rgba(0,0,0,0.8); }
    HelpScreen  Static { background: $surface; padding: 1 2; border: round $primary; }
    ShelfScreen { align: center middle; background: rgba(0,0,0,0.85); }
    ShelfScreen Static { background: #1e2030; padding: 1 3; border: round cyan; width: 62; }
    """
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, table: TableData, settings: Settings,
                 filepath: Optional[str]) -> None:
        super().__init__()
        self._table = table; self._settings = settings; self._filepath = filepath

    def compose(self) -> ComposeResult:
        yield GridWidget(self._table, self._settings, self._filepath)

    def on_mount(self) -> None:
        self.title = f"tableplan \u2014 {self._filepath}" if self._filepath else "tableplan (demo)"
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
        if filepath: save_yaml(filepath, table, settings)
    TablePlanApp(table, settings, filepath).run()


if __name__ == "__main__":
    main()
