#!/usr/bin/env python3
"""
tableplan v0.1 — vim-style terminal table organizer
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from textual.app import App, ComposeResult
from textual.widget import Widget
from textual import events
from textual.strip import Strip
from rich.segment import Segment
from rich.style import Style


# ─────────────────────────────────────────────────────────────────────────────
#  Data model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Block:
    """A movable item that occupies space on the table."""
    name: str
    height: float   # in units; must be a multiple of 0.5
    width: int      # number of columns spanned
    row: float      # top-left row position in units (0-based)
    col: int        # top-left column index  (0-based)


@dataclass
class TableData:
    """A single table: axis labels + placed blocks."""
    name: str
    columns: list[str]
    rows: list[str]
    blocks: list[Block]


# ─────────────────────────────────────────────────────────────────────────────
#  Hard-coded demo  (YAML persistence comes next)
# ─────────────────────────────────────────────────────────────────────────────

DEMO = TableData(
    name="Weekly Schedule",
    columns=["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
    rows=["8:00am", "9:00am", "10:00am", "11:00am", "12:00pm"],
    blocks=[
        Block("Dog Walk",  0.5, 1, 0.0, 0),
        Block("Standup",   0.5, 5, 1.0, 0),
        Block("Deep Work", 2.0, 2, 2.0, 2),
        Block("Lunch",     1.0, 1, 4.0, 1),
    ],
)


# ─────────────────────────────────────────────────────────────────────────────
#  Styles
# ─────────────────────────────────────────────────────────────────────────────

S_BORDER  = Style(color="bright_black")
S_HEADER  = Style(color="cyan", bold=True)
S_LABEL   = Style(color="white")
S_BLOCK   = Style(color="black", bgcolor="green")
S_GRABBED = Style(color="black", bgcolor="yellow")
S_INVALID = Style(color="white", bgcolor="red")
S_CURSOR  = Style(color="white", bgcolor="blue", bold=True)
S_EMPTY   = Style()
S_STATUS  = Style(color="bright_white")
S_ERR     = Style(color="red", bold=True)

MSG_DEFAULT = "  hjkl move  │  space grab/drop  │  esc cancel  │  :q quit"


# ─────────────────────────────────────────────────────────────────────────────
#  Grid widget
# ─────────────────────────────────────────────────────────────────────────────

class GridWidget(Widget):
    """Renders the table and handles all interaction."""

    can_focus = True

    def __init__(self, table: TableData) -> None:
        super().__init__()
        self.table     = table
        self.cursor_row = 0        # position in half-units (0 = top of row 0)
        self.cursor_col = 0        # column index
        self.grabbed: Optional[Block] = None
        self.cmd_mode   = False
        self.cmd_buf    = ""
        self.status     = MSG_DEFAULT
        self.status_err = False

    # ── Layout ───────────────────────────────────────────────────────────────

    def _layout(self) -> tuple[int, int, list[int]]:
        """
        Derive cell dimensions from the current terminal size.
        Returns (half_h, row_lw, col_widths).

        half_h     – terminal lines per 0.5 unit of grid height
        row_lw     – character width of the row-label column
        col_widths – per-column character widths
        """
        W, H = self.size.width, self.size.height
        n_rows = len(self.table.rows)
        n_cols = len(self.table.columns)

        # Row-label column: widest label + 2 padding chars
        row_lw = max((len(r) for r in self.table.rows), default=5) + 2

        # Per-column width: widest single word in header or any block label
        col_widths: list[int] = []
        for ci in range(n_cols):
            words = self.table.columns[ci].split()
            for b in self.table.blocks:
                if b.col <= ci < b.col + b.width:
                    words += b.name.split()
            col_widths.append(max((len(w) for w in words), default=3) + 2)

        # Shrink columns proportionally if they overflow terminal width
        n_seps  = n_cols + 1                       # │ characters
        avail_w = W - row_lw - n_seps
        total_w = sum(col_widths)
        if total_w > avail_w > 0:
            scale     = avail_w / total_w
            col_widths = [max(3, int(cw * scale)) for cw in col_widths]

        # Half-unit height: fill available height evenly
        # Reserve 1 line for the column header + 1 for the status bar
        avail_h = max(1, H - 2)
        half_h  = max(1, avail_h // (n_rows * 2))

        return half_h, row_lw, col_widths

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _block_at(self, hr: int, ci: int) -> Optional[Block]:
        """Return whichever block occupies (half_row, col), ignoring grabbed."""
        for b in self.table.blocks:
            if b is self.grabbed:
                continue
            if b.col <= ci < b.col + b.width:
                bs = int(b.row * 2)
                be = int((b.row + b.height) * 2)
                if bs <= hr < be:
                    return b
        return None

    def _can_place(self, b: Block, hr: int, ci: int) -> bool:
        """True if block b fits at top-left (half_row hr, col ci) with no overlap."""
        nr  = len(self.table.rows)
        nc  = len(self.table.columns)
        bh  = int(b.height * 2)

        # Boundary check
        if ci < 0 or ci + b.width > nc:
            return False
        if hr < 0 or hr + bh > nr * 2:
            return False

        # Overlap check against every other placed block
        for ob in self.table.blocks:
            if ob is b:
                continue
            obs = int(ob.row * 2)
            obe = int((ob.row + ob.height) * 2)
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

        # ── Status / command bar (last line) ─────────────────────────────────
        if y == H - 1:
            if self.cmd_mode:
                txt = self.cmd_buf.ljust(self.size.width)[: self.size.width]
                return Strip([Segment(txt, S_STATUS)])
            style = S_ERR if self.status_err else S_STATUS
            txt   = self.status.ljust(self.size.width)[: self.size.width]
            return Strip([Segment(txt, style)])

        # ── Column header row (y == 0) ────────────────────────────────────────
        if y == 0:
            segs: list[Segment] = [Segment(" " * row_lw, S_EMPTY)]
            for ci in range(n_cols):
                cw = col_widths[ci]
                segs.append(Segment("│", S_BORDER))
                segs.append(Segment(
                    self.table.columns[ci][:cw].center(cw), S_HEADER
                ))
            segs.append(Segment("│", S_BORDER))
            return Strip(segs)

        # ── Grid body ─────────────────────────────────────────────────────────
        body_y       = y - 1
        hr           = body_y // half_h        # half-unit index
        line_in_half = body_y % half_h         # line within that half-unit

        if hr >= n_rows * 2:
            return Strip([Segment(" " * self.size.width, S_EMPTY)])

        unit_i        = hr // 2
        is_unit_start = (hr % 2 == 0) and (line_in_half == 0)

        segs = []

        # Row-label column
        if is_unit_start and unit_i < len(self.table.rows):
            lbl = self.table.rows[unit_i].ljust(row_lw)[:row_lw]
            segs.append(Segment(lbl, S_LABEL))
        else:
            segs.append(Segment(" " * row_lw, S_EMPTY))

        # Data columns
        for ci in range(n_cols):
            cw        = col_widths[ci]
            is_cursor = (hr == self.cursor_row and ci == self.cursor_col)
            block     = self._block_at(hr, ci)

            segs.append(Segment("│", S_BORDER))

            # ── Ghost: preview of the grabbed block at cursor position ─────
            cell_rendered = False
            if self.grabbed is not None:
                gr_s = self.cursor_row
                gr_e = gr_s + int(self.grabbed.height * 2)
                gc_s = self.cursor_col
                gc_e = gc_s + self.grabbed.width
                if gr_s <= hr < gr_e and gc_s <= ci < gc_e:
                    valid   = self._can_place(self.grabbed, self.cursor_row, self.cursor_col)
                    style   = S_GRABBED if valid else S_INVALID
                    total_l = int(self.grabbed.height * 2) * half_h
                    line_ig = (hr - gr_s) * half_h + line_in_half
                    mid     = max(0, total_l // 2)
                    txt     = self.grabbed.name if line_ig == mid else ""
                    segs.append(Segment(txt[:cw].center(cw), style))
                    cell_rendered = True

            # ── Normal cell content ────────────────────────────────────────
            if not cell_rendered:
                if block is not None:
                    bs      = int(block.row * 2)
                    total_l = int(block.height * 2) * half_h
                    line_ib = (hr - bs) * half_h + line_in_half
                    mid     = max(0, total_l // 2)
                    txt     = block.name if line_ib == mid else ""
                    style   = S_CURSOR if is_cursor else S_BLOCK
                    segs.append(Segment(txt[:cw].center(cw), style))
                else:
                    style = S_CURSOR if (is_cursor and self.grabbed is None) else S_EMPTY
                    segs.append(Segment(" " * cw, style))

        segs.append(Segment("│", S_BORDER))
        return Strip(segs)

    # ── Input ────────────────────────────────────────────────────────────────

    def on_key(self, event: events.Key) -> None:
        if self.cmd_mode:
            self._key_cmd(event)
        else:
            self._key_normal(event)
        self.refresh()

    def _key_normal(self, event: events.Key) -> None:
        k  = event.key
        ch = event.character or ""
        nr = len(self.table.rows)
        nc = len(self.table.columns)

        if k == "h":
            self.cursor_col = max(0, self.cursor_col - 1)
        elif k == "l":
            self.cursor_col = min(nc - 1, self.cursor_col + 1)
        elif k == "j":
            self.cursor_row = min(nr * 2 - 1, self.cursor_row + 1)
        elif k == "k":
            self.cursor_row = max(0, self.cursor_row - 1)
        elif k == "space":
            self._toggle_grab()
        elif k == "escape":
            if self.grabbed is not None:
                self.grabbed     = None
                self.status      = "  Grab cancelled.  " + MSG_DEFAULT
                self.status_err  = False
        elif k == "colon" or ch == ":":
            self.cmd_mode   = True
            self.cmd_buf    = ":"
            self.status_err = False

    def _key_cmd(self, event: events.Key) -> None:
        k  = event.key
        ch = event.character or ""

        if k == "escape":
            self.cmd_mode = False
            self.cmd_buf  = ""
            self.status   = MSG_DEFAULT
        elif k == "enter":
            self._exec_cmd()
            self.cmd_mode = False
            self.cmd_buf  = ""
        elif k == "backspace":
            self.cmd_buf = self.cmd_buf[:-1]
            if not self.cmd_buf:
                self.cmd_mode = False
        elif ch and ch.isprintable():
            self.cmd_buf += ch

    def _toggle_grab(self) -> None:
        if self.grabbed is not None:
            if self._can_place(self.grabbed, self.cursor_row, self.cursor_col):
                self.grabbed.row = self.cursor_row / 2.0
                self.grabbed.col = self.cursor_col
                self.grabbed     = None
                self.status      = "  Placed.  " + MSG_DEFAULT
                self.status_err  = False
            else:
                self.status     = "  ✗ Cannot place here — find a clear spot first."
                self.status_err = True
        else:
            for b in self.table.blocks:
                bs = int(b.row * 2)
                be = int((b.row + b.height) * 2)
                if (b.col <= self.cursor_col < b.col + b.width
                        and bs <= self.cursor_row < be):
                    self.grabbed    = b
                    self.status     = (
                        f"  Grabbed [{b.name}]  │  "
                        f"hjkl move  │  space drop  │  esc cancel"
                    )
                    self.status_err = False
                    return
            self.status     = "  No block at cursor."
            self.status_err = True

    def _exec_cmd(self) -> None:
        cmd = self.cmd_buf.strip()
        if cmd in (":q", ":wq", ":x"):
            self.app.exit()          # TODO: save to YAML before exit
        else:
            self.status     = f"  Unknown command: {cmd}"
            self.status_err = True


# ─────────────────────────────────────────────────────────────────────────────
#  Application
# ─────────────────────────────────────────────────────────────────────────────

class TablePlanApp(App):
    CSS = """
    Screen {
        background: $surface;
    }
    GridWidget {
        width: 100%;
        height: 100%;
    }
    """

    def compose(self) -> ComposeResult:
        yield GridWidget(DEMO)

    def on_mount(self) -> None:
        self.query_one(GridWidget).focus()


if __name__ == "__main__":
    TablePlanApp().run()
