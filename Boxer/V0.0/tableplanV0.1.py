#!/usr/bin/env python3
"""
tableplan v0.2 — vim-style terminal table organizer

Usage:
    python tableplan.py              # in-memory demo (nothing saved)
    python tableplan.py myplan.yaml  # load or create a YAML table
"""
from __future__ import annotations

import os
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


@dataclass
class TableData:
    name:    str
    columns: list[str]
    rows:    list[str]
    blocks:  list[Block] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
#  YAML persistence
# ─────────────────────────────────────────────────────────────────────────────

def load_yaml(path: str) -> TableData:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    t = data["table"]
    table = TableData(name=t["name"], columns=list(t["columns"]), rows=list(t["rows"]))
    for bd in data.get("blocks", []):
        table.blocks.append(Block(
            name        = str(bd["name"]),
            height      = float(bd.get("height", 1.0)),
            width       = int(bd.get("width", 1)),
            row         = float(bd.get("row", 0.0)),
            col         = int(bd.get("col", 0)),
            transparent = bool(bd.get("transparent", False)),
        ))
    return table


def save_yaml(path: str, table: TableData) -> None:
    data = {
        "table": {"name": table.name, "columns": table.columns, "rows": table.rows},
        "blocks": [
            {"name": b.name, "height": b.height, "width": b.width,
             "row": b.row, "col": b.col, "transparent": b.transparent}
            for b in table.blocks
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _demo_table() -> TableData:
    return TableData(
        name    = "Weekly Schedule",
        columns = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
        rows    = ["8:00am", "9:00am", "10:00am", "11:00am", "12:00pm"],
        blocks  = [
            Block("Dog Walk",  0.5, 1, 0.0, 0),
            Block("Standup",   0.5, 5, 1.0, 0),
            Block("Deep Work", 2.0, 2, 2.0, 2),
            Block("Lunch",     1.0, 1, 4.0, 1),
        ],
    )


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
        self.values.append(val)
        self.buf   = ""
        self.step += 1
        return self.step >= len(self.steps)


# ─────────────────────────────────────────────────────────────────────────────
#  Styles
# ─────────────────────────────────────────────────────────────────────────────

S_BORDER  = Style(color="bright_black")
S_HEADER  = Style(color="cyan", bold=True)
S_LABEL   = Style(color="white")
S_BLOCK   = Style(color="black",        bgcolor="green")
S_TRANSP  = Style(color="bright_black", bgcolor="dark_cyan")
S_GRABBED = Style(color="black",        bgcolor="yellow")
S_INVALID = Style(color="white",        bgcolor="red")
S_CURSOR  = Style(color="white",        bgcolor="blue", bold=True)
S_EMPTY   = Style()
S_STATUS  = Style(color="bright_white")
S_ERR     = Style(color="red", bold=True)

_HINT = (
    "  hjkl move  │  space grab  │  a add  │  e edit  │  x del  │  v transp  │"
    "  o/O row  │  i/I col  │  d/D del row/col  │  :w save  │  :q quit"
)


# ─────────────────────────────────────────────────────────────────────────────
#  Grid widget
# ─────────────────────────────────────────────────────────────────────────────

class GridWidget(Widget):
    can_focus = True

    def __init__(self, table: TableData, filepath: Optional[str]) -> None:
        super().__init__()
        self.table      = table
        self.filepath   = filepath
        self.cursor_row = 0
        self.cursor_col = 0
        self.grabbed:   Optional[Block]  = None
        self.prompt:    Optional[Prompt] = None
        self.cmd_mode   = False
        self.cmd_buf    = ""
        self.status     = _HINT
        self.status_err = False

    # ── Layout ───────────────────────────────────────────────────────────────

    def _layout(self) -> tuple[int, int, list[int]]:
        W, H   = self.size.width, self.size.height
        n_rows = len(self.table.rows)
        n_cols = len(self.table.columns)

        row_lw = max((len(r) for r in self.table.rows), default=5) + 2

        col_widths: list[int] = []
        for ci in range(n_cols):
            words = self.table.columns[ci].split()
            for b in self.table.blocks:
                if b.col <= ci < b.col + b.width:
                    words += b.name.split()
            col_widths.append(max((len(w) for w in words), default=3) + 2)

        avail_w = W - row_lw - (n_cols + 1)
        total_w = sum(col_widths)
        if total_w > avail_w > 0:
            scale      = avail_w / total_w
            col_widths = [max(3, int(cw * scale)) for cw in col_widths]

        avail_h = max(1, H - 2)
        half_h  = max(1, avail_h // (n_rows * 2))
        return half_h, row_lw, col_widths

    # ── Block helpers ─────────────────────────────────────────────────────────

    def _block_at(self, hr: int, ci: int, solid_only: bool = False) -> Optional[Block]:
        found_transp: Optional[Block] = None
        for b in self.table.blocks:
            if b is self.grabbed:
                continue
            if b.col <= ci < b.col + b.width:
                bs = int(b.row * 2)
                be = int((b.row + b.height) * 2)
                if bs <= hr < be:
                    if not b.transparent:
                        return b
                    elif not solid_only and found_transp is None:
                        found_transp = b
        return found_transp

    def _can_place(self, b: Block, hr: int, ci: int) -> bool:
        nr = len(self.table.rows)
        nc = len(self.table.columns)
        bh = int(b.height * 2)
        if ci < 0 or ci + b.width > nc:   return False
        if hr < 0 or hr + bh > nr * 2:    return False
        for ob in self.table.blocks:
            if ob is b or ob.transparent:  continue
            obs = int(ob.row * 2);  obe = int((ob.row + ob.height) * 2)
            col_clear = (ci + b.width <= ob.col) or (ci >= ob.col + ob.width)
            row_clear = (hr + bh <= obs)          or (hr >= obe)
            if not col_clear and not row_clear:
                return False
        return True

    # ── Rendering ────────────────────────────────────────────────────────────

    def render_line(self, y: int) -> Strip:  # noqa: C901
        if self.size.width == 0 or self.size.height == 0:
            return Strip([])

        half_h, row_lw, col_widths = self._layout()
        n_rows = len(self.table.rows)
        n_cols = len(self.table.columns)
        H      = self.size.height

        # Status / prompt / command bar
        if y == H - 1:
            if self.prompt is not None:
                txt = self.prompt.display().ljust(self.size.width)[:self.size.width]
                return Strip([Segment(txt, S_STATUS)])
            if self.cmd_mode:
                txt = self.cmd_buf.ljust(self.size.width)[:self.size.width]
                return Strip([Segment(txt, S_STATUS)])
            style = S_ERR if self.status_err else S_STATUS
            txt   = self.status.ljust(self.size.width)[:self.size.width]
            return Strip([Segment(txt, style)])

        # Column header row
        if y == 0:
            segs: list[Segment] = [Segment(" " * row_lw, S_EMPTY)]
            for ci in range(n_cols):
                cw = col_widths[ci]
                segs.append(Segment("│", S_BORDER))
                segs.append(Segment(self.table.columns[ci][:cw].center(cw), S_HEADER))
            segs.append(Segment("│", S_BORDER))
            return Strip(segs)

        # Grid body
        body_y       = y - 1
        hr           = body_y // half_h
        line_in_half = body_y % half_h

        if hr >= n_rows * 2:
            return Strip([Segment(" " * self.size.width, S_EMPTY)])

        unit_i        = hr // 2
        is_unit_start = (hr % 2 == 0) and (line_in_half == 0)

        segs = []
        if is_unit_start and unit_i < len(self.table.rows):
            segs.append(Segment(self.table.rows[unit_i].ljust(row_lw)[:row_lw], S_LABEL))
        else:
            segs.append(Segment(" " * row_lw, S_EMPTY))

        for ci in range(n_cols):
            cw        = col_widths[ci]
            is_cursor = (hr == self.cursor_row and ci == self.cursor_col)
            segs.append(Segment("│", S_BORDER))

            # Ghost (grabbed block preview)
            cell_done = False
            if self.grabbed is not None:
                gr_s = self.cursor_row
                gr_e = gr_s + int(self.grabbed.height * 2)
                gc_s = self.cursor_col
                gc_e = gc_s + self.grabbed.width
                if gr_s <= hr < gr_e and gc_s <= ci < gc_e:
                    valid = self._can_place(self.grabbed, self.cursor_row, self.cursor_col)
                    style = S_GRABBED if valid else S_INVALID
                    tot   = int(self.grabbed.height * 2) * half_h
                    lig   = (hr - gr_s) * half_h + line_in_half
                    txt   = self.grabbed.name if lig == max(0, tot // 2) else ""
                    segs.append(Segment(txt[:cw].center(cw), style))
                    cell_done = True

            if not cell_done:
                block = self._block_at(hr, ci)
                if block is not None:
                    bs   = int(block.row * 2)
                    tot  = int(block.height * 2) * half_h
                    lib  = (hr - bs) * half_h + line_in_half
                    txt  = block.name if lib == max(0, tot // 2) else ""
                    if is_cursor:
                        style = S_CURSOR
                    elif block.transparent:
                        style = S_TRANSP
                    else:
                        style = S_BLOCK
                    segs.append(Segment(txt[:cw].center(cw), style))
                else:
                    style = S_CURSOR if (is_cursor and self.grabbed is None) else S_EMPTY
                    segs.append(Segment(" " * cw, style))

        segs.append(Segment("│", S_BORDER))
        return Strip(segs)

    # ── Input dispatch ────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        if self.prompt is not None:
            self._key_prompt(event)
        elif self.cmd_mode:
            self._key_cmd(event)
        else:
            self._key_normal(event)
        self.refresh()

    def _key_normal(self, event: events.Key) -> None:  # noqa: C901
        k  = event.key
        ch = event.character or ""
        nr = len(self.table.rows)
        nc = len(self.table.columns)

        if   k == "h":     self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "l":     self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "j":     self.cursor_row = min(nr * 2 - 1, self.cursor_row + 1)
        elif k == "k":     self.cursor_row = max(0, self.cursor_row - 1)
        elif k == "space": self._toggle_grab()
        elif k == "escape" and self.grabbed:
            self.grabbed = None;  self.status = "  Grab cancelled.";  self.status_err = False
        elif k == "colon" or ch == ":":
            self.cmd_mode = True;  self.cmd_buf = ":";  self.status_err = False
        elif k == "a":  self._cmd_add_block()
        elif k == "e":  self._cmd_edit_block()
        elif k == "x":  self._cmd_delete_block()
        elif k == "v":  self._cmd_toggle_transparent()
        elif k == "o":  self._cmd_add_row(below=True)
        elif k == "O":  self._cmd_add_row(below=False)
        elif k == "d":  self._cmd_delete_row()
        elif k == "i":  self._cmd_add_col(right=False)
        elif k == "I":  self._cmd_add_col(right=True)
        elif k == "D":  self._cmd_delete_col()

    def _key_cmd(self, event: events.Key) -> None:
        k = event.key;  ch = event.character or ""
        if   k == "escape":    self.cmd_mode = False;  self.cmd_buf = "";  self.status = _HINT
        elif k == "enter":     self._exec_cmd();  self.cmd_mode = False;  self.cmd_buf = ""
        elif k == "backspace": self.cmd_buf = self.cmd_buf[:-1]; (not self.cmd_buf and setattr(self, "cmd_mode", False))
        elif ch and ch.isprintable(): self.cmd_buf += ch

    def _exec_cmd(self) -> None:
        cmd = self.cmd_buf.strip()
        if cmd in (":q", ":wq", ":x"):
            self._save();  self.app.exit()
        elif cmd == ":q!":
            self.app.exit()
        elif cmd == ":w":
            self._save()
            self.status     = f"  Saved → {self.filepath or '(no file)'}"
            self.status_err = False
        else:
            self.status     = f"  Unknown command: {cmd}"
            self.status_err = True

    def _save(self) -> None:
        if self.filepath:
            save_yaml(self.filepath, self.table)

    def _key_prompt(self, event: events.Key) -> None:
        k = event.key;  ch = event.character or ""
        p = self.prompt
        if k == "escape":
            self.prompt = None;  self.status = "  Cancelled.";  self.status_err = False
        elif k == "enter":
            if p.submit():
                cb = p.callback;  vals = p.values[:]
                self.prompt = None;  self.status = _HINT
                cb(vals)
        elif k == "backspace":
            p.buf = p.buf[:-1]
        elif ch and ch.isprintable():
            p.buf += ch

    def _prompt(self, steps: list[str], cb: Callable[[list[str]], None],
                defaults: Optional[list[str]] = None) -> None:
        self.prompt = Prompt(
            steps=steps, defaults=defaults or [""] * len(steps),
            values=[], step=0, buf="", callback=cb,
        )

    # ── Grab / drop ───────────────────────────────────────────────────────────

    def _toggle_grab(self) -> None:
        if self.grabbed is not None:
            if self._can_place(self.grabbed, self.cursor_row, self.cursor_col):
                self.grabbed.row = self.cursor_row / 2.0
                self.grabbed.col = self.cursor_col
                self.grabbed     = None
                self.status      = "  Placed.  " + _HINT
                self.status_err  = False
            else:
                self.status = "  ✗ Cannot place here.";  self.status_err = True
        else:
            block = self._block_at(self.cursor_row, self.cursor_col)
            if block:
                self.grabbed    = block
                self.status     = f"  Grabbed [{block.name}]  │  hjkl move  │  space drop  │  esc cancel"
                self.status_err = False
            else:
                self.status = "  No block at cursor.";  self.status_err = True

    # ── Block commands ────────────────────────────────────────────────────────

    def _cmd_add_block(self) -> None:
        hr, ci = self.cursor_row, self.cursor_col
        def done(v: list[str]) -> None:
            name = v[0] or "Unnamed"
            try:    h = max(0.5, round(float(v[1]) * 2) / 2)
            except: h = 1.0
            try:    w = max(1, int(v[2]))
            except: w = 1
            nb = Block(name=name, height=h, width=w, row=hr / 2.0, col=ci)
            if self._can_place(nb, hr, ci):
                self.table.blocks.append(nb);  self.status = f"  Added: {name}";  self.status_err = False
            else:
                self.status = "  ✗ No room — move cursor and try again.";  self.status_err = True
        self._prompt(["Block name", "Height in units (e.g. 0.5)", "Width in columns"], done)

    def _cmd_edit_block(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor.";  self.status_err = True;  return
        def done(v: list[str]) -> None:
            block.name = v[0] or block.name
            try:    block.height = max(0.5, round(float(v[1]) * 2) / 2)
            except: pass
            try:    block.width  = max(1, int(v[2]))
            except: pass
            self.status = f"  Edited: {block.name}";  self.status_err = False
        self._prompt(["Name", "Height", "Width"], done,
                     defaults=[block.name, str(block.height), str(block.width)])

    def _cmd_delete_block(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor.";  self.status_err = True;  return
        def done(v: list[str]) -> None:
            if v[0].lower() == "y":
                self.table.blocks.remove(block);  self.status = f"  Deleted: {block.name}";  self.status_err = False
            else:
                self.status = "  Cancelled."
        self._prompt([f"Delete '{block.name}'? (y/n)"], done)

    def _cmd_toggle_transparent(self) -> None:
        block = self._block_at(self.cursor_row, self.cursor_col)
        if not block:
            self.status = "  No block at cursor.";  self.status_err = True;  return
        block.transparent = not block.transparent
        self.status = f"  {block.name} → {'transparent' if block.transparent else 'solid'}"
        self.status_err = False

    # ── Row commands ──────────────────────────────────────────────────────────

    def _cmd_add_row(self, below: bool) -> None:
        unit_i   = self.cursor_row // 2
        n        = len(self.table.rows)
        ref      = self.table.rows[min(unit_i, n - 1)]
        insert_i = unit_i + (1 if below else 0)
        side     = "after" if below else "before"
        def done(v: list[str]) -> None:
            label = v[0] or f"Row {insert_i + 1}"
            self.table.rows.insert(insert_i, label)
            for b in self.table.blocks:
                if b.row >= insert_i: b.row += 1.0
            if not below:
                self.cursor_row = min(self.cursor_row + 2, len(self.table.rows) * 2 - 1)
            self.status = f"  Added row: {label}";  self.status_err = False
        self._prompt([f"Label for new row ({side} '{ref}')"], done)

    def _cmd_delete_row(self) -> None:
        unit_i = self.cursor_row // 2
        if len(self.table.rows) <= 1:
            self.status = "  Cannot delete the last row.";  self.status_err = True;  return
        label = self.table.rows[unit_i]
        def done(v: list[str]) -> None:
            if v[0].lower() != "y":
                self.status = "  Cancelled.";  return
            self.table.rows.pop(unit_i)
            keep: list[Block] = []
            for b in self.table.blocks:
                if b.row < unit_i + 1 and b.row + b.height > unit_i: continue
                if b.row >= unit_i + 1: b.row -= 1.0
                keep.append(b)
            self.table.blocks = keep
            self.cursor_row   = min(self.cursor_row, len(self.table.rows) * 2 - 1)
            self.status = f"  Deleted row: {label}";  self.status_err = False
        self._prompt([f"Delete row '{label}'? (y/n)"], done)

    # ── Column commands ───────────────────────────────────────────────────────

    def _cmd_add_col(self, right: bool) -> None:
        ci       = self.cursor_col
        nc       = len(self.table.columns)
        ref      = self.table.columns[min(ci, nc - 1)]
        insert_i = ci + (1 if right else 0)
        side     = "right of" if right else "left of"
        def done(v: list[str]) -> None:
            label = v[0] or f"Col {insert_i + 1}"
            self.table.columns.insert(insert_i, label)
            for b in self.table.blocks:
                if b.col >= insert_i: b.col += 1
            if not right:
                self.cursor_col = min(self.cursor_col + 1, len(self.table.columns) - 1)
            self.status = f"  Added column: {label}";  self.status_err = False
        self._prompt([f"Label for new column ({side} '{ref}')"], done)

    def _cmd_delete_col(self) -> None:
        ci = self.cursor_col
        if len(self.table.columns) <= 1:
            self.status = "  Cannot delete the last column.";  self.status_err = True;  return
        label = self.table.columns[ci]
        def done(v: list[str]) -> None:
            if v[0].lower() != "y":
                self.status = "  Cancelled.";  return
            self.table.columns.pop(ci)
            keep: list[Block] = []
            for b in self.table.blocks:
                if b.col > ci:
                    b.col -= 1;  keep.append(b)
                elif b.col <= ci < b.col + b.width:
                    b.width -= 1
                    if b.width >= 1: keep.append(b)
                else:
                    keep.append(b)
            self.table.blocks = keep
            self.cursor_col   = min(self.cursor_col, len(self.table.columns) - 1)
            self.status = f"  Deleted column: {label}";  self.status_err = False
        self._prompt([f"Delete column '{label}'? (y/n)"], done)


# ─────────────────────────────────────────────────────────────────────────────
#  Application
# ─────────────────────────────────────────────────────────────────────────────

class TablePlanApp(App):
    CSS = """
    Screen     { background: $surface; }
    GridWidget { width: 100%; height: 100%; }
    """

    def __init__(self, table: TableData, filepath: Optional[str]) -> None:
        super().__init__()
        self.table    = table
        self.filepath = filepath

    def compose(self) -> ComposeResult:
        yield GridWidget(self.table, self.filepath)

    def on_mount(self) -> None:
        self.title = f"tableplan — {self.filepath}" if self.filepath else "tableplan (demo)"
        self.query_one(GridWidget).focus()


# ─────────────────────────────────────────────────────────────────────────────
#  Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    filepath: Optional[str] = None
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
        table = load_yaml(filepath) if os.path.exists(filepath) else _demo_table()
        if not os.path.exists(filepath):
            save_yaml(filepath, table)   # seed the file immediately
    else:
        table = _demo_table()
    TablePlanApp(table, filepath).run()


if __name__ == "__main__":
    main()
