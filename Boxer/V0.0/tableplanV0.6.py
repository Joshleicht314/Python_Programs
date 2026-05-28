#!/usr/bin/env python3
"""
tableplan v0.6  —  vim-style terminal table organizer

Usage:
    python tableplan.py              # in-memory demo
    python tableplan.py myplan.yaml  # load or create YAML file
"""
from __future__ import annotations

import copy, os, subprocess, sys
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
#  Color palette
# ─────────────────────────────────────────────────────────────────────────────

_PALETTE: list[tuple[str, str]] = [
    ("green",        "black"),   # 0
    ("blue",         "white"),   # 1
    ("dark_magenta", "white"),   # 2
    ("dark_cyan",    "black"),   # 3
    ("red3",         "white"),   # 4
    ("yellow",       "black"),   # 5
    ("spring_green2","black"),   # 6
    ("dark_blue",    "white"),   # 7
    ("magenta",      "black"),   # 8
    ("cyan",         "black"),   # 9
    ("orange3",      "black"),   # a=10
    ("purple",       "white"),   # b=11
]
_PAL_KEYS = "0123456789ab"

def _solid(ci: int) -> Style:
    bg, fg = _PALETTE[ci % len(_PALETTE)]
    return Style(bgcolor=bg, color=fg, bold=True)

def _dim(ci: int) -> Style:
    bg, _ = _PALETTE[ci % len(_PALETTE)]
    return Style(bgcolor=bg, color="bright_black")

def _cursor_on(ci: int) -> Style:
    bg, fg = _PALETTE[ci % len(_PALETTE)]
    return Style(bgcolor="white", color=bg, bold=True, underline=True)

def _selected_style(ci: int) -> Style:
    bg, fg = _PALETTE[ci % len(_PALETTE)]
    return Style(bgcolor=bg, color=fg, bold=True, underline=True, overline=True)

S_CONFLICT = Style(bgcolor="red",        color="bright_white", bold=True)
S_GHOST_OK = Style(bgcolor="yellow",     color="black")
S_GHOST_CF = Style(bgcolor="dark_orange3", color="white")
S_GHOST_OB = Style(bgcolor="red",        color="white")
S_BORDER   = Style(color="bright_black")
S_HEADER   = Style(color="cyan", bold=True)
S_LABEL    = Style(color="white")
S_CURSOR   = Style(bgcolor="blue", color="white", bold=True)
S_EMPTY    = Style()
S_STATUS   = Style(color="bright_white")
S_ERR      = Style(color="red", bold=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    name:        str
    height:      float
    width:       int
    row:         float
    col:         int
    transparent: bool = False
    color_idx:   int  = 0


@dataclass
class TableData:
    name:    str
    columns: list[str]
    rows:    list[str]
    blocks:  list[Block] = field(default_factory=list)


@dataclass
class Settings:
    height_steps:     int           = 2
    zoom_h:           float         = 1.0
    zoom_w:           float         = 1.0
    block_wrap:       bool          = False
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
            name=str(bd["name"]), height=float(bd.get("height", 1.0)),
            width=int(bd.get("width", 1)), row=float(bd.get("row", 0.0)),
            col=int(bd.get("col", 0)), transparent=bool(bd.get("transparent", False)),
            color_idx=int(bd.get("color_idx", 0)),
        ))
    sd = data.get("settings", {})
    return table, Settings(
        height_steps    =int(sd.get("height_steps", 2)),
        zoom_h          =float(sd.get("zoom_h", 1.0)),
        zoom_w          =float(sd.get("zoom_w", 1.0)),
        block_wrap      =bool(sd.get("block_wrap", False)),
        max_visible_cols=sd.get("max_visible_cols"),
        max_visible_rows=sd.get("max_visible_rows"),
    )


def save_yaml(path: str, table: TableData, settings: Settings) -> None:
    sd: dict = {k: v for k, v in {
        "height_steps": settings.height_steps, "zoom_h": settings.zoom_h,
        "zoom_w": settings.zoom_w, "block_wrap": settings.block_wrap,
        "max_visible_cols": settings.max_visible_cols,
        "max_visible_rows": settings.max_visible_rows,
    }.items() if v is not None}
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"table": {"name": str(table.name),
                        "columns": [str(c) for c in table.columns],
                        "rows":    [str(r) for r in table.rows]},
             "settings": sd,
             "blocks": [{"name": b.name, "height": b.height, "width": b.width,
                          "row": b.row, "col": b.col, "transparent": b.transparent,
                          "color_idx": b.color_idx} for b in table.blocks]},
            f, default_flow_style=False, allow_unicode=True, sort_keys=False,
        )


def _demo_table() -> tuple[TableData, Settings]:
    return TableData(
        name="Weekly Schedule",
        columns=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        rows=["8:00am", "9:00am", "10:00am", "11:00am", "12:00pm"],
        blocks=[
            Block("Dog Walk",  0.5, 1, 0.0, 0, color_idx=0),
            Block("Standup",   0.5, 5, 1.0, 0, color_idx=1),
            Block("Deep Work", 2.0, 2, 2.0, 2, color_idx=2),
            Block("Lunch",     1.0, 1, 4.0, 1, color_idx=3),
        ],
    ), Settings()


# ─────────────────────────────────────────────────────────────────────────────
#  Help
# ─────────────────────────────────────────────────────────────────────────────

HELP_TEXT = """\
╔══════════════════════════════════════════════════════════════════╗
║                    tableplan  v0.6  —  controls                  ║
╠═══════════════════════════════════╦══════════════════════════════╣
║  NAVIGATION                       ║  BLOCKS                      ║
║  h/l       move left/right        ║  space   grab / drop         ║
║  j/k       move down/up           ║  a       add new block       ║
║  (scrolls automatically)          ║  e       edit block (resize) ║
╠═══════════════════════════════════║  E       rename block        ║
║  SIZING MODE  (after a / e)       ║  x       delete block        ║
║  SIZING MODE  (after a or e)      ║  v       toggle transparent  ║
║  l / h    wider / narrower        ║  y       yank (copy)         ║
║  j / k    taller / shorter        ║  p       paste copy          ║
║  H/J/K/L  move anchor position    ║  c       change color        ║
║  Enter    confirm                 ╠══════════════════════════════╣
║  Esc      cancel                  ║  MULTI-SELECT                ║
╠═══════════════════════════════════║  V       toggle visual mode  ║
║  ZOOM & VIEW                      ║  hjkl    move + paint select ║
║  +        zoom in                 ║  space   grab selection      ║
║  -        zoom out                ║  Esc     exit visual mode    ║
║  T        transpose axes (T×2=undo)╠══════════════════════════════╣
║  f / :flash  reveal hidden blocks ║  COMMANDS                    ║
╠═══════════════════════════════════║  :w  :q  :q!  ZZ  " ?  Tab   ║
║  ROWS & COLUMNS                   ║  COMMANDS                    ║
║  o / O    add row below/above     ║  :w      save                ║
║  i / I    add col left/right      ║  :q      save & quit         ║
║  d        delete row              ║  :q!     quit no save        ║
║  D        delete column           ║  ZZ      save & quit         ║
╠═══════════════════════════════════╠══════════════════════════════╣
║  :set wrap / nowrap               ║  Overlap → always solid red  ║
║  :set transpose  swap axes        ║  :check  list overlapping    ║
║  :set width N   visible cols      ╚══════════════════════════════╝
║  :set height N  visible rows
║  :set tolerance N  steps/unit
║  :set home  reset zoom/view
╚═══════════════════════════════════╝
  Press any key to close."""


class HelpScreen(Screen):
    CSS = "Screen{align:center middle;}Static{width:auto;}"
    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT)
    def on_key(self, _: events.Key) -> None:
        self.app.pop_screen()


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
#  Modes & tab-complete list
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
    ":check", ":flash", ":q", ":q!", ":w", ":wq", ":x",
    ":set home", ":set nowrap", ":set transpose", ":set wrap",
    ":set width ", ":set height ", ":set tolerance ",
])

_HINT = ("  hjkl:move  spc:grab  a:add  e:edit  E:rename  x:del  v:transp  V:visual  "
         "y:yank  p:paste  c:color  f:flash  T:transpose  o/O:row  i/I:col  d/D:del  "
         "-/+:zoom  \":vim  ?:help  ZZ/:w:save  :check")


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
        # Cursor / viewport
        self.cursor_row     = 0     # absolute steps
        self.cursor_col     = 0     # absolute column index
        self.view_row_off   = 0
        self.view_col_off   = 0
        # Mode
        self.mode           = MODE_NORMAL
        # Single grab
        self.grabbed: Optional[Block] = None
        self.grab_offset_row: int     = 0   # steps from block top to cursor at grab time
        self.grab_offset_col: int     = 0   # cols  from block left to cursor at grab time
        # Multi-select / visual
        self.selected_ids: set[int]   = set()   # Python id() of selected blocks
        # Multi-grab
        self.grabbed_group: list[Block]          = []
        self.grp_offsets:   list[tuple[int,int]] = []  # (row_off_steps, col_off) per block
        # Sizing (a/e)
        self.sizing_block:  Optional[Block] = None
        self.sizing_target: Optional[Block] = None  # None=new, else=edit target
        # Color picker
        self.color_block: Optional[Block]  = None
        # Clipboard
        self.clipboard:   Optional[Block]  = None
        # Prompt
        self.prompt: Optional[Prompt] = None
        # Command
        self.cmd_buf    = ""
        self._tab_prefix    = ""
        self._tab_candidates: list[str] = []
        self._tab_idx       = 0
        self._in_tab_cycle  = False
        # Flash mode
        self.flash_mode = False
        # Status
        self.status     = _HINT
        self.status_err = False
        self.last_key   = ""
        # Conflicts
        self._conflict_set: set[int] = set()
        self._conflict_dirty         = True
        # Layout cache
        self._step_h      = 1
        self._row_lw      = 8
        self._col_widths: list[int] = []
        self._vis_cols:   list[int] = []
        self._n_vis_steps = 1

    # ── Layout ───────────────────────────────────────────────────────────────

    def _layout(self) -> tuple[int, int, list[int], list[int], int]:
        """
        Return (step_h, row_lw, col_widths, vis_cols, n_vis_steps).
        All visible columns share the same width (uniform grid).
        Row height fills available space based on n_visible_rows.
        Updates self._* cache.
        """
        W, H   = self.size.width, self.size.height
        n_rows = len(self.table.rows)
        n_cols = len(self.table.columns)
        s      = self.settings

        # ── Row-label column ──────────────────────────────────────────────────
        # Coerce to str defensively (YAML may load numbers as int)
        rows_s = [str(r) for r in self.table.rows]
        cols_s = [str(c) for c in self.table.columns]
        row_lw = max((len(r) for r in rows_s), default=5) + 2

        # ── Uniform column width ──────────────────────────────────────────────
        all_words: list[str] = []
        for ci in range(n_cols):
            all_words += cols_s[ci].split()
        for b in self.table.blocks:
            all_words += b.name.split()
        nat_w   = max((len(w) for w in all_words), default=3) + 2
        base_cw = max(3, int(nat_w * s.zoom_w))

        avail_w   = W - row_lw - 1          # left border already in row_lw gap
        max_fit   = max(1, avail_w // (base_cw + 1))
        vis_count = min(max_fit, n_cols - self.view_col_off)
        if s.max_visible_cols is not None:
            vis_count = min(vis_count, s.max_visible_cols)
        vis_count = max(1, vis_count)
        vis_cols  = list(range(self.view_col_off,
                               min(self.view_col_off + vis_count, n_cols)))

        # Fill width exactly
        avail_d  = max(len(vis_cols) * 3, avail_w - len(vis_cols))
        col_w    = max(3, avail_d // len(vis_cols))
        leftover = avail_d - col_w * len(vis_cols)
        col_widths = [col_w + (1 if i < leftover else 0) for i in range(len(vis_cols))]

        # ── Row step height ───────────────────────────────────────────────────
        # Determine visible step count FIRST, then scale step_h to fill height.
        n_steps  = n_rows * s.height_steps
        n_vis_s  = n_steps
        if s.max_visible_rows is not None:
            n_vis_s = min(n_vis_s, s.max_visible_rows * s.height_steps)
        n_vis_s  = max(1, n_vis_s)

        avail_h  = max(1, H - 2)                      # reserve header + status
        base_sh  = max(1, avail_h // n_vis_s)
        step_h   = max(1, int(base_sh * s.zoom_h))

        # Cache
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
        n_rows  = len(self.table.rows)
        n_cols  = len(self.table.columns)
        n_steps = max(1, n_rows * s.height_steps)

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
        """If nowrap, keep grabbed block(s) inside table bounds."""
        if self.settings.block_wrap:
            return
        hs = self.settings.height_steps
        nr = len(self.table.rows)
        nc = len(self.table.columns)

        if self.mode == MODE_GRAB and self.grabbed is not None:
            bh = round(self.grabbed.height * hs)
            bw = self.grabbed.width
            min_cr = self.grab_offset_row
            max_cr = (nr * hs - bh) + self.grab_offset_row
            min_cc = self.grab_offset_col
            max_cc = (nc - bw) + self.grab_offset_col
            self.cursor_row = max(min_cr, min(max_cr, self.cursor_row))
            self.cursor_col = max(min_cc, min(max_cc, self.cursor_col))

        elif self.mode == MODE_MGRB and self.grabbed_group:
            min_cr: Optional[int] = None
            max_cr: Optional[int] = None
            min_cc: Optional[int] = None
            max_cc: Optional[int] = None
            for i, gb in enumerate(self.grabbed_group):
                row_off, col_off = self.grp_offsets[i]
                bh = round(gb.height * hs)
                bw = gb.width
                lo_r = -row_off
                hi_r = nr * hs - bh - row_off
                lo_c = -col_off
                hi_c = nc - bw - col_off
                if min_cr is None:
                    min_cr, max_cr = lo_r, hi_r
                    min_cc, max_cc = lo_c, hi_c
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

    def _block_at(self, abs_step: int, ci: int) -> Optional[Block]:
        """Return solid block, then transparent, skipping grabbed/group/sizing_target."""
        skip = {id(self.grabbed), id(self.sizing_target)} | {id(g) for g in self.grabbed_group}
        found_t: Optional[Block] = None
        for b in self.table.blocks:
            if id(b) in skip: continue
            if b.col <= ci < b.col + b.width:
                bs, be = self._block_steps(b)
                if bs <= abs_step < be:
                    if not b.transparent: return b
                    if found_t is None:   found_t = b
        return found_t

    def _all_blocks_at(self, abs_step: int, ci: int) -> list[Block]:
        """Return ALL blocks occupying (abs_step, ci), solid first then transparent.
        Skips grabbed/group/sizing_target. Used for label display and flash mode."""
        skip = {id(self.grabbed), id(self.sizing_target)} | {id(g) for g in self.grabbed_group}
        solid_blocks: list[Block] = []
        transp_blocks: list[Block] = []
        for b in self.table.blocks:
            if id(b) in skip: continue
            if b.col <= ci < b.col + b.width:
                bs, be = self._block_steps(b)
                if bs <= abs_step < be:
                    if not b.transparent:
                        solid_blocks.append(b)
                    else:
                        transp_blocks.append(b)
        return solid_blocks + transp_blocks

    def _in_bounds(self, b: Block, step: int, ci: int) -> bool:
        hs = self.settings.height_steps
        nr = len(self.table.rows); nc = len(self.table.columns)
        bh = round(b.height * hs)
        if self.settings.block_wrap:
            # Only require block to START within the table
            return 0 <= ci < nc and 0 <= step < nr * hs
        return 0 <= ci and ci + b.width <= nc and 0 <= step and step + bh <= nr * hs

    def _has_conflict(self, b: Block, step: int, ci: int) -> bool:
        hs = self.settings.height_steps
        bh = round(b.height * hs)
        skip = {id(self.grabbed), id(self.sizing_target)} | {id(g) for g in self.grabbed_group}
        for ob in self.table.blocks:
            if id(ob) in skip or ob.transparent: continue
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
                as_, ae = self._block_steps(a); bs_, be = self._block_steps(b)
                if (a.col + a.width <= b.col) or (a.col >= b.col + b.width): continue
                if (ae <= bs_)               or (as_ >= be):                  continue
                result.add(id(a)); result.add(id(b))
        self._conflict_set = result; self._conflict_dirty = False
        return result

    def _next_color(self) -> int:
        used = {b.color_idx for b in self.table.blocks}
        for i in range(len(_PALETTE)):
            if i not in used: return i
        return len(self.table.blocks) % len(_PALETTE)

    # ── Ghost list ────────────────────────────────────────────────────────────

    def _get_ghosts(self) -> list[tuple[Block, int, int]]:
        """
        Return (block, ghost_top_step, ghost_left_col) for all active ghosts.
        Single grab accounts for the grab offset so block doesn't jump.
        """
        hs = self.settings.height_steps
        ghosts: list[tuple[Block, int, int]] = []

        if self.mode == MODE_GRAB and self.grabbed is not None:
            gs = self.cursor_row - self.grab_offset_row
            gc = self.cursor_col - self.grab_offset_col
            ghosts.append((self.grabbed, gs, gc))

        elif self.mode == MODE_MGRB:
            for i, gb in enumerate(self.grabbed_group):
                row_off, col_off = self.grp_offsets[i]
                ghosts.append((gb, self.cursor_row + row_off, self.cursor_col + col_off))

        elif self.mode == MODE_SIZING and self.sizing_block is not None:
            ghosts.append((self.sizing_block, self.cursor_row, self.cursor_col))

        return ghosts

    # ── Rendering ────────────────────────────────────────────────────────────

    def render_line(self, y: int) -> Strip:  # noqa: C901
        if self.size.width == 0 or self.size.height == 0:
            return Strip([])

        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        n_rows = len(self.table.rows)
        H, W   = self.size.height, self.size.width
        hs     = self.settings.height_steps

        # ── Status bar ───────────────────────────────────────────────────────
        if y == H - 1:
            return self._render_status(W)

        # ── Column header ─────────────────────────────────────────────────────
        if y == 0:
            segs: list[Segment] = [Segment(" " * row_lw, S_EMPTY)]
            for i, ci in enumerate(vis_cols):
                segs.append(Segment("│", S_BORDER))
                segs.append(Segment(
                    str(self.table.columns[ci])[:col_widths[i]].center(col_widths[i]), S_HEADER))
            segs.append(Segment("│", S_BORDER))
            used = row_lw + sum(col_widths) + len(vis_cols) + 1
            if used < W: segs.append(Segment(" " * (W - used), S_EMPTY))
            return Strip(segs)

        # ── Grid body ─────────────────────────────────────────────────────────
        body_y       = y - 1
        step_in_view = body_y // step_h
        line_in_step = body_y % step_h
        abs_step     = self.view_row_off + step_in_view

        if step_in_view >= n_vis_s or abs_step >= n_rows * hs:
            used = row_lw + sum(col_widths) + len(vis_cols) + 1
            return Strip([Segment(" " * W, S_EMPTY)])

        unit_i   = abs_step // hs
        sub_step = abs_step % hs
        show_lbl = (sub_step == 0) and (line_in_step == 0)

        conflict_ids = self._get_conflict_ids()
        ghosts       = self._get_ghosts()

        segs = []
        if show_lbl and unit_i < len(self.table.rows):
            segs.append(Segment(str(self.table.rows[unit_i]).ljust(row_lw)[:row_lw], S_LABEL))
        else:
            segs.append(Segment(" " * row_lw, S_EMPTY))

        for i, ci in enumerate(vis_cols):
            cw        = col_widths[i]
            is_cursor = (abs_step == self.cursor_row and ci == self.cursor_col
                         and self.mode not in (MODE_GRAB, MODE_MGRB, MODE_SIZING))
            segs.append(Segment("│", S_BORDER))

            # 1. Ghost rendering
            cell_done = False
            for ghost_block, gs, gc in ghosts:
                ge  = gs + round(ghost_block.height * hs)
                gce = gc + ghost_block.width
                if gs <= abs_step < ge and gc <= ci < gce:
                    in_b = self._in_bounds(ghost_block, gs, gc)
                    cf   = self._has_conflict(ghost_block, gs, gc)
                    if not in_b:   gstyle = S_GHOST_OB
                    elif cf:       gstyle = S_GHOST_CF
                    else:          gstyle = S_GHOST_OK
                    tot = round(ghost_block.height * hs) * step_h
                    lig = (abs_step - gs) * step_h + line_in_step
                    mid = max(0, tot // 2)
                    if self.mode == MODE_SIZING:
                        sb   = self.sizing_block
                        dims = f"{sb.name}  {sb.height:.3g}u×{sb.width}c"
                        txt  = dims if lig == mid else ""
                    else:
                        txt = ghost_block.name if lig == mid else ""
                    segs.append(Segment(txt[:cw].center(cw), gstyle))
                    cell_done = True
                    break

            # 2. Normal cell
            if not cell_done:
                block = self._block_at(abs_step, ci)
                all_blks = self._all_blocks_at(abs_step, ci)
                if all_blks:
                    top = all_blks[0]
                    n   = len(all_blks)

                    if self.flash_mode:
                        # Stripe: each terminal line shows a different block's name+color
                        show_idx  = line_in_step % n
                        show_blk  = all_blks[show_idx]
                        txt       = show_blk.name
                        if id(show_blk) in self.selected_ids:
                            txt   = "►" + show_blk.name
                        if id(show_blk) in conflict_ids:
                            style = S_CONFLICT
                        elif show_blk.transparent:
                            style = _dim(show_blk.color_idx)
                        else:
                            style = _solid(show_blk.color_idx)
                    elif n == 1:
                        # Single block — show name on middle line only
                        bs, be = self._block_steps(top)
                        tot    = (be - bs) * step_h
                        lib    = (abs_step - bs) * step_h + line_in_step
                        raw    = ("►" + top.name) if id(top) in self.selected_ids else top.name
                        txt    = raw if lib == max(0, tot // 2) else ""
                        if is_cursor:
                            style = _cursor_on(top.color_idx)
                        elif id(top) in self.selected_ids:
                            style = _selected_style(top.color_idx)
                        elif top.transparent:
                            style = _dim(top.color_idx)
                        elif id(top) in conflict_ids:
                            style = S_CONFLICT
                        else:
                            style = _solid(top.color_idx)
                    else:
                        # Multiple overlapping blocks:
                        # Each terminal line within a step shows one block's name.
                        # Block 0 -> line 0, Block 1 -> line 1, ...
                        # Wraps if more blocks than step_h lines.
                        show_idx = line_in_step % n
                        show_blk = all_blks[show_idx]
                        # Only print something on the first n lines per step
                        # (avoids double-printing for tall blocks)
                        if line_in_step < n:
                            pfx = "►" if id(show_blk) in self.selected_ids else ""
                            txt = pfx + show_blk.name
                        else:
                            txt = ""
                        # Style from the top (first) solid block
                        if is_cursor:
                            style = _cursor_on(top.color_idx)
                        elif id(top) in self.selected_ids:
                            style = _selected_style(top.color_idx)
                        elif id(top) in conflict_ids:
                            style = S_CONFLICT
                        elif top.transparent:
                            style = _dim(top.color_idx)
                        else:
                            style = _solid(top.color_idx)

                    segs.append(Segment(txt[:cw].center(cw), style))
                else:
                    style = S_CURSOR if is_cursor else S_EMPTY
                    segs.append(Segment(" " * cw, style))

        segs.append(Segment("│", S_BORDER))
        used = row_lw + sum(col_widths) + len(vis_cols) + 1
        if used < W: segs.append(Segment(" " * (W - used), S_EMPTY))
        return Strip(segs)

    def _render_status(self, W: int) -> Strip:
        if self.flash_mode:
            n_conflict = len(self._get_conflict_ids())
            msg = (f"  ◼ FLASH MODE — all hidden/overlapping blocks visible  │  "
                   f"{len(self.table.blocks)} blocks total  │  "
                   f"{'⚠ ' + str(n_conflict // 2) + ' pairs overlapping' if n_conflict else '✓ no overlaps'}  │  "
                   f"f or Esc to exit")
            return Strip([Segment(msg.ljust(W)[:W], Style(bgcolor="dark_red", color="bright_white", bold=True))])
        if self.mode == MODE_COLOR and self.color_block is not None:
            segs: list[Segment] = [Segment("  Color: ", S_STATUS)]
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
                   f"j/k height  l/h width  H/J/K/L move anchor  Enter confirm  Esc cancel")
            return Strip([Segment(msg.ljust(W)[:W], S_STATUS)])
        if self.mode == MODE_GRAB:
            name = self.grabbed.name if self.grabbed else "?"
            cf   = self._conflict_set  # show stale is fine
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
                   f"Esc exit  (blocks under cursor are highlighted)")
            return Strip([Segment(msg.ljust(W)[:W], S_STATUS)])

        # Normal + conflicts warning
        cids = self._get_conflict_ids()
        overlap_warn = "  ⚠ OVERLAPPING BLOCKS" if cids else ""
        style = S_ERR if (self.status_err or cids) else S_STATUS
        txt   = (self.status + overlap_warn).ljust(W)[:W]
        return Strip([Segment(txt, style)])

    # ── Input dispatch ────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        # Flash mode: any movement key also works; f or Esc exits
        if self.flash_mode and event.key == "escape":
            self.flash_mode = False; self.status = _HINT; self.status_err = False
            self._scroll_to_cursor(); self.refresh(); return
        if   self.mode == MODE_PROMPT: self._key_prompt(event)
        elif self.mode == MODE_CMD:    self._key_cmd(event)
        elif self.mode == MODE_SIZING: self._key_sizing(event)
        elif self.mode == MODE_COLOR:  self._key_color(event)
        elif self.mode == MODE_VISUAL: self._key_visual(event)
        else:                          self._key_normal(event)   # NORMAL / GRAB / MGRB
        self._clamp_cursor_for_grab()
        self._scroll_to_cursor()
        self.refresh()

    # ── Normal / grab / multi-grab mode ──────────────────────────────────────

    def _key_normal(self, event: events.Key) -> None:  # noqa: C901
        k  = event.key
        ch = event.character or ""
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

        # Movement (normal + grab + multi-grab share hjkl)
        if k == "h":
            self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "l":
            self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "j":
            self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif k == "k":
            self.cursor_row = max(0, self.cursor_row - 1)

        elif k == "space":
            if self.mode == MODE_GRAB:
                self._drop_single()
            elif self.mode == MODE_MGRB:
                self._drop_multi()
            elif self.selected_ids:
                self._start_multi_grab()
            else:
                self._pickup_single()

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

        # Escape also exits flash mode
        elif k == "escape" and self.flash_mode:
            self.flash_mode = False; self.status = _HINT; self.status_err = False

        # Block ops (only in NORMAL — not while grabbing)
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
            elif ch == "V": self.mode = MODE_VISUAL; self.status = "  Visual selection"
            elif k == "o": self._cmd_add_row(below=True)
            elif k == "O": self._cmd_add_row(below=False)
            elif k == "d": self._cmd_delete_row()
            elif k == "i": self._cmd_add_col(right=False)
            elif k == "I": self._cmd_add_col(right=True)
            elif k == "D": self._cmd_delete_col()
            elif k == "minus" or ch == "-":
                s.zoom_h = max(0.25, round(s.zoom_h - 0.25, 2))
                s.zoom_w = max(0.25, round(s.zoom_w - 0.25, 2))
                self.status = f"  Zoom {s.zoom_h:.2f}×"
            elif ch in ("+", "="):
                s.zoom_h = min(8.0, round(s.zoom_h + 0.25, 2))
                s.zoom_w = min(8.0, round(s.zoom_w + 0.25, 2))
                self.status = f"  Zoom {s.zoom_h:.2f}×"
            elif ch == '"': self._open_in_vim()
            elif k == "question_mark" or ch == "?":
                self.app.push_screen(HelpScreen())
            elif k == "colon" or ch == ":":
                self.mode = MODE_CMD; self.cmd_buf = ":"
                self._in_tab_cycle = False

    # ── Visual selection mode ─────────────────────────────────────────────────

    def _key_visual(self, event: events.Key) -> None:
        k  = event.key
        nc = len(self.table.columns)
        nr = len(self.table.rows)
        ns = nr * self.settings.height_steps

        if k == "h":   self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "l": self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "j": self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif k == "k": self.cursor_row = max(0, self.cursor_row - 1)
        elif k == "space":
            if self.selected_ids:
                self._start_multi_grab(); return
        elif k == "escape":
            self.selected_ids.clear(); self.mode = MODE_NORMAL
            self.status = "  Selection cleared."; self.status_err = False; return
        elif event.character == "V":
            self.selected_ids.clear(); self.mode = MODE_NORMAL
            self.status = "  Visual mode off."; return

        # Paint selection at current cursor position
        block = self._block_at(self.cursor_row, self.cursor_col)
        if block: self.selected_ids.add(id(block))

    # ── Command mode ──────────────────────────────────────────────────────────

    def _key_cmd(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""

        if k == "tab":
            self._do_tab_complete(); return

        # Any non-tab key resets tab cycle
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
            self._tab_prefix     = self.cmd_buf
            self._tab_candidates = [c for c in _CMD_COMPLETIONS
                                     if c.startswith(self._tab_prefix)]
            self._tab_idx        = 0
            self._in_tab_cycle   = True
        if self._tab_candidates:
            self.cmd_buf   = self._tab_candidates[self._tab_idx % len(self._tab_candidates)]
            self._tab_idx += 1

    def _exec_cmd(self) -> None:  # noqa: C901
        raw   = self.cmd_buf.strip()
        parts = raw.split()
        s     = self.settings

        if raw in (":q", ":wq", ":x"):   self._save(); self.app.exit(); return
        if raw == ":q!":                   self.app.exit(); return
        if raw == ":w":
            self._save(); self.status = f"  Saved → {self.filepath or '(no file)'}"; return
        if raw == ":check":               self._cmd_check(); return
        if raw == ":flash":
            self._cmd_toggle_flash(); return
        if raw == ":set transpose":
            self._cmd_transpose(); return

        if raw == ":set wrap":
            s.block_wrap = True
            self.status = "  Block wrap ON — blocks may extend past table height into next col"; return
        if raw == ":set nowrap":
            s.block_wrap = False; self.status = "  Block wrap OFF — blocks clamped to table"; return
        if raw == ":set home":
            s.zoom_h = 1.0; s.zoom_w = 1.0
            s.max_visible_cols = None; s.max_visible_rows = None
            self.view_row_off = 0; self.view_col_off = 0
            self.status = "  Home: zoom reset, all rows/cols visible"; return

        if len(parts) == 3 and parts[0] == ":set":
            try:   val = int(parts[2])
            except ValueError:
                self.status = f"  Bad value: {parts[2]}"; self.status_err = True; return
            if parts[1] == "width":
                s.max_visible_cols = max(1, val); self.view_col_off = 0
                self.status = f"  Visible columns: {s.max_visible_cols}"; return
            if parts[1] == "height":
                s.max_visible_rows = max(1, val); self.view_row_off = 0
                self.status = f"  Visible rows: {s.max_visible_rows}"; return
            if parts[1] == "tolerance":
                unit_pos = self.cursor_row / s.height_steps
                s.height_steps = max(1, val)
                self.cursor_row = round(unit_pos * s.height_steps)
                self.status = (f"  Tolerance: {s.height_steps} steps/unit "
                               f"(min {1/s.height_steps:.3g} units)"); return

        self.status = f"  Unknown: {raw}"; self.status_err = True

    def _save(self) -> None:
        if self.filepath:
            save_yaml(self.filepath, self.table, self.settings)

    # ── Prompt mode ───────────────────────────────────────────────────────────

    def _key_prompt(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        p = self.prompt
        # Guard: if prompt was cleared externally but mode wasn't reset, self-heal
        if p is None:
            self.mode = MODE_NORMAL
            return
        if k == "escape":
            # Restore sizing_target if mid-edit-prompt
            if self.sizing_target is not None and self.sizing_target not in self.table.blocks:
                self.table.blocks.append(self.sizing_target)
                self.sizing_target = None
            self.sizing_block = None
            self.prompt = None; self.mode = MODE_NORMAL
            self.status = "  Cancelled."; self.status_err = False
        elif k == "enter":
            if p.submit():
                cb = p.callback; vals = p.values[:]
                # Reset BOTH prompt and mode before cb() so any exception
                # in the callback can't leave mode stuck at MODE_PROMPT
                self.prompt = None
                self.mode   = MODE_NORMAL
                self.status = _HINT
                try:
                    cb(vals)
                except Exception as exc:
                    self.status     = f"  Error: {exc}"
                    self.status_err = True
        elif k == "backspace": p.buf = p.buf[:-1]
        elif ch and ch.isprintable(): p.buf += ch

    def _prompt(self, steps: list[str], cb: Callable,
                defaults: Optional[list[str]] = None) -> None:
        self.prompt = Prompt(steps=steps, defaults=defaults or [""] * len(steps),
                             values=[], step=0, buf="", callback=cb)
        self.mode = MODE_PROMPT

    # ── Sizing mode ───────────────────────────────────────────────────────────

    def _cmd_start_sizing(self, new: bool) -> None:
        hs    = self.settings.height_steps
        min_h = 1 / hs

        if new:
            cidx = self._next_color()
            self.sizing_block  = Block(name="New Block", height=min_h, width=1,
                                       row=self.cursor_row / hs, col=self.cursor_col,
                                       color_idx=cidx)
            self.sizing_target = None
            def got_name(vals: list[str]) -> None:
                self.sizing_block.name = vals[0] or "New Block"
                self.mode = MODE_SIZING
            self._prompt(["Block name (then resize with hjkl, Enter to place)"], got_name)
        else:
            block = self._block_at(self.cursor_row, self.cursor_col)
            if block is None:
                self.status = "  No block at cursor."; self.status_err = True; return
            self.sizing_target = block
            self.sizing_block  = copy.copy(block)
            self.table.blocks.remove(block)
            # Move cursor to block's top-left so it doesn't jump
            self.cursor_row = round(block.row * hs)
            self.cursor_col = block.col
            self.mode = MODE_SIZING

    def _key_sizing(self, event: events.Key) -> None:
        k  = event.key; ch = event.character or ""
        sb = self.sizing_block
        hs = self.settings.height_steps
        min_h = 1 / hs
        nc = len(self.table.columns)
        nr = len(self.table.rows)
        ns = nr * hs

        if k == "escape":
            if self.sizing_target is not None:
                self.table.blocks.append(self.sizing_target)
            self.sizing_block = None; self.sizing_target = None
            self.mode = MODE_NORMAL; self.status = "  Cancelled."; self.status_err = False
        elif k == "enter":
            step, ci = self.cursor_row, self.cursor_col
            if not self._in_bounds(sb, step, ci) and not self.settings.block_wrap:
                self.status = "  ✗ Out of bounds."; self.status_err = True; return
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
            if cf: msg += "  ⚠ (overlapping)"
            self.sizing_block = None; self.sizing_target = None
            self.mode = MODE_NORMAL; self.status = msg; self.status_err = cf
        # Resize
        elif k == "l": sb.width = min(nc - self.cursor_col, sb.width + 1)
        elif k == "h": sb.width = max(1, sb.width - 1)
        elif k == "j": sb.height = round(sb.height + min_h, 10)
        elif k == "k": sb.height = max(min_h, round(sb.height - min_h, 10))
        # Move anchor (shift+hjkl)
        elif ch == "H": self.cursor_col = max(0, self.cursor_col - 1)
        elif ch == "L": self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif ch == "J": self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif ch == "K": self.cursor_row = max(0, self.cursor_row - 1)

    # ── Rename block (Shift+E) ───────────────────────────────────────────────────

    def _cmd_rename_block(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        def done(vals: list[str]) -> None:
            block.name = vals[0] or block.name
            self.status = f"  Renamed: {block.name}"; self.status_err = False
        self._prompt(["New name"], done, defaults=[block.name])

    # ── Flash mode (f / :flash) ───────────────────────────────────────────────

    def _cmd_toggle_flash(self) -> None:
        self.flash_mode = not self.flash_mode
        if self.flash_mode:
            self._invalidate_conflicts()
            n = len(self.table.blocks)
            self.status = f"  FLASH ON — {n} blocks rendered  │  f or Esc to exit"
        else:
            self.status = _HINT
        self.status_err = False

    # ── Transpose (T / :set transpose) ───────────────────────────────────────

    def _cmd_transpose(self) -> None:
        """Swap row and column axes symmetrically.
        Calling twice restores original orientation (within rounding).
        Block row↔col and height↔width are exchanged."""
        hs = self.settings.height_steps
        # Swap axis labels
        self.table.rows, self.table.columns = self.table.columns, self.table.rows
        # Remap every block: new_row = old_col, new_col = round(old_row)
        # new_height = old_width (cols → row units 1:1), new_width = round(old_height)
        for b in self.table.blocks:
            old_row, old_col     = b.row,    b.col
            old_height, old_width = b.height, b.width
            b.row    = float(old_col)
            b.col    = max(0, min(len(self.table.columns) - 1, round(old_row)))
            b.height = float(old_width)
            b.width  = max(1, round(old_height))
        # Swap cursor position too
        old_cr, old_cc      = self.cursor_row, self.cursor_col
        self.cursor_row     = old_cc * hs
        self.cursor_col     = min(len(self.table.columns) - 1, old_cr // hs)
        self.view_row_off   = 0
        self.view_col_off   = 0
        self._invalidate_conflicts()
        nr, nc = len(self.table.rows), len(self.table.columns)
        self.status = f"  Transposed — now {nr} rows × {nc} cols  (T again to restore)"
        self.status_err = False

    # ── Color pick ────────────────────────────────────────────────────────────

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
            self.status = "  Color updated."; self.status_err = False

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_mouse_down(self, event: events.MouseDown) -> None:
        cell = self._mouse_to_cell(event.x, event.y)
        if cell is None: return
        abs_step, ci = cell

        if self.mode == MODE_GRAB and self.grabbed is not None:
            gs = abs_step - self.grab_offset_row
            gc = ci - self.grab_offset_col
            self.cursor_row = abs_step; self.cursor_col = ci
            self._clamp_cursor_for_grab()
            gs = self.cursor_row - self.grab_offset_row
            gc = self.cursor_col - self.grab_offset_col
            self.grabbed.row = gs / self.settings.height_steps; self.grabbed.col = gc
            self._invalidate_conflicts()
            cids = self._get_conflict_ids()
            self.status = ("  Placed ⚠ OVERLAPPING" if id(self.grabbed) in cids
                           else "  Placed.")
            self.status_err = bool(cids and id(self.grabbed) in cids)
            self.table.blocks.append(self.grabbed)
            self.grabbed = None; self.mode = MODE_NORMAL
        elif self.mode == MODE_MGRB:
            self.cursor_row = abs_step; self.cursor_col = ci
            self._drop_multi()
        elif self.mode == MODE_NORMAL:
            block = self._block_at(abs_step, ci)
            if block:
                self.grabbed          = block
                self.grab_offset_row  = abs_step - round(block.row * self.settings.height_steps)
                self.grab_offset_col  = ci - block.col
                self.cursor_row = abs_step; self.cursor_col = ci
                self.table.blocks.remove(block)
                self.mode = MODE_GRAB
                self.status = f"  Grabbed [{block.name}]"; self.status_err = False

        self._clamp_cursor_for_grab()
        self._scroll_to_cursor(); self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.mode not in (MODE_GRAB, MODE_MGRB): return
        cell = self._mouse_to_cell(event.x, event.y)
        if cell is None: return
        self.cursor_row, self.cursor_col = cell
        self._clamp_cursor_for_grab()
        self._scroll_to_cursor(); self.refresh()

    def _mouse_to_cell(self, x: int, y: int) -> Optional[tuple[int, int]]:
        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        H  = self.size.height; hs = self.settings.height_steps; nr = len(self.table.rows)
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
        if block:
            hs = self.settings.height_steps
            self.grabbed          = block
            self.grab_offset_row  = self.cursor_row - round(block.row * hs)
            self.grab_offset_col  = self.cursor_col - block.col
            self.table.blocks.remove(block)
            self.mode = MODE_GRAB
            self.status = f"  Grabbed [{block.name}]"; self.status_err = False
        else:
            self.status = "  No block at cursor."; self.status_err = True

    def _drop_single(self) -> None:
        gs = self.cursor_row - self.grab_offset_row
        gc = self.cursor_col - self.grab_offset_col
        hs = self.settings.height_steps
        self.grabbed.row = gs / hs; self.grabbed.col = gc
        self.table.blocks.append(self.grabbed)
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        cf   = id(self.grabbed) in cids
        self.status = (f"  Placed [{self.grabbed.name}]  ⚠ OVERLAPPING — :check for details"
                       if cf else f"  Placed [{self.grabbed.name}]")
        self.status_err = cf
        self.grabbed = None; self.mode = MODE_NORMAL

    # ── Multi-grab / drop ─────────────────────────────────────────────────────

    def _start_multi_grab(self) -> None:
        selected = [b for b in self.table.blocks if id(b) in self.selected_ids]
        if not selected: return
        hs = self.settings.height_steps
        self.grabbed_group = selected
        self.grp_offsets   = [(round(b.row * hs) - self.cursor_row,
                               b.col - self.cursor_col) for b in selected]
        for b in selected: self.table.blocks.remove(b)
        self.selected_ids.clear()
        self.mode = MODE_MGRB
        self.status = f"  Grabbed {len(selected)} blocks — hjkl move  space drop  Esc cancel"

    def _drop_multi(self) -> None:
        hs  = self.settings.height_steps
        for i, gb in enumerate(self.grabbed_group):
            row_off, col_off = self.grp_offsets[i]
            gb.row = (self.cursor_row + row_off) / hs
            gb.col =  self.cursor_col + col_off
            self.table.blocks.append(gb)
        self.grabbed_group = []; self.grp_offsets = []
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        self.status = ("  Group placed  ⚠ OVERLAPPING — :check for details"
                       if cids else "  Group placed.")
        self.status_err = bool(cids)
        self.mode = MODE_NORMAL

    # ── Yank / paste ──────────────────────────────────────────────────────────

    def _cmd_yank(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        self.clipboard = copy.copy(block)
        self.status = f"  Yanked: {block.name}"; self.status_err = False

    def _cmd_paste(self) -> None:
        if self.clipboard is None:
            self.status = "  Nothing in clipboard."; self.status_err = True; return
        hs = self.settings.height_steps
        nb = copy.copy(self.clipboard)
        nb.row = self.cursor_row / hs; nb.col = self.cursor_col
        nb.color_idx = self._next_color()
        self.table.blocks.append(nb)
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        cf   = id(nb) in cids
        self.status = f"  Pasted: {nb.name}" + ("  ⚠ OVERLAPPING" if cf else "")
        self.status_err = cf

    # ── Block delete / transparent ────────────────────────────────────────────

    def _cmd_delete_block(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        def done(v: list[str]) -> None:
            if v[0].lower() == "y":
                self.table.blocks.remove(block); self._invalidate_conflicts()
                self.status = f"  Deleted: {block.name}"; self.status_err = False
            else: self.status = "  Cancelled."
        self._prompt([f"Delete '{block.name}'? (y/n)"], done)

    def _cmd_toggle_transparent(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor."; self.status_err = True; return
        block.transparent = not block.transparent; self._invalidate_conflicts()
        self.status = f"  {block.name} → {'transparent' if block.transparent else 'solid'}"
        self.status_err = False

    # ── Row / column commands ─────────────────────────────────────────────────

    def _cmd_add_row(self, below: bool) -> None:
        hs = self.settings.height_steps; unit_i = self.cursor_row // hs
        n  = len(self.table.rows); ref = self.table.rows[min(unit_i, n - 1)]
        ins = unit_i + (1 if below else 0)
        def done(v: list[str]) -> None:
            label = v[0] or f"Row {ins + 1}"
            self.table.rows.insert(ins, label)
            for b in self.table.blocks:
                if b.row >= ins: b.row += 1.0
            if not below:
                self.cursor_row = min(self.cursor_row + hs, len(self.table.rows) * hs - 1)
            self._invalidate_conflicts(); self.status = f"  Added row: {label}"; self.status_err = False
        self._prompt([f"Label ({'after' if below else 'before'} '{ref}')"], done)

    def _cmd_delete_row(self) -> None:
        hs = self.settings.height_steps; unit_i = self.cursor_row // hs
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
            self.cursor_row = min(self.cursor_row, len(self.table.rows) * hs - 1)
            self._invalidate_conflicts(); self.status = f"  Deleted row: {label}"; self.status_err = False
        self._prompt([f"Delete row '{label}'? (y/n)"], done)

    def _cmd_add_col(self, right: bool) -> None:
        ci = self.cursor_col; nc = len(self.table.columns)
        ref = self.table.columns[min(ci, nc - 1)]; ins = ci + (1 if right else 0)
        def done(v: list[str]) -> None:
            label = v[0] or f"Col {ins + 1}"
            self.table.columns.insert(ins, label)
            for b in self.table.blocks:
                if b.col >= ins: b.col += 1
            if not right:
                self.cursor_col = min(self.cursor_col + 1, len(self.table.columns) - 1)
            self._invalidate_conflicts(); self.status = f"  Added column: {label}"; self.status_err = False
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
                if b.col > ci:             b.col -= 1; keep.append(b)
                elif b.col <= ci < b.col + b.width:
                    b.width -= 1
                    if b.width >= 1: keep.append(b)
                else: keep.append(b)
            self.table.blocks = keep
            self.cursor_col = min(self.cursor_col, len(self.table.columns) - 1)
            self._invalidate_conflicts(); self.status = f"  Deleted column: {label}"; self.status_err = False
        self._prompt([f"Delete column '{label}'? (y/n)"], done)

    # ── Check ─────────────────────────────────────────────────────────────────

    def _cmd_check(self) -> None:
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        if not cids:
            self.status = "  ✓ No overlapping solid blocks."; self.status_err = False; return
        names = list(dict.fromkeys(b.name for b in self.table.blocks if id(b) in cids))
        self.status = "  ✗ Overlapping: " + "  ↔  ".join(names); self.status_err = True

    # ── Vim edit ──────────────────────────────────────────────────────────────

    def _open_in_vim(self) -> None:
        if not self.filepath:
            self.status = "  No file — save with :w first."; self.status_err = True; return
        self._save()
        self.run_worker(self._vim_worker)

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
    HelpScreen { align: center middle; background: rgba(0,0,0,0.8); }
    HelpScreen Static { background: $surface; padding: 1 2; border: round $primary; }
    """
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, table: TableData, settings: Settings, filepath: Optional[str]) -> None:
        super().__init__()
        self._table = table; self._settings = settings; self._filepath = filepath

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
        if filepath: save_yaml(filepath, table, settings)
    TablePlanApp(table, settings, filepath).run()


if __name__ == "__main__":
    main()
