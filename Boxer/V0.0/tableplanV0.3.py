#!/usr/bin/env python3
"""
tableplan v0.4  —  vim-style terminal table organizer

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

_PALETTE: list[tuple[str, str]] = [   # (bg, fg)
    ("green",       "black"),   # 0
    ("blue",        "white"),   # 1
    ("dark_magenta","white"),   # 2
    ("dark_cyan",   "black"),   # 3
    ("red3",        "white"),   # 4
    ("yellow",      "black"),   # 5
    ("spring_green2","black"),  # 6
    ("dark_blue",   "white"),   # 7
    ("magenta",     "black"),   # 8
    ("cyan",        "black"),   # 9
    ("orange3",     "black"),   # a (10)
    ("purple",      "white"),   # b (11)
]

def _solid(ci: int) -> Style:
    bg, fg = _PALETTE[ci % len(_PALETTE)]; return Style(bgcolor=bg, color=fg, bold=True)

def _dim(ci: int) -> Style:
    bg, _  = _PALETTE[ci % len(_PALETTE)]; return Style(bgcolor=bg, color="bright_black")

def _sel(ci: int) -> Style:                                   # cursor on block
    bg, fg = _PALETTE[ci % len(_PALETTE)]
    return Style(bgcolor="white", color=bg, bold=True, underline=True)

S_CONFLICT= Style(bgcolor="red",    color="bright_white", bold=True)   # always red
S_GHOST_OK= Style(bgcolor="yellow", color="black")
S_GHOST_CF= Style(bgcolor="dark_orange3", color="white")               # conflict ghost
S_GHOST_OB= Style(bgcolor="red",    color="white")                     # out-of-bounds ghost
S_BORDER  = Style(color="bright_black")
S_HEADER  = Style(color="cyan",  bold=True)
S_LABEL   = Style(color="white")
S_CURSOR  = Style(bgcolor="blue",color="white", bold=True)
S_EMPTY   = Style()
S_STATUS  = Style(color="bright_white")
S_ERR     = Style(color="red",   bold=True)

_PALETTE_KEYS = "0123456789ab"


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


@dataclass
class Settings:
    height_steps:     int           = 2      # subdivisions per row unit
    zoom_h:           float         = 1.0
    zoom_w:           float         = 1.0
    block_wrap:       bool          = False  # blocks can spill to next column
    max_visible_cols: Optional[int] = None
    max_visible_rows: Optional[int] = None


# ─────────────────────────────────────────────────────────────────────────────
#  YAML persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_yaml(path: str) -> tuple[TableData, Settings]:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    t = data["table"]
    table = TableData(name=t["name"], columns=list(t["columns"]), rows=list(t["rows"]))
    for bd in data.get("blocks", []):
        table.blocks.append(Block(
            name=str(bd["name"]), height=float(bd.get("height",1.0)),
            width=int(bd.get("width",1)), row=float(bd.get("row",0.0)),
            col=int(bd.get("col",0)), transparent=bool(bd.get("transparent",False)),
            color_idx=int(bd.get("color_idx",0)),
        ))
    sd = data.get("settings", {})
    settings = Settings(
        height_steps    =int(sd.get("height_steps",2)),
        zoom_h          =float(sd.get("zoom_h",1.0)),
        zoom_w          =float(sd.get("zoom_w",1.0)),
        block_wrap      =bool(sd.get("block_wrap",False)),
        max_visible_cols=sd.get("max_visible_cols"),
        max_visible_rows=sd.get("max_visible_rows"),
    )
    return table, settings


def save_yaml(path: str, table: TableData, settings: Settings) -> None:
    sd: dict = {"height_steps":settings.height_steps,"zoom_h":settings.zoom_h,
                "zoom_w":settings.zoom_w,"block_wrap":settings.block_wrap}
    if settings.max_visible_cols is not None: sd["max_visible_cols"]=settings.max_visible_cols
    if settings.max_visible_rows is not None: sd["max_visible_rows"]=settings.max_visible_rows
    data={"table":{"name":table.name,"columns":table.columns,"rows":table.rows},
          "settings":sd,
          "blocks":[{"name":b.name,"height":b.height,"width":b.width,
                     "row":b.row,"col":b.col,"transparent":b.transparent,
                     "color_idx":b.color_idx} for b in table.blocks]}
    with open(path,"w",encoding="utf-8") as f:
        yaml.dump(data,f,default_flow_style=False,allow_unicode=True,sort_keys=False)


def _demo_table() -> tuple[TableData, Settings]:
    t = TableData(
        name="Weekly Schedule",
        columns=["Monday","Tuesday","Wednesday","Thursday","Friday"],
        rows=["8:00am","9:00am","10:00am","11:00am","12:00pm"],
        blocks=[
            Block("Dog Walk", 0.5,1,0.0,0,color_idx=0),
            Block("Standup",  0.5,5,1.0,0,color_idx=1),
            Block("Deep Work",2.0,2,2.0,2,color_idx=2),
            Block("Lunch",    1.0,1,4.0,1,color_idx=3),
        ],
    )
    return t, Settings()


# ─────────────────────────────────────────────────────────────────────────────
#  Help text
# ─────────────────────────────────────────────────────────────────────────────

HELP_TEXT = """
╔══════════════════════════════════════════════════════════════════╗
║                    tableplan  —  controls                        ║
╠══════════════════════════════════════╦═══════════════════════════╣
║  NAVIGATION                          ║  BLOCKS                   ║
║  h/l        move cursor left/right   ║  space  grab / drop       ║
║  j/k        move cursor down/up      ║  a      add new block     ║
║  (scrolls automatically)             ║  e      edit block        ║
╠══════════════════════════════════════║  x      delete block      ║
║  SIZING MODE (after a or e)          ║  v      toggle transp.    ║
║  l / h      wider / narrower         ║  y      yank (copy)       ║
║  j / k      taller / shorter         ║  p      paste copy        ║
║  Enter      confirm                  ║  c      change color      ║
║  Esc        cancel                   ╠═══════════════════════════╣
╠══════════════════════════════════════║  ROWS & COLUMNS           ║
║  ZOOM                                ║  o / O  add row below/up  ║
║  +          zoom in                  ║  i / I  col left/right    ║
║  -          zoom out                 ║  d      delete row        ║
╠══════════════════════════════════════║  D      delete column     ║
║  COMMANDS                            ╠═══════════════════════════╣
║  :w         save                     ║  MOUSE                    ║
║  :q         save & quit              ║  click   grab/drop block  ║
║  :q!        quit without save        ║  drag    move while held  ║
║  ZZ         save & quit (shortcut)   ╠═══════════════════════════╣
║  "          open YAML in $EDITOR     ║  DISPLAY                  ║
║  ?          this help screen         ║  Overlap shown in red     ║
╠══════════════════════════════════════║  Transp. shown dimmed     ║
║  :set wrap          block wrap on    ║  Grabbed shown yellow     ║
║  :set nowrap        block wrap off   ╚═══════════════════════════╝
║  :set width N       visible columns
║  :set height N      visible rows
║  :set tolerance N   steps/unit (2=0.5, 4=0.25 ...)
║  :set home          reset zoom, show all
║  :check             list overlapping blocks
╚══════════════════════════════════════╝

Press any key to close.
"""


# ─────────────────────────────────────────────────────────────────────────────
#  Help screen
# ─────────────────────────────────────────────────────────────────────────────

class HelpScreen(Screen):
    CSS = "Screen { align: center middle; } Static { width: auto; }"
    def compose(self) -> ComposeResult:
        yield Static(HELP_TEXT)
    def on_key(self, _: events.Key) -> None:
        self.app.pop_screen()


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
        self.values.append(val); self.buf=""; self.step+=1
        return self.step >= len(self.steps)


# ─────────────────────────────────────────────────────────────────────────────
#  Modes
# ─────────────────────────────────────────────────────────────────────────────

MODE_NORMAL  = "normal"
MODE_GRAB    = "grab"
MODE_SIZING  = "sizing"    # interactive block resize (a / e)
MODE_COLOR   = "color"     # color-picker for c
MODE_CMD     = "cmd"
MODE_PROMPT  = "prompt"


# ─────────────────────────────────────────────────────────────────────────────
#  Hint bar text
# ─────────────────────────────────────────────────────────────────────────────

_HINT = ("  hjkl:move  spc:grab  a:add  e:edit  x:del  v:transp  "
         "y:yank  p:paste  c:color  o/O:row  i/I:col  d/D:del  -/+:zoom  "
         "\":vim  ?:help  ZZ/:w:save  :check")


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
        self.cursor_row     = 0     # absolute steps
        self.cursor_col     = 0     # absolute column index
        self.view_row_off   = 0     # first visible step
        self.view_col_off   = 0     # first visible column
        self.mode           = MODE_NORMAL
        self.grabbed: Optional[Block]  = None
        self.sizing_block:  Optional[Block]  = None   # preview in sizing mode
        self.sizing_target: Optional[Block]  = None   # None=new, else=edit
        self.color_block:   Optional[Block]  = None
        self.clipboard:     Optional[Block]  = None
        self.prompt:        Optional[Prompt] = None
        self.cmd_buf        = ""
        self.status         = _HINT
        self.status_err     = False
        self.last_key       = ""
        self._conflict_set: set[int] = set()
        self._conflict_dirty         = True
        # Layout cache — always recomputed at the start of scroll/render
        self._step_h      = 1
        self._row_lw      = 8
        self._col_widths: list[int] = []
        self._vis_cols:   list[int] = []
        self._n_vis_steps = 1

    # ── Layout ───────────────────────────────────────────────────────────────

    def _layout(self) -> tuple[int, int, list[int], list[int], int]:
        """
        Derive geometry from terminal size + settings.
        All visible columns are given the SAME width (uniform grid).
        Returns (step_h, row_lw, col_widths, vis_cols, n_vis_steps)
        and updates self._* cache fields.
        """
        W, H   = self.size.width, self.size.height
        n_rows = len(self.table.rows)
        n_cols = len(self.table.columns)
        s      = self.settings

        # Row-label column
        row_lw = max((len(r) for r in self.table.rows), default=5) + 2

        # ── Determine visible columns ─────────────────────────────────────
        # Natural uniform width = widest word across ALL columns & block labels
        all_words: list[str] = []
        for ci in range(n_cols):
            all_words += self.table.columns[ci].split()
        for b in self.table.blocks:
            all_words += b.name.split()
        nat_w = max((len(w) for w in all_words), default=3) + 2
        # Apply zoom
        base_cw = max(3, int(nat_w * s.zoom_w))

        # How many columns fit from view_col_off?
        avail_w   = W - row_lw - 1          # subtract the leftmost separator
        max_fit   = max(1, avail_w // (base_cw + 1))  # +1 for │
        vis_count = min(max_fit, n_cols - self.view_col_off)
        if s.max_visible_cols is not None:
            vis_count = min(vis_count, s.max_visible_cols)
        vis_count = max(1, vis_count)
        vis_cols  = list(range(self.view_col_off, self.view_col_off + vis_count))

        # Expand/shrink all columns uniformly to fill avail_w exactly
        n_sep    = vis_count                          # one │ per column (trailing)
        avail_d  = max(vis_count * 3, avail_w - n_sep)
        col_w    = avail_d // vis_count
        col_w    = max(3, col_w)
        # Distribute leftover pixels to the first columns
        leftover = avail_d - col_w * vis_count
        col_widths = [col_w + (1 if i < leftover else 0) for i in range(vis_count)]

        # ── Vertical step height ──────────────────────────────────────────
        n_steps  = n_rows * s.height_steps
        avail_h  = max(1, H - 2)               # reserve header + status
        base_sh  = max(1, avail_h // max(1, n_steps))
        step_h   = max(1, int(base_sh * s.zoom_h))

        n_vis_s  = min(n_steps, avail_h // step_h)
        if s.max_visible_rows is not None:
            n_vis_s = min(n_vis_s, s.max_visible_rows * s.height_steps)
        n_vis_s  = max(1, n_vis_s)

        # Cache
        self._step_h      = step_h
        self._row_lw      = row_lw
        self._col_widths  = col_widths
        self._vis_cols    = vis_cols
        self._n_vis_steps = n_vis_s

        return step_h, row_lw, col_widths, vis_cols, n_vis_s

    # ── Scroll ────────────────────────────────────────────────────────────────

    def _scroll_to_cursor(self) -> None:
        # Always recompute layout so scroll uses fresh values
        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        s       = self.settings
        n_rows  = len(self.table.rows)
        n_cols  = len(self.table.columns)
        n_steps = max(1, n_rows * s.height_steps)

        self.cursor_row = max(0, min(self.cursor_row, n_steps - 1))
        self.cursor_col = max(0, min(self.cursor_col, n_cols - 1))

        # Vertical
        if self.cursor_row < self.view_row_off:
            self.view_row_off = self.cursor_row
        elif self.cursor_row >= self.view_row_off + n_vis_s:
            self.view_row_off = self.cursor_row - n_vis_s + 1
        self.view_row_off = max(0, min(self.view_row_off, n_steps - 1))

        # Horizontal
        if self.cursor_col < self.view_col_off:
            self.view_col_off = self.cursor_col
        elif vis_cols and self.cursor_col > vis_cols[-1]:
            self.view_col_off = self.cursor_col - len(vis_cols) + 1
        self.view_col_off = max(0, min(self.view_col_off, n_cols - 1))

    # ── Block helpers ─────────────────────────────────────────────────────────

    def _block_steps(self, b: Block) -> tuple[int, int]:
        hs = self.settings.height_steps
        return round(b.row * hs), round((b.row + b.height) * hs)

    def _block_at(self, abs_step: int, ci: int) -> Optional[Block]:
        found_t: Optional[Block] = None
        for b in self.table.blocks:
            if b is self.grabbed or b is self.sizing_target: continue
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
        hs = self.settings.height_steps
        bh = round(b.height * hs)
        for ob in self.table.blocks:
            if ob is b or ob is self.grabbed or ob is self.sizing_target: continue
            if ob.transparent: continue
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
            for j in range(i+1, len(solid)):
                a, b = solid[i], solid[j]
                as_, ae = self._block_steps(a)
                bs_, be = self._block_steps(b)
                if ((a.col + a.width <= b.col) or (a.col >= b.col + b.width)): continue
                if ((ae <= bs_)               or (as_ >= be)):                  continue
                result.add(id(a)); result.add(id(b))
        self._conflict_set   = result
        self._conflict_dirty = False
        return result

    def _next_color(self) -> int:
        used = {b.color_idx for b in self.table.blocks}
        for i in range(len(_PALETTE)):
            if i not in used: return i
        return len(self.table.blocks) % len(_PALETTE)

    # ── Rendering ────────────────────────────────────────────────────────────

    def render_line(self, y: int) -> Strip:  # noqa: C901
        if self.size.width == 0 or self.size.height == 0:
            return Strip([])

        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        n_rows = len(self.table.rows)
        H, W   = self.size.height, self.size.width
        hs     = self.settings.height_steps

        # ── Status / prompt / command bar ────────────────────────────────────
        if y == H - 1:
            return self._render_status(W)

        # ── Column header ─────────────────────────────────────────────────────
        if y == 0:
            segs: list[Segment] = [Segment(" " * row_lw, S_EMPTY)]
            for i, ci in enumerate(vis_cols):
                cw = col_widths[i]
                segs.append(Segment("│", S_BORDER))
                segs.append(Segment(self.table.columns[ci][:cw].center(cw), S_HEADER))
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

        segs = []
        if show_lbl and unit_i < len(self.table.rows):
            segs.append(Segment(self.table.rows[unit_i].ljust(row_lw)[:row_lw], S_LABEL))
        else:
            segs.append(Segment(" " * row_lw, S_EMPTY))

        for i, ci in enumerate(vis_cols):
            cw        = col_widths[i]
            is_cursor = (abs_step == self.cursor_row and ci == self.cursor_col)
            segs.append(Segment("│", S_BORDER))

            cell_done = False

            # ── Sizing preview ────────────────────────────────────────────────
            if self.mode == MODE_SIZING and self.sizing_block is not None:
                sb  = self.sizing_block
                ss  = self.cursor_row
                se  = ss + round(sb.height * hs)
                sc  = self.cursor_col
                sce = sc + sb.width
                if ss <= abs_step < se and sc <= ci < sce:
                    in_b = self._in_bounds(sb, ss, sc)
                    cf   = self._has_conflict(sb, ss, sc)
                    if not in_b:   style = S_GHOST_OB
                    elif cf:       style = S_GHOST_CF
                    else:          style = S_GHOST_OK
                    tot  = round(sb.height * hs) * step_h
                    lig  = (abs_step - ss) * step_h + line_in_step
                    mid  = max(0, tot // 2)
                    dims = f"{sb.name}  {sb.height}u×{sb.width}c"
                    txt  = dims if lig == mid else ""
                    segs.append(Segment(txt[:cw].center(cw), style))
                    cell_done = True

            # ── Grabbed block ghost ───────────────────────────────────────────
            if not cell_done and self.mode == MODE_GRAB and self.grabbed is not None:
                gs  = self.cursor_row
                ge  = gs + round(self.grabbed.height * hs)
                gc  = self.cursor_col
                gce = gc + self.grabbed.width
                if gs <= abs_step < ge and gc <= ci < gce:
                    in_b = self._in_bounds(self.grabbed, gs, gc)
                    cf   = self._has_conflict(self.grabbed, gs, gc)
                    if not in_b:   style = S_GHOST_OB
                    elif cf:       style = S_GHOST_CF
                    else:          style = S_GHOST_OK
                    tot  = round(self.grabbed.height * hs) * step_h
                    lig  = (abs_step - gs) * step_h + line_in_step
                    txt  = self.grabbed.name if lig == max(0, tot // 2) else ""
                    segs.append(Segment(txt[:cw].center(cw), style))
                    cell_done = True

            # ── Normal block rendering ────────────────────────────────────────
            if not cell_done:
                block = self._block_at(abs_step, ci)
                if block is not None:
                    bs, be = self._block_steps(block)
                    tot = (be - bs) * step_h
                    lib = (abs_step - bs) * step_h + line_in_step
                    txt = block.name if lib == max(0, tot // 2) else ""
                    if is_cursor and self.mode == MODE_NORMAL:
                        style = _sel(block.color_idx)
                    elif block.transparent:
                        style = _dim(block.color_idx)
                    elif id(block) in conflict_ids:
                        style = S_CONFLICT
                    else:
                        style = _solid(block.color_idx)
                    segs.append(Segment(txt[:cw].center(cw), style))
                else:
                    style = S_CURSOR if (is_cursor and self.mode == MODE_NORMAL) else S_EMPTY
                    segs.append(Segment(" " * cw, style))

        segs.append(Segment("│", S_BORDER))
        used = row_lw + sum(col_widths) + len(vis_cols) + 1
        if used < W: segs.append(Segment(" " * (W - used), S_EMPTY))
        return Strip(segs)

    def _render_status(self, W: int) -> Strip:
        """Render the bottom status bar (varies by mode)."""
        # Color pick mode — show swatches
        if self.mode == MODE_COLOR and self.color_block is not None:
            segs: list[Segment] = [Segment("  Color: ", S_STATUS)]
            for i, (bg, fg) in enumerate(_PALETTE):
                key = _PALETTE_KEYS[i]
                cur = "►" if i == self.color_block.color_idx else " "
                segs.append(Segment(f"{cur}{key}", Style(bgcolor=bg, color=fg, bold=True)))
                segs.append(Segment(" ", S_EMPTY))
            segs.append(Segment("  press key to select  Esc cancel", S_STATUS))
            return Strip(segs)

        if self.mode == MODE_PROMPT and self.prompt is not None:
            txt = self.prompt.display().ljust(W)[:W]
            return Strip([Segment(txt, S_STATUS)])

        if self.mode == MODE_CMD:
            txt = self.cmd_buf.ljust(W)[:W]
            return Strip([Segment(txt, S_STATUS)])

        if self.mode == MODE_SIZING and self.sizing_block is not None:
            sb  = self.sizing_block
            hs  = self.settings.height_steps
            msg = (f"  SIZING [{sb.name}]  "
                   f"h:{sb.height:.3g}u  w:{sb.width}col  │  "
                   f"j/k height  l/h width  Enter confirm  Esc cancel")
            return Strip([Segment(msg.ljust(W)[:W], S_STATUS)])

        if self.mode == MODE_GRAB:
            name = self.grabbed.name if self.grabbed else "?"
            msg  = f"  GRAB [{name}]  │  hjkl/mouse move  │  space/click drop  │  Esc cancel"
            return Strip([Segment(msg.ljust(W)[:W], S_STATUS)])

        style = S_ERR if self.status_err else S_STATUS
        return Strip([Segment(self.status.ljust(W)[:W], style)])

    # ── Input dispatch ────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        if   self.mode == MODE_PROMPT: self._key_prompt(event)
        elif self.mode == MODE_CMD:    self._key_cmd(event)
        elif self.mode == MODE_SIZING: self._key_sizing(event)
        elif self.mode == MODE_COLOR:  self._key_color(event)
        elif self.mode in (MODE_NORMAL, MODE_GRAB): self._key_normal(event)
        self._scroll_to_cursor()
        self.refresh()

    # ── Normal / grab mode ────────────────────────────────────────────────────

    def _key_normal(self, event: events.Key) -> None:  # noqa: C901
        k  = event.key
        ch = event.character or ""
        s  = self.settings
        nc = len(self.table.columns)
        nr = len(self.table.rows)
        ns = nr * s.height_steps

        # ZZ shortcut
        if ch == "Z":
            if self.last_key == "Z":
                self._save(); self.app.exit(); return
            self.last_key = "Z"; return
        self.last_key = k

        # Movement
        if k == "h":
            if self.mode == MODE_GRAB:
                self.cursor_col = max(0, self.cursor_col - 1)
            else:
                self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "l":
            self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "j":
            self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif k == "k":
            self.cursor_row = max(0, self.cursor_row - 1)

        # Grab / drop
        elif k == "space":  self._toggle_grab()
        elif k == "escape":
            if self.mode == MODE_GRAB:
                self.grabbed = None; self.mode = MODE_NORMAL
                self.status = "  Grab cancelled."; self.status_err = False

        # Zoom
        elif k == "minus" or ch == "-":
            s.zoom_h = max(0.25, round(s.zoom_h - 0.25, 2))
            s.zoom_w = max(0.25, round(s.zoom_w - 0.25, 2))
            self.status = f"  Zoom {s.zoom_h:.2f}×"; self.status_err = False
        elif ch in ("+", "="):
            s.zoom_h = min(8.0, round(s.zoom_h + 0.25, 2))
            s.zoom_w = min(8.0, round(s.zoom_w + 0.25, 2))
            self.status = f"  Zoom {s.zoom_h:.2f}×"; self.status_err = False

        # Block commands
        elif k == "a": self._cmd_start_sizing(new=True)
        elif k == "e": self._cmd_start_sizing(new=False)
        elif k == "x": self._cmd_delete_block()
        elif k == "v": self._cmd_toggle_transparent()
        elif k == "y": self._cmd_yank()
        elif k == "p": self._cmd_paste()
        elif k == "c": self._cmd_color_pick()

        # Row / column commands
        elif k == "o": self._cmd_add_row(below=True)
        elif k == "O": self._cmd_add_row(below=False)
        elif k == "d": self._cmd_delete_row()
        elif k == "i": self._cmd_add_col(right=False)
        elif k == "I": self._cmd_add_col(right=True)
        elif k == "D": self._cmd_delete_col()

        # Vim edit / help
        elif ch == '"': self._open_in_vim()
        elif k == "question_mark" or ch == "?":
            self.app.push_screen(HelpScreen())

        # Command mode
        elif k == "colon" or ch == ":":
            self.mode = MODE_CMD; self.cmd_buf = ":"

    # ── Command mode ──────────────────────────────────────────────────────────

    def _key_cmd(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        if k == "escape":
            self.mode = MODE_NORMAL; self.cmd_buf = ""; self.status = _HINT
        elif k == "enter":
            self._exec_cmd(); self.mode = MODE_NORMAL; self.cmd_buf = ""
        elif k == "backspace":
            self.cmd_buf = self.cmd_buf[:-1]
            if not self.cmd_buf: self.mode = MODE_NORMAL
        elif ch and ch.isprintable():
            self.cmd_buf += ch

    def _exec_cmd(self) -> None:  # noqa: C901
        raw   = self.cmd_buf.strip()
        parts = raw.split()
        s     = self.settings

        if raw in (":q",":wq",":x"):    self._save(); self.app.exit(); return
        if raw == ":q!":                 self.app.exit(); return
        if raw == ":w":
            self._save(); self.status = f"  Saved → {self.filepath or '(no file)'}"; return
        if raw == ":check":              self._cmd_check(); return

        if raw == ":set wrap":
            s.block_wrap = True
            self.status = "  Block wrap ON — blocks may extend beyond table height into next col"; return
        if raw == ":set nowrap":
            s.block_wrap = False; self.status = "  Block wrap OFF"; return

        if raw == ":set home":
            s.zoom_h = 1.0; s.zoom_w = 1.0
            s.max_visible_cols = None; s.max_visible_rows = None
            self.view_row_off = 0; self.view_col_off = 0
            self.status = "  Home: zoom reset, showing all rows/cols"; return

        if len(parts) == 3 and parts[0] == ":set":
            try:   val = int(parts[2])
            except ValueError:
                self.status = f"  Bad value: {parts[2]}"; self.status_err = True; return
            if parts[1] == "width":
                s.max_visible_cols = max(1, val)
                self.view_col_off  = 0
                self.status = f"  Visible columns: {s.max_visible_cols}  (scroll with h/l)"; return
            if parts[1] == "height":
                s.max_visible_rows = max(1, val)
                self.view_row_off  = 0
                self.status = f"  Visible rows: {s.max_visible_rows}  (scroll with j/k)"; return
            if parts[1] == "tolerance":
                unit_pos        = self.cursor_row / s.height_steps
                s.height_steps  = max(1, val)
                self.cursor_row = round(unit_pos * s.height_steps)
                self.status = (f"  Tolerance: {s.height_steps} steps/unit "
                               f"(min block: {1/s.height_steps:.3g} units)"); return

        if len(parts) == 4 and parts[0] == ":set" and parts[1] == "tolerance":
            try:   hs = max(1, int(parts[2]))
            except ValueError:
                self.status = "  Bad value"; self.status_err = True; return
            unit_pos        = self.cursor_row / s.height_steps
            s.height_steps  = hs; self.cursor_row = round(unit_pos * hs)
            self.status = f"  Tolerance: {hs} steps/unit"; return

        self.status = f"  Unknown command: {raw}"; self.status_err = True

    def _save(self) -> None:
        if self.filepath:
            save_yaml(self.filepath, self.table, self.settings)

    # ── Prompt mode ───────────────────────────────────────────────────────────

    def _key_prompt(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        p = self.prompt
        if k == "escape":
            self.prompt = None; self.mode = MODE_NORMAL
            self.status = "  Cancelled."; self.status_err = False
        elif k == "enter":
            if p.submit():
                cb = p.callback; vals = p.values[:]
                self.prompt = None; self.mode = MODE_NORMAL; self.status = _HINT
                cb(vals)
        elif k == "backspace": p.buf = p.buf[:-1]
        elif ch and ch.isprintable(): p.buf += ch

    def _prompt(self, steps: list[str], cb: Callable, defaults: Optional[list[str]]=None) -> None:
        self.prompt = Prompt(steps=steps, defaults=defaults or [""]*len(steps),
                             values=[], step=0, buf="", callback=cb)
        self.mode = MODE_PROMPT

    # ── Sizing mode ───────────────────────────────────────────────────────────

    def _cmd_start_sizing(self, new: bool) -> None:
        hs  = self.settings.height_steps
        min_h = 1 / hs

        if new:
            # Start with a 1×1 ghost at cursor
            cidx = self._next_color()
            self.sizing_block  = Block(name="New Block", height=min_h, width=1,
                                       row=self.cursor_row/hs, col=self.cursor_col,
                                       color_idx=cidx)
            self.sizing_target = None
            # Ask for name first via one-step prompt then enter sizing
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
            # Temporarily remove target from table so it doesn't interfere with overlap checks
            self.table.blocks.remove(block)
            self.mode = MODE_SIZING

    def _key_sizing(self, event: events.Key) -> None:
        k  = event.key; ch = event.character or ""
        sb = self.sizing_block
        hs = self.settings.height_steps
        min_h = 1 / hs

        if k == "escape":
            # Restore edited block if needed
            if self.sizing_target is not None:
                self.table.blocks.append(self.sizing_target)
            self.sizing_block = None; self.sizing_target = None
            self.mode = MODE_NORMAL; self.status = "  Cancelled."; self.status_err = False
        elif k == "enter":
            step, ci = self.cursor_row, self.cursor_col
            if not self._in_bounds(sb, step, ci):
                self.status = "  ✗ Out of bounds — adjust size or position."; self.status_err = True; return
            if self.sizing_target is not None:
                # Edit: update original block in-place
                self.sizing_target.name   = sb.name
                self.sizing_target.height = sb.height
                self.sizing_target.width  = sb.width
                self.sizing_target.row    = step / hs
                self.sizing_target.col    = ci
                self.table.blocks.append(self.sizing_target)
                self.status = f"  Edited: {sb.name}"
            else:
                # New block
                sb.row = step / hs; sb.col = ci
                self.table.blocks.append(sb)
                self.status = f"  Added: {sb.name}"
            self._invalidate_conflicts()
            self.sizing_block = None; self.sizing_target = None
            self.mode = MODE_NORMAL; self.status_err = False
        elif k == "l":
            nc = len(self.table.columns)
            if self.cursor_col + sb.width < nc:
                sb.width += 1
        elif k == "h":
            sb.width = max(1, sb.width - 1)
        elif k == "j":
            sb.height = round(sb.height + min_h, 10)
        elif k == "k":
            sb.height = max(min_h, round(sb.height - min_h, 10))
        elif k == "H":
            self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "L":
            nc = len(self.table.columns)
            self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "J":
            ns = len(self.table.rows) * self.settings.height_steps
            self.cursor_row = min(ns - 1, self.cursor_row + 1)
        elif k == "K":
            self.cursor_row = max(0, self.cursor_row - 1)

    # ── Color pick mode ───────────────────────────────────────────────────────

    def _cmd_color_pick(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if block is None:
            self.status = "  No block at cursor."; self.status_err = True; return
        self.color_block = block
        self.mode = MODE_COLOR

    def _key_color(self, event: events.Key) -> None:
        k = event.key; ch = event.character or ""
        if k == "escape":
            self.color_block = None; self.mode = MODE_NORMAL; self.status = _HINT; return
        if ch and ch in _PALETTE_KEYS:
            idx = _PALETTE_KEYS.index(ch)
            self.color_block.color_idx = idx
            self.color_block = None; self.mode = MODE_NORMAL
            self.status = "  Color updated."; self.status_err = False

    # ── Mouse ─────────────────────────────────────────────────────────────────

    def on_mouse_down(self, event: events.MouseDown) -> None:
        cell = self._mouse_to_cell(event.x, event.y)
        if cell is None: return
        abs_step, ci = cell
        if self.mode == MODE_GRAB and self.grabbed is not None:
            in_b = self._in_bounds(self.grabbed, abs_step, ci)
            if in_b:
                cf = self._has_conflict(self.grabbed, abs_step, ci)
                self.grabbed.row = abs_step / self.settings.height_steps
                self.grabbed.col = ci
                self._invalidate_conflicts()
                self.status = "  Placed (overlapping — :check to review)" if cf else "  Placed."
                self.status_err = False; self.grabbed = None; self.mode = MODE_NORMAL
            else:
                self.status = "  ✗ Out of bounds."; self.status_err = True
        elif self.mode == MODE_NORMAL:
            block = self._block_at(abs_step, ci)
            if block:
                self.grabbed    = block
                self.cursor_row = abs_step; self.cursor_col = ci
                self.mode       = MODE_GRAB
                self.status     = f"  Grabbed [{block.name}]"
                self.status_err = False
        self._scroll_to_cursor(); self.refresh()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self.mode != MODE_GRAB or self.grabbed is None: return
        cell = self._mouse_to_cell(event.x, event.y)
        if cell is None: return
        self.cursor_row, self.cursor_col = cell
        self._scroll_to_cursor(); self.refresh()

    def _mouse_to_cell(self, x: int, y: int) -> Optional[tuple[int, int]]:
        step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()
        H  = self.size.height
        hs = self.settings.height_steps
        nr = len(self.table.rows)
        if y == 0 or y == H - 1: return None
        body_y       = y - 1
        step_in_view = body_y // step_h
        abs_step     = self.view_row_off + step_in_view
        if step_in_view >= n_vis_s or abs_step >= nr * hs: return None
        if x < row_lw: return None
        cx = x - row_lw
        for i, ci in enumerate(vis_cols):
            cx -= 1
            if cx < 0: return abs_step, ci
            if cx < col_widths[i]: return abs_step, ci
            cx -= col_widths[i]
        return None

    # ── Vim edit ──────────────────────────────────────────────────────────────

    def _open_in_vim(self) -> None:
        if not self.filepath:
            self.status = "  No file — save with :w first."; self.status_err = True; return
        self._save()
        self.run_worker(self._vim_worker)

    async def _vim_worker(self) -> None:
        editor = os.environ.get("EDITOR", "vim")
        # Use sync context manager (compatible with all Textual versions)
        with self.app.suspend():
            subprocess.run([editor, self.filepath])
        try:
            table, settings   = load_yaml(self.filepath)
            self.table        = table
            self.settings     = settings
            self._invalidate_conflicts()
            self.status       = f"  Reloaded from {self.filepath}"
            self.status_err   = False
        except Exception as e:
            self.status       = f"  Reload error: {e}"
            self.status_err   = True
        self.refresh()

    # ── Check ─────────────────────────────────────────────────────────────────

    def _cmd_check(self) -> None:
        self._invalidate_conflicts()
        cids = self._get_conflict_ids()
        if not cids:
            self.status = "  ✓ No overlapping solid blocks."; self.status_err = False; return
        names = list(dict.fromkeys(b.name for b in self.table.blocks if id(b) in cids))
        self.status = "  ✗ Overlapping: " + "  ↔  ".join(names); self.status_err = True

    # ── Grab / drop ───────────────────────────────────────────────────────────

    def _toggle_grab(self) -> None:
        if self.mode == MODE_GRAB and self.grabbed is not None:
            step, ci = self.cursor_row, self.cursor_col
            if not self._in_bounds(self.grabbed, step, ci):
                self.status = "  ✗ Out of bounds."; self.status_err = True; return
            cf = self._has_conflict(self.grabbed, step, ci)
            self.grabbed.row = step / self.settings.height_steps
            self.grabbed.col = ci
            self._invalidate_conflicts()
            self.status = (f"  Placed [{self.grabbed.name}] (overlapping)" if cf
                           else "  Placed.")
            self.status_err = False; self.grabbed = None; self.mode = MODE_NORMAL
        else:
            block = self._block_at(self.cursor_row, self.cursor_col)
            if block:
                self.grabbed = block; self.mode = MODE_GRAB
                self.status  = f"  Grabbed [{block.name}]"; self.status_err = False
            else:
                self.status = "  No block at cursor."; self.status_err = True

    # ── Yank / paste ──────────────────────────────────────────────────────────

    def _cmd_yank(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if block is None:
            self.status = "  No block at cursor."; self.status_err = True; return
        self.clipboard  = copy.copy(block)
        self.status     = f"  Yanked: {block.name}"; self.status_err = False

    def _cmd_paste(self) -> None:
        if self.clipboard is None:
            self.status = "  Nothing in clipboard."; self.status_err = True; return
        nb = copy.copy(self.clipboard)
        hs = self.settings.height_steps
        nb.row = self.cursor_row / hs
        nb.col = self.cursor_col
        nb.color_idx = self._next_color()
        self.table.blocks.append(nb)
        self._invalidate_conflicts()
        self.status = f"  Pasted: {nb.name}"; self.status_err = False

    # ── Block commands ────────────────────────────────────────────────────────

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

    # ── Row commands ──────────────────────────────────────────────────────────

    def _cmd_add_row(self, below: bool) -> None:
        hs = self.settings.height_steps; unit_i = self.cursor_row // hs
        n  = len(self.table.rows); ref = self.table.rows[min(unit_i, n-1)]
        ins = unit_i + (1 if below else 0)
        def done(v: list[str]) -> None:
            label = v[0] or f"Row {ins+1}"
            self.table.rows.insert(ins, label)
            for b in self.table.blocks:
                if b.row >= ins: b.row += 1.0
            if not below:
                self.cursor_row = min(self.cursor_row + hs, len(self.table.rows)*hs - 1)
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
                if b.row < unit_i+1 and b.row+b.height > unit_i: continue
                if b.row >= unit_i+1: b.row -= 1.0
                keep.append(b)
            self.table.blocks = keep
            self.cursor_row = min(self.cursor_row, len(self.table.rows)*hs - 1)
            self._invalidate_conflicts(); self.status = f"  Deleted row: {label}"; self.status_err = False
        self._prompt([f"Delete row '{label}'? (y/n)"], done)

    # ── Column commands ───────────────────────────────────────────────────────

    def _cmd_add_col(self, right: bool) -> None:
        ci = self.cursor_col; nc = len(self.table.columns)
        ref = self.table.columns[min(ci, nc-1)]; ins = ci + (1 if right else 0)
        def done(v: list[str]) -> None:
            label = v[0] or f"Col {ins+1}"
            self.table.columns.insert(ins, label)
            for b in self.table.blocks:
                if b.col >= ins: b.col += 1
            if not right:
                self.cursor_col = min(self.cursor_col+1, len(self.table.columns)-1)
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
                if b.col > ci:         b.col -= 1; keep.append(b)
                elif b.col <= ci < b.col+b.width:
                    b.width -= 1
                    if b.width >= 1: keep.append(b)
                else: keep.append(b)
            self.table.blocks = keep
            self.cursor_col = min(self.cursor_col, len(self.table.columns)-1)
            self._invalidate_conflicts(); self.status = f"  Deleted column: {label}"; self.status_err = False
        self._prompt([f"Delete column '{label}'? (y/n)"], done)


# ─────────────────────────────────────────────────────────────────────────────
#  Application
# ─────────────────────────────────────────────────────────────────────────────

class TablePlanApp(App):
    CSS = """
    Screen     { background: $surface; }
    GridWidget { width: 100%; height: 100%; }
    HelpScreen { align: center middle; background: rgba(0,0,0,0.7); }
    HelpScreen Static { background: $surface; padding: 1 2; border: round $primary; }
    """
    ENABLE_COMMAND_PALETTE = False
    SCREENS = {"help": HelpScreen}

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
        if filepath: save_yaml(filepath, table, settings)
    TablePlanApp(table, settings, filepath).run()


if __name__ == "__main__":
    main()
