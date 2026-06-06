Markh


Overview: To create a terminal based TUI for a table organizer/planner. The tui will be run on all devices (linux, windows, mac os, freebsd?). The application will allow users to move "blocks" around on the table. 

How: The program will start in python on a linux machine and migrate from there. We may need to switch to rust for improved compatibaility and for speed. The tables and blocks will be stored inside a yaml file for future use and to allow for multiple tables and continuous refinement of the tables. 

What: 
Table Layout: The table will consist of rows and columns of arbiturary entries. Each entry is counted as a unit. The entry can be numbers (1,2,3,4...) times (12:00pm, 1:00pm, 1300...) dates (3/13/2026, Thursday ...) categories (personal, groceries, etc) etc. These entries will populate the labels of the table.

Blocks: Each block contains a name and length of rows in units. Example: Dog walking 0.5 units. This would populate a block that is .5 of a unit.

Interface: the user will move around these blocks and rearrange them on the table without changing the size of the blocks. 

Notes: Since this is a terminal interface only, I would like to keep the commands similar to vim style of commands. I can provide more of list when necessary of the commands I would like to see.

Let's start slow. Ask me questions as we go.


This is great!
lets get the yaml file ability loaded and the saving. 

Lets also add some more features/commands:
a - prompts for a new block (both category and size in rows and columns) and places it at the current selector position
e - edits the exisiting block that is there  have
x - deletes block (prompts to confirm) 
v- toggles transparancy
o - adds a new row below cursor position (prompts for entry block)
O - adds a new row at the top of cursor position (prompts for entry)
i - adds a new column to the left of cursor position (prompts)
I - adds a new column to the right of cursor position 
d - deletes current row (prompts to confirm)
D - deletes column (prompts to confirm)


Transparancy- this changes the blocks contrast/color and allows the user to put blocks on top of it (Basically a holding ground where it is not deleted but it is also not taking up room in the plot)

MarkA
Prompt 3

This is making a lot of progress. Lets add a few more features:
" - opens up the current yaml file in vim for editing. Would love to return to application on close.
- - "zooms" out making the size of the units (rows, columns, and blocks smaller)
+ - "zooms" in making size of everything larger 
:set wrap - allows blocks to be wrapped from one column to the top of the next column 
:set width ## - Allows user to set number of blocks in width
:set height ## - Allows user to set number of blocks of height
:set tolerance ## ## - Allows user to set the resultion per move (i.e. .5 would be entered as 2  units or .25 would be entered as 4  etc) for both first height and then width (Like a standard matrix)
ZZ - shortcut for write quit

*Add move: as you navigate the cursor to the edge of the table in any direction, if there is more columns or rows past the viewable range it moves to allow those to be shown.

*Add the option to "wrap" blocks from one column to the next

*Add color: Try to make each block a unique color if possible.

*Add mouse interactions to the drag on drop features (click automatically selects and release lets go) of the block under the cursor

Check - runs a quick check and notifies the user what blocks are overlapping.

Lets modify the way it handles overlapping blocks. Instead of blocking it completely, lets just change colors similar to what we have but still allow to set them down. 
Fixes:
Lets make the vertical and horizontal table space use all the avaliable room. Keep the short help menu on the bottom but remove the large space to the right of the table by inlarging the columns and rows to take up the correct amount of space. Scale to fit the current window but if the window is too small to display the words width, simple keep the minimum size and use the new ability to move to allow visibility of the whole table. 


MarkB
Prompt 4:
- Automatically show some form of "error" color when two cells overlap.
- Copy paste commands (yank -y and paste -p)
- c allows changing the color of the current item (manually select)
- :set home - resets zoom to show maximum number of rows and columns while still using the full screen.
- Views still need some work, would perfer to keep all rows and columns same dimensions when possible
- Set row and set column does not work (Just simple does not change the number of items shown)
- :set wrap - not working the way I intended. Intention: when wrap is turned on, blocks can extend paste the current row size by moving to the top of the next column. No wrap prohibits you from moving a block beyond a viable time.
- Make a help menu with list of controls
- when adding or editting a block, provide a updating view that grows the block on the table from the current cursor position using the hjkl keys with enter to set.

When trying to edit the yaml file: 
ERRORS:
│   355 │   │   │   self._run_threaded() if self._thread_worker else self._run_async()                                                           │
│   356 │   │   )                                                                                                                                │
│   357                                                                                                                                          │
│                                                                                                                                                │
│ ╭─────────────────────────────────────────────────── locals ───────────────────────────────────────────────────╮                               │
│ │ self = <Worker ERROR name='_vim_worker' description='<bound method GridWidget._vim_worker of GridWidget()>'> │                               │
│ ╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────╯                               │
│                                                                                                                                                │
│ /home/joshua/python_virtual/lib/python3.13/site-packages/textual/worker.py:339 in _run_async                                                   │
│                                                                                                                                                │
│   336 │   │   │   or hasattr(self._work, "func")                                                                                               │
│   337 │   │   │   and inspect.iscoroutinefunction(self._work.func)                                                                             │
│   338 │   │   ):                                                                                                                               │
│ ❱ 339 │   │   │   return await self._work()                                                                                                    │
│   340 │   │   elif inspect.isawaitable(self._work):                                                                                            │
│   341 │   │   │   return await self._work                                                                                                      │
│   342 │   │   elif callable(self._work):                                                                                                       │
│                                                                                                                                                │
│ ╭─────────────────────────────────────────────────── locals ───────────────────────────────────────────────────╮                               │
│ │ self = <Worker ERROR name='_vim_worker' description='<bound method GridWidget._vim_worker of GridWidget()>'> │                               │
│ ╰──────────────────────────────────────────────────────────────────────────────────────────────────────────────╯                               │
│                                                                                                                                                │
│ /home/joshua/Documents/table_planner/V0.0/tableplanV0.2.py:762 in _vim_worker                                                                  │
│                                                                                                                                                │
│   759 │   async def _vim_worker(self) -> None:                                                                                                 │
│   760 │   │   import asyncio                                                                                                                   │
│   761 │   │   editor = os.environ.get("EDITOR", "vim")                                                                                         │
│ ❱ 762 │   │   async with self.app.suspend():                                                                                                   │
│   763 │   │   │   await asyncio.get_event_loop().run_in_executor(                                                                              │
│   764 │   │   │   │   None, lambda: subprocess.run([editor, self.filepath])                                                                    │
│   765 │   │   │   )                                                                                                                            │
│                                                                                                                                                │
│ ╭────────────────────────────────── locals ───────────────────────────────────╮                                                                │
│ │ asyncio = <module 'asyncio' from '/usr/lib/python3.13/asyncio/__init__.py'> │                                                                │
│ │  editor = 'vim'                                                             │                                                                │
│ │    self = GridWidget()                                                      │                                                                │
│ ╰─────────────────────────────────────────────────────────────────────────────╯                                                                │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
TypeError: '_GeneratorContextManager' object does not support the asynchronous context manager protocol
(python_virtual) joshua@joshual:~/Documents/table_planner/V0.0$ 


MarkC  SMALL
Prompt 5:
- when editing blocks, do not "jump" the block size to align with the current cusor position, instead keep the same block size and move the cursor to the edge before moving the block. 
- when using the set height command, resize the rows to use the entire table area similar to what is done with the columns
- when selecting a block to move, do not move the block to align with the cursor, instead start moving the block from the original position
- tab complete for the commands would be nice 
- :set wrap still does not work as intended, it will not allow blocks to be placed at the edge, when set wrap is off (nowrap) make the cursor not move a selected block outside the table range.
- add ability to select multiple blocks using shift and then moving the cursor over the blocks to allow selecting multiple
- allow placing of blocks overlapping one another but maintain warning in bottom that it is "illegal"

MarkD LARGE 
Prompt 6
- E (shift E) allows for editing the name of the block
- Always show text for block labels even if there is a multiple block collision
- Create a command to flash all blocks to see if any blocks are hiddeno
- Make sure that it is symmetric (tables can go both ways, categories as well) both horizontal and vertical can be used interchangeably


Resolved by adding "##" quotations. NOT IDEAL
error: 
╭────────────────────────────────────────────────────── Traceback (most recent call last) ───────────────────────────────────────────────────────╮
│ /home/joshua/python_virtual/lib/python3.13/site-packages/textual/widget.py:4285 in render_lines                                                │
│                                                                                                                                                │
│   4282 │   │   │   │   Strip.blank(crop.width, self.visual_style.rich_style)                                                                   │
│   4283 │   │   │   ] * crop.height                                                                                                             │
│   4284 │   │   else:                                                                                                                           │
│ ❱ 4285 │   │   │   strips = self._styles_cache.render_widget(self, crop)                                                                       │
│   4286 │   │   return strips                                                                                                                   │
│   4287 │                                                                                                                                       │
│   4288 │   def get_style_at(self, x: int, y: int) -> Style:                                                                                    │
│                                                                                                                                                │
│ ╭─────────────────── locals ────────────────────╮                                                                                              │
│ │ crop = Region(x=0, y=0, width=146, height=40) │                                                                                              │
│ │ self = GridWidget()                           │                                                                                              │
│ ╰───────────────────────────────────────────────╯                                                                                              │
│                                                                                                                                                │
│ /home/joshua/python_virtual/lib/python3.13/site-packages/textual/_styles_cache.py:115 in render_widget                                         │
│                                                                                                                                                │
│   112 │   │                                                                                                                                    │
│   113 │   │   base_background, background = widget.background_colors                                                                           │
│   114 │   │   styles = widget.styles                                                                                                           │
│ ❱ 115 │   │   strips = self.render(                                                                                                            │
│   116 │   │   │   styles,                                                                                                                      │
│   117 │   │   │   widget.region.size,                                                                                                          │
│   118 │   │   │   base_background,                                                                                                             │
│                                                                                                                                                │
│ ╭──────────────────────────────────────────────── locals ────────────────────────────────────────────────╮                                     │
│ │      background = Color(30, 30, 30)                                                                    │                                     │
│ │ base_background = Color(30, 30, 30)                                                                    │                                     │
│ │ border_subtitle = None                                                                                 │                                     │
│ │    border_title = None                                                                                 │                                     │
│ │            crop = Region(x=0, y=0, width=146, height=40)                                               │                                     │
│ │            self = <StylesCache width=146>                                                              │                                     │
│ │          styles = RenderStyles(                                                                        │                                     │
│ │                   │   GridWidget(),                                                                    │                                     │
│ │                   │   background=Color(0, 0, 0, a=0),                                                  │                                     │
│ │                   │   width=Scalar(value=100.0, unit=<Unit.WIDTH: 4>, percent_unit=<Unit.WIDTH: 4>),   │                                     │
│ │                   │   height=Scalar(                                                                   │                                     │
│ │                   │   │   value=100.0,                                                                 │                                     │
│ │                   │   │   unit=<Unit.HEIGHT: 5>,                                                       │                                     │
│ │                   │   │   percent_unit=<Unit.WIDTH: 4>                                                 │                                     │
│ │                   │   ),                                                                               │                                     │
│ │                   │   scrollbar_color=Color(0, 48, 84),                                                │                                     │
│ │                   │   scrollbar_color_hover=Color(0, 60, 106),                                         │                                     │
│ │                   │   scrollbar_color_active=Color(1, 120, 212),                                       │                                     │
│ │                   │   scrollbar_corner_color=Color(0, 0, 0),                                           │                                     │
│ │                   │   scrollbar_background=Color(0, 0, 0),                                             │                                     │
│ │                   │   scrollbar_background_hover=Color(0, 0, 0),                                       │                                     │
│ │                   │   scrollbar_background_active=Color(0, 0, 0),                                      │                                     │
│ │                   │   scrollbar_size_vertical=2,                                                       │                                     │
│ │                   │   scrollbar_size_horizontal=1,                                                     │                                     │
│ │                   │   link_color=Color(255, 255, 255, a=0.87),                                         │                                     │
│ │                   │   auto_link_color=True,                                                            │                                     │
│ │                   │   link_background=Color(0, 0, 0, a=0),                                             │                                     │
│ │                   │   link_style=Style(underline=True),                                                │                                     │
│ │                   │   link_color_hover=Color(255, 255, 255, a=0.87),                                   │                                     │
│ │                   │   auto_link_color_hover=True,                                                      │                                     │
│ │                   │   link_background_hover=Color(1, 120, 212),                                        │                                     │
│ │                   │   link_style_hover=Style(bold=True, underline=False)                               │                                     │
│ │                   )                                                                                    │                                     │
│ │          widget = GridWidget()                                                                         │                                     │
│ ╰────────────────────────────────────────────────────────────────────────────────────────────────────────╯                                     │
│                                                                                                                                                │
│ /home/joshua/python_virtual/lib/python3.13/site-packages/textual/_styles_cache.py:217 in render                                                │
│                                                                                                                                                │
│   214 │   │                                                                                                                                    │
│   215 │   │   for y in crop.line_range:                                                                                                        │
│   216 │   │   │   if is_dirty(y) or y not in self._cache:                                                                                      │
│ ❱ 217 │   │   │   │   strip = render_line(                                                                                                     │
│   218 │   │   │   │   │   styles,                                                                                                              │
│   219 │   │   │   │   │   y,                                                                                                                   │
│   220 │   │   │   │   │   size,                                                                                                                │
│                                                                                                                                                │
│ ╭────────────────────────────────────────────────── locals ──────────────────────────────────────────────────╮                                 │
│ │             _height = 40                                                                                   │                                 │
│ │           add_strip = <built-in method append of list object at 0x7b09f2c47840>                            │                                 │
│ │          ansi_theme = <rich.terminal_theme.TerminalTheme object at 0x7b09f3178830>                         │                                 │
│ │          background = Color(30, 30, 30)                                                                    │                                 │
│ │     base_background = Color(30, 30, 30)                                                                    │                                 │
│ │     border_subtitle = None                                                                                 │                                 │
│ │        border_title = None                                                                                 │                                 │
│ │        content_size = Size(width=146, height=40)                                                           │                                 │
│ │                crop = Region(x=0, y=0, width=146, height=40)                                               │                                 │
│ │             filters = [<textual.filter.ANSIToTruecolor object at 0x7b09f2d78ad0>]                          │                                 │
│ │            is_dirty = <built-in method __contains__ of set object at 0x7b09f2c42c00>                       │                                 │
│ │             opacity = 1.0                                                                                  │                                 │
│ │             padding = Spacing(top=0, right=0, bottom=0, left=0)                                            │                                 │
│ │ render_content_line = <bound method GridWidget.render_line of GridWidget()>                                │                                 │
│ │         render_line = <bound method StylesCache.render_line of <StylesCache width=146>>                    │                                 │
│ │                self = <StylesCache width=146>                                                              │                                 │
│ │                size = Size(width=146, height=40)                                                           │                                 │
│ │              strips = []                                                                                   │                                 │
│ │              styles = RenderStyles(                                                                        │                                 │
│ │                       │   GridWidget(),                                                                    │                                 │
│ │                       │   background=Color(0, 0, 0, a=0),                                                  │                                 │
│ │                       │   width=Scalar(value=100.0, unit=<Unit.WIDTH: 4>, percent_unit=<Unit.WIDTH: 4>),   │                                 │
│ │                       │   height=Scalar(                                                                   │                                 │
│ │                       │   │   value=100.0,                                                                 │                                 │
│ │                       │   │   unit=<Unit.HEIGHT: 5>,                                                       │                                 │
│ │                       │   │   percent_unit=<Unit.WIDTH: 4>                                                 │                                 │
│ │                       │   ),                                                                               │                                 │
│ │                       │   scrollbar_color=Color(0, 48, 84),                                                │                                 │
│ │                       │   scrollbar_color_hover=Color(0, 60, 106),                                         │                                 │
│ │                       │   scrollbar_color_active=Color(1, 120, 212),                                       │                                 │
│ │                       │   scrollbar_corner_color=Color(0, 0, 0),                                           │                                 │
│ │                       │   scrollbar_background=Color(0, 0, 0),                                             │                                 │
│ │                       │   scrollbar_background_hover=Color(0, 0, 0),                                       │                                 │
│ │                       │   scrollbar_background_active=Color(0, 0, 0),                                      │                                 │
│ │                       │   scrollbar_size_vertical=2,                                                       │                                 │
│ │                       │   scrollbar_size_horizontal=1,                                                     │                                 │
│ │                       │   link_color=Color(255, 255, 255, a=0.87),                                         │                                 │
│ │                       │   auto_link_color=True,                                                            │                                 │
│ │                       │   link_background=Color(0, 0, 0, a=0),                                             │                                 │
│ │                       │   link_style=Style(underline=True),                                                │                                 │
│ │                       │   link_color_hover=Color(255, 255, 255, a=0.87),                                   │                                 │
│ │                       │   auto_link_color_hover=True,                                                      │                                 │
│ │                       │   link_background_hover=Color(1, 120, 212),                                        │                                 │
│ │                       │   link_style_hover=Style(bold=True, underline=False)                               │                                 │
│ │                       )                                                                                    │                                 │
│ │               width = 146                                                                                  │                                 │
│ │                   y = 0                                                                                    │                                 │
│ ╰────────────────────────────────────────────────────────────────────────────────────────────────────────────╯                                 │
│                                                                                                                                                │
│ /home/joshua/python_virtual/lib/python3.13/site-packages/textual/_styles_cache.py:447 in render_line                                           │
│                                                                                                                                                │
│   444 │   │   │   # Content with border and padding (C)                                                                                        │
│   445 │   │   │   content_y = y - gutter.top                                                                                                   │
│   446 │   │   │   if content_y < content_height:                                                                                               │
│ ❱ 447 │   │   │   │   line = render_content_line(y - gutter.top)                                                                               │
│   448 │   │   │   │   line = line.adjust_cell_length(content_width, inner.rich_style)                                                          │
│   449 │   │   │   else:                                                                                                                        │
│   450 │   │   │   │   line = Strip.blank(content_width, inner.rich_style)                                                                      │
│                                                                                                                                                │
│ ╭────────────────────────────────────────────────── locals ───────────────────────────────────────────────────╮                                │
│ │           ansi_theme = <rich.terminal_theme.TerminalTheme object at 0x7b09f3178830>                         │                                │
│ │           background = Color(30, 30, 30)                                                                    │                                │
│ │      base_background = Color(30, 30, 30)                                                                    │                                │
│ │        border_bottom = ''                                                                                   │                                │
│ │  border_bottom_color = Color(0, 255, 0)                                                                     │                                │
│ │          border_left = ''                                                                                   │                                │
│ │    border_left_color = Color(0, 255, 0)                                                                     │                                │
│ │         border_right = ''                                                                                   │                                │
│ │   border_right_color = Color(0, 255, 0)                                                                     │                                │
│ │      border_subtitle = None                                                                                 │                                │
│ │         border_title = None                                                                                 │                                │
│ │           border_top = ''                                                                                   │                                │
│ │     border_top_color = Color(0, 255, 0)                                                                     │                                │
│ │   cache_simple_strip = False                                                                                │                                │
│ │       content_height = 40                                                                                   │                                │
│ │         content_size = Size(width=146, height=40)                                                           │                                │
│ │        content_width = 146                                                                                  │                                │
│ │            content_y = 0                                                                                    │                                │
│ │           from_color = <bound method Style.from_color of <class 'rich.style.Style'>>                        │                                │
│ │               gutter = Spacing(top=0, right=0, bottom=0, left=0)                                            │                                │
│ │               height = 40                                                                                   │                                │
│ │                inner = Style(background=Color(30, 30, 30))                                                  │                                │
│ │              opacity = 1.0                                                                                  │                                │
│ │                outer = Style(background=Color(30, 30, 30))                                                  │                                │
│ │       outline_bottom = ''                                                                                   │                                │
│ │ outline_bottom_color = Color(0, 255, 0)                                                                     │                                │
│ │         outline_left = ''                                                                                   │                                │
│ │   outline_left_color = Color(0, 255, 0)                                                                     │                                │
│ │        outline_right = ''                                                                                   │                                │
│ │  outline_right_color = Color(0, 255, 0)                                                                     │                                │
│ │          outline_top = ''                                                                                   │                                │
│ │    outline_top_color = Color(0, 255, 0)                                                                     │                                │
│ │           pad_bottom = 0                                                                                    │                                │
│ │             pad_left = 0                                                                                    │                                │
│ │            pad_right = 0                                                                                    │                                │
│ │              pad_top = 0                                                                                    │                                │
│ │              padding = Spacing(top=0, right=0, bottom=0, left=0)                                            │                                │
│ │  render_content_line = <bound method GridWidget.render_line of GridWidget()>                                │                                │
│ │                 self = <StylesCache width=146>                                                              │                                │
│ │                 size = Size(width=146, height=40)                                                           │                                │
│ │               styles = RenderStyles(                                                                        │                                │
│ │                        │   GridWidget(),                                                                    │                                │
│ │                        │   background=Color(0, 0, 0, a=0),                                                  │                                │
│ │                        │   width=Scalar(value=100.0, unit=<Unit.WIDTH: 4>, percent_unit=<Unit.WIDTH: 4>),   │                                │
│ │                        │   height=Scalar(                                                                   │                                │
│ │                        │   │   value=100.0,                                                                 │                                │
│ │                        │   │   unit=<Unit.HEIGHT: 5>,                                                       │                                │
│ │                        │   │   percent_unit=<Unit.WIDTH: 4>                                                 │                                │
│ │                        │   ),                                                                               │                                │
│ │                        │   scrollbar_color=Color(0, 48, 84),                                                │                                │
│ │                        │   scrollbar_color_hover=Color(0, 60, 106),                                         │                                │
│ │                        │   scrollbar_color_active=Color(1, 120, 212),                                       │                                │
│ │                        │   scrollbar_corner_color=Color(0, 0, 0),                                           │                                │
│ │                        │   scrollbar_background=Color(0, 0, 0),                                             │                                │
│ │                        │   scrollbar_background_hover=Color(0, 0, 0),                                       │                                │
│ │                        │   scrollbar_background_active=Color(0, 0, 0),                                      │                                │
│ │                        │   scrollbar_size_vertical=2,                                                       │                                │
│ │                        │   scrollbar_size_horizontal=1,                                                     │                                │
│ │                        │   link_color=Color(255, 255, 255, a=0.87),                                         │                                │
│ │                        │   auto_link_color=True,                                                            │                                │
│ │                        │   link_background=Color(0, 0, 0, a=0),                                             │                                │
│ │                        │   link_style=Style(underline=True),                                                │                                │
│ │                        │   link_color_hover=Color(255, 255, 255, a=0.87),                                   │                                │
│ │                        │   auto_link_color_hover=True,                                                      │                                │
│ │                        │   link_background_hover=Color(1, 120, 212),                                        │                                │
│ │                        │   link_style_hover=Style(bold=True, underline=False)                               │                                │
│ │                        )                                                                                    │                                │
│ │                width = 146                                                                                  │                                │
│ │                    y = 0                                                                                    │                                │
│ ╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────╯                                │
│                                                                                                                                                │
│ /home/joshua/Documents/table_planner/V0.0/tableplanV0.4.py:541 in render_line                                                                  │
│                                                                                                                                                │
│    538 │   │   if self.size.width == 0 or self.size.height == 0:                                ╭────── locals ───────╮                        │
│    539 │   │   │   return Strip([])                                                             │ self = GridWidget() │                        │
│    540 │   │                                                                                    │    y = 0            │                        │
│ ❱  541 │   │   step_h, row_lw, col_widths, vis_cols, n_vis_s = self._layout()                   ╰─────────────────────╯                        │
│    542 │   │   n_rows = len(self.table.rows)                                                                                                   │
│    543 │   │   H, W   = self.size.height, self.size.width                                                                                      │
│    544 │   │   hs     = self.settings.height_steps                                                                                             │
│                                                                                                                                                │
│ /home/joshua/Documents/table_planner/V0.0/tableplanV0.4.py:334 in _layout                                                                      │
│                                                                                                                                                │
│    331 │   │   s      = self.settings                                                                                                          │
│    332 │   │                                                                                                                                   │
│    333 │   │   # ── Row-label column ──────────────────────────────────────────────────                                                        │
│ ❱  334 │   │   row_lw = max((len(r) for r in self.table.rows), default=5) + 2                                                                  │
│    335 │   │                                                                                                                                   │
│    336 │   │   # ── Uniform column width ──────────────────────────────────────────────                                                        │
│    337 │   │   all_words: list[str] = []                                                                                                       │
│                                                                                                                                                │
│ ╭───────────────────────────────────────────────────────── locals ──────────────────────────────────────────────────────────╮                  │
│ │      H = 40                                                                                                               │                  │
│ │ n_cols = 15                                                                                                               │                  │
│ │ n_rows = 10                                                                                                               │                  │
│ │      s = Settings(height_steps=1, zoom_h=1.0, zoom_w=1.0, block_wrap=False, max_visible_cols=None, max_visible_rows=None) │                  │
│ │   self = GridWidget()                                                                                                     │                  │
│ │      W = 146                                                                                                              │                  │
│ ╰───────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯                  │
│                                                                                                                                                │
│ /home/joshua/Documents/table_planner/V0.0/tableplanV0.4.py:334 in <genexpr>                                                                    │
│                                                                                                                                                │
│    331 │   │   s      = self.settings                                                                                                          │
│    332 │   │                                                                                                                                   │
│    333 │   │   # ── Row-label column ──────────────────────────────────────────────────                                                        │
│ ❱  334 │   │   row_lw = max((len(r) for r in self.table.rows), default=5) + 2                                                                  │
│    335 │   │                                                                                                                                   │
│    336 │   │   # ── Uniform column width ──────────────────────────────────────────────                                                        │
│    337 │   │   all_words: list[str] = []                                                                                                       │
│                                                                                                                                                │
│ ╭─────────────────── locals ────────────────────╮                                                                                              │
│ │ .0 = <list_iterator object at 0x7b09f2c03f10> │                                                                                              │
│ │  r = 1                                        │                                                                                              │
│ ╰───────────────────────────────────────────────╯                                                                                              │
╰────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
TypeError: object of type 'int' has no len()

MarkE
# Prompt7
- Add wrap text of block labels inside blocks when necessary
- Add ability to search for blocks (/) (moves cursor to the block)
- Automatically select the current block that the cursor is under when enter visual mode.
- Add grouping feature and ungrouping feature to temporary move blocks together (g - groups and shift + g - ungroups)
    -> when grouped together blocks all move and keep same structuring as if they were one block but maintain their status as individual blocks.
- Add a temporary holding ground that removes the block or group from the tables, but keeps it in memory and can then be placed down. This is different than the select tool. The intention is that the user can send the blocks to the holding ground, move some other blocks around and then come back to those same blocks. Think of it like a shelf that it can quickly be brought back into use.
- Add ability to scale individual axis only (scale horizontal only or scale vertical only, can remove scaling both simultaneously. Leave set home as currently behaves)
- Make both the horizontal and vertical axis be float value scales with a tolerance so that they can be used interchangebly.  
- Undo and redo command (u and shift + r) 
- Add scroll to mouse scroll wheel if possible (Shift + scroll)

MarkF
# Prompt8
- make redo just normal r for now (instead of shift)
- when searching for stuff, clear the highlight by typing :noh or z
- stop auto zooming in when there is no more room to scroll horizontally. (it currently inlarges the size of the columns)
- shelf command to return from shelf, place starting at cursor (so that remaining portion of block or group goes below the cursor or to the right if in transpose mode)
- Shelf command when multiple items are in the shelf display them in a list format similar to regs in vim but allow the user to select via number which item from the shelf they would like to place. This is the "S" command (shift + s) 
- add additional colors
- set wrap still is not behaving as expected. I would like when it is on to be able to take the current portion of the block that is past the end of the table and push it to the top of the next column (or left of the next row if wrapping columns).

- generator for inputs. This means create a standalone python application that creates the necessary formatting for blocks in a yaml file from a csv which only contains name, height, width. From that create a randomized color and a position that avoids overlap with the previous block.

MarkG
# Prompt9
- update the wrap feature to be included when checking for overlaps and show red when overlapping even if it is from a wrapped block
- Make the shelf command (shift + S) behave like regs where it shows the different groups vertically with the numbers instead of trying to keep them all in a line
- Create a way to export the table to a printable format (pdf, svg, etc) what ever method is easiest.
- Transpose mode is broken, it will no longer show blocks any larger than a 1x1
- set wrap is not working at all when tables are transposed. It should force the cells to wrap from the right current row to the left most column in the next row.  


MarkH
# Prompt10
- Export feature does not work fully: Does not export the numbers of a timed row or column header
- Add export data to csv (only actual information)
- when putting down from shelf it removes any thing that is not able to paste, Do not remove anything from the shelf, instead only paste what is possible
- Add ability to click even where there are no boxes
- Tab auto complete for commands

- add ability to customize settings and defaults in .tablerc file

MarkI
# Prompt 11
- Fixing export to include wrap

MarkJ
# Prompt 12
- Take this table_generation.py and convert it to be easier to use. Specifically, the rows and columns can you make them come in a secondary file? leave the wrap, steps and seed

MarkK 
# Prompt 13
- make the table easily transposable fully
- fix vertical scroll
