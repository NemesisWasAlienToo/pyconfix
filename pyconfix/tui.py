# MIT License
#
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Curses front-end for pyconfix.

Owns all terminal interaction. A :class:`Tui` is driven by a core manager
(``app``) and reaches back into it for every piece of logic — building the
visible list, availability, toggling/collapsing, executing actions — and calls
the serializer to persist. Importing this module is the only place that pulls in
curses, so core/serializer/runner stay usable headless.
"""

import curses
import curses.textpad
import curses.ascii
import textwrap

from .option import ConfigOptionType
from . import serializer


class Tui:
    def __init__(self, app):
        self.app = app

    def run(self):
        """Run the main interactive loop using curses."""
        curses.wrapper(self._menu_loop)

    def _show_help(self, stdscr):
        app = self.app
        help_text = [
            "Help Page",
            "",
             "Keybindings:",
             "  Navigate                  : Arrow Up/Down",
             "  Select/Toggle option      : Enter",
            f"  Save configuration        : {curses.keyname(app.save_key).decode()}",
            f"  Save diff configuration   : {curses.keyname(app.save_diff_key).decode()}",
            f"  Quit                      : {curses.keyname(app.quite_key).decode()}",
            f"  Collapse/Expand group     : {curses.keyname(app.collapse_key).decode()}",
            f"  Search                    : {curses.keyname(app.search_key).decode()}",
            f"  Show help page            : {curses.keyname(app.help_key).decode()}",
            f"  Show description          : {curses.keyname(app.description_key).decode()}",
            f"  Exit search               : {curses.keyname(app.abort_key).decode()}",
            f"  Exit input box            : {curses.keyname(app.abort_key).decode()}",
             "",
             "How it works:",
             "  - Use the arrow keys to navigate through the options.",
             "  - Press Enter to select or toggle an option.",
             "  - Options that depend on other options will be shown or hidden based on their dependencies.",
             "  - Use the search function to quickly find options by name.",
            f"  - Collapse/Expand groups : {curses.keyname(app.collapse_key).decode()}",
             ""
        ]

        start_index = 0
        while True:
            stdscr.clear()
            max_y, _ = stdscr.getmaxyx()
            display_limit = max(1, max_y - 3)
            if max_y > 2:
                stdscr.addstr(max_y - 2, 2, "Press 'q' to return to the menu or UP/DOWN to scroll")

            if max_y >= 4:
                for idx, line in enumerate(help_text[start_index:start_index + display_limit]):
                    stdscr.addstr(idx + 1, 2, line)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP and start_index > 0:
                start_index -= 1
            elif key == curses.KEY_DOWN and start_index < len(help_text) - display_limit:
                start_index += 1
            elif key == curses.KEY_RESIZE:
                max_y, _ = stdscr.getmaxyx()
                display_limit = max_y - 2
            elif key == ord('q') or key == self.app.abort_key:
                break

    def _description_page(self, stdscr, option):
        start_index = 0
        while True:
            stdscr.clear()
            stdscr.border(0)
            stdscr.addstr(0, 2, f" {option.name} ")
            max_y, max_x = stdscr.getmaxyx()
            display_limit = max(1, max_y - 3)

            content = [
                "",
                "Dependencies ",
                (option.dependencies if not callable(option.dependencies) else "<function>") if option.dependencies else "No dependencies",
                "",
                "Description ",
                option.description if option.description else "No description available"
            ]

            if max_y > 2:
                stdscr.addstr(max_y - 2, 2, "Press 'q' to return to the menu or UP/DOWN to scroll")

            wrapped_content = []
            for line in content:
                if line == "":
                    wrapped_content.append(line)
                else:
                    wrapped_content.extend(textwrap.wrap(line, max_x - 4))

            if max_y >= 4:
                for idx, line in enumerate(wrapped_content[start_index:start_index + display_limit]):
                    stdscr.addstr(idx + 1, 2, line)

            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP and start_index > 0:
                start_index -= 1
            elif key == curses.KEY_DOWN and start_index < len(wrapped_content) - display_limit:
                start_index += 1
            elif key == curses.KEY_RESIZE:
                max_y, max_x = stdscr.getmaxyx()
                display_limit = max_y - 2
            elif key == ord('q'):
                break

    def _display_options(self, stdscr, flat_options, start_index, current_row, search_mode):
        max_y, max_x = stdscr.getmaxyx()
        display_limit = max_y - 4 if not search_mode else max_y - 6
        for idx in range(start_index, min(start_index + display_limit, len(flat_options))):
            option, depth = flat_options[idx]
            indicator = "[+]" if option.option_type == ConfigOptionType.GROUP and not option.expanded else "[-]" if option.option_type == ConfigOptionType.GROUP else ""
            name = f"{indicator} {option.name}" if option.option_type == ConfigOptionType.GROUP else option.name
            value = ""
            if option.option_type == ConfigOptionType.EXTERNAL:
                value = f"{option.value} [external]"
            elif option.value is None and option.option_type != ConfigOptionType.GROUP:
                value = "[disabled]"
            elif option.option_type == ConfigOptionType.ENUM:
                value = option.choices[option.value][:10] + "..." if len(option.choices[option.value]) > 10 else option.choices[option.value]
            elif option.option_type == ConfigOptionType.BOOL:
                value = "True" if option.value else "False"
            elif option.option_type in [ConfigOptionType.INT, ConfigOptionType.STRING]:
                value = str(option.value)[:10] + "..." if len(str(option.value)) > 10 else str(option.value)
            display_text = f"{name}: {value}" if value != "" else name
            if option.option_type == ConfigOptionType.ACTION:
                display_text = f"({name})"
                if option.value is None:
                    display_text += " [disabled]"
            if len(display_text) > max_x - 2:
                display_text = display_text[:max_x - 5] + "..."
            if idx == current_row:
                stdscr.attron(curses.color_pair(1))
            stdscr.addstr(2 + idx - start_index, 2 + depth * 2, display_text)
            if idx == current_row:
                stdscr.attroff(curses.color_pair(1))

    def _search_options(self, options, query, depth=0):
        app = self.app
        flat_options = []
        for option in options:
            available = app._is_option_available(option)
            app._sync_option_value(option, available)
            if app.show_disabled or available:
                if option.option_type == ConfigOptionType.GROUP:
                    option.expanded = True
                if query.lower() in option.name.lower():
                    flat_options.extend(app._flatten_options([option], depth))
                elif option.option_type == ConfigOptionType.GROUP:
                    nested_options = self._search_options(option.options, query, depth + 1)
                    if nested_options:
                        flat_options.append((option, depth))
                        flat_options.extend(nested_options)
        return flat_options

    def _collapse_current_group(self, flat_options, current_row, search_mode):
        selected_option, _ = flat_options[current_row]
        if selected_option.option_type == ConfigOptionType.GROUP:
            selected_option.expanded = not selected_option.expanded
            if search_mode:
                for option, _ in flat_options:
                    if option in selected_option.options:
                        option.expanded = selected_option.expanded
            return current_row
        for idx, (option, _) in enumerate(flat_options):
            if option.option_type == ConfigOptionType.GROUP and option.expanded and selected_option in option.options:
                option.expanded = False
                return idx
        return current_row

    def _menu_loop(self, stdscr):
        app = self.app
        curses.curs_set(0)
        stdscr.keypad(True)
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_WHITE)
        current_row = 0
        search_mode, search_query = False, ""
        start_index = 0

        while True:
            stdscr.clear()
            stdscr.border(0)
            stdscr.addstr(0, 2, f" {app.config_name or 'Unnamed'} ")
            max_y, max_x = stdscr.getmaxyx()
            if not search_mode and max_y > 2:
                info = f"'{curses.keyname(app.quite_key).decode()}': Exit, '{curses.keyname(app.save_key).decode()}': Save, '{curses.keyname(app.collapse_key).decode()}': Collapse Group, '/': Search, '{curses.keyname(app.help_key).decode()}': Help"
                stdscr.addstr(max_y - 2, 2, info[:max_x - 5])

            flat_options = self._search_options(app.options, search_query) if search_mode else app._flatten_options(app.options)
            if current_row >= len(flat_options):
                current_row = len(flat_options) - 1
            if current_row < 0:
                current_row = 0
            if current_row < start_index:
                start_index = current_row
            elif current_row >= start_index + (max_y - 6 if search_mode else max_y - 5):
                start_index = current_row - (max_y - 7 if search_mode else max_y - 6)

            self._display_options(stdscr, flat_options, start_index, current_row, search_mode)
            if search_mode:
                if max_y > 3:
                    stdscr.addstr(max_y - 3, 2, f"Search: {search_query}")
                if max_y > 2:
                    stdscr.addstr(max_y - 2, 2, f"Press {curses.keyname(app.abort_key).decode()} to abort search")
            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
            if search_mode:
                if key in (curses.KEY_BACKSPACE, 127):
                    search_query = search_query[:-1]
                elif key == app.abort_key:
                    stdscr.timeout(100)
                    if stdscr.getch() == -1:
                        search_mode, search_query = False, ""
                    stdscr.timeout(-1)
                elif 32 <= key <= 126:
                    search_query += chr(key)
                elif key in (curses.KEY_UP, curses.KEY_DOWN):
                    if key == curses.KEY_UP and current_row > 0:
                        current_row -= 1
                    elif key == curses.KEY_DOWN and current_row < len(flat_options) - 1:
                        current_row += 1
                elif key in (curses.KEY_ENTER, 10, 13):
                    self._handle_enter(flat_options, current_row, stdscr, search_mode)
                elif key == app.description_key:
                    selected_option, _ = flat_options[current_row]
                    self._description_page(stdscr, selected_option)
            else:
                if key in (curses.KEY_UP, curses.KEY_DOWN):
                    if key == curses.KEY_UP and current_row > 0:
                        current_row -= 1
                        if current_row < start_index:
                            start_index -= 1
                    elif key == curses.KEY_DOWN and current_row < len(flat_options) - 1:
                        current_row += 1
                        if current_row >= start_index + max_y - 4:
                            start_index += 1
                elif key in (curses.KEY_ENTER, 10, 13):
                    self._handle_enter(flat_options, current_row, stdscr, search_mode)
                elif key == app.save_key:
                    self._save_config(stdscr, False)
                elif key == app.save_diff_key:
                    self._save_config(stdscr, True)
                elif key == app.quite_key or key == app.abort_key:
                    break
                elif key == app.collapse_key:
                    current_row = self._collapse_current_group(flat_options, current_row, search_mode)
                elif key == app.search_key:
                    search_mode, search_query, current_row = True, "", 0
                elif key == app.help_key:
                    self._show_help(stdscr)
                elif key == app.description_key:
                    selected_option, _ = flat_options[current_row]
                    self._description_page(stdscr, selected_option)

    def _handle_enter(self, flat_options, row, stdscr, search_mode):
        if not flat_options:
            return
        selected_option, _ = flat_options[row]
        if selected_option.option_type == ConfigOptionType.GROUP:
            if not search_mode:
                selected_option.expanded = not selected_option.expanded
                return
        # If value is None, the option is diasabled, skip
        if selected_option.value is None:
            return
        if selected_option.option_type == ConfigOptionType.EXTERNAL:
            return
        if selected_option.option_type == ConfigOptionType.BOOL:
            selected_option.value = not selected_option.value
        elif selected_option.option_type in [ConfigOptionType.INT, ConfigOptionType.STRING]:
            self._edit_option(stdscr, selected_option)
        elif selected_option.option_type == ConfigOptionType.ENUM:
            self._edit_multiple_choice_option(stdscr, selected_option)
        elif selected_option.option_type == ConfigOptionType.ACTION:
            curses.echo()
            curses.nocbreak()
            stdscr.keypad(False)
            curses.endwin()
            self.app._execute_action(selected_option)
            stdscr = curses.initscr()
            curses.noecho()
            curses.cbreak()
            stdscr.keypad(True)
            return

    def _edit_option(self, stdscr, option):
        if option.value is None:
            return
        original_value = option.value
        curses.curs_set(1)

        def redraw_window():
            stdscr.clear()
            max_y, max_x = stdscr.getmaxyx()

            start_y = 1
            start_x = 2
            end_y = max_y - 3
            end_x = max_x - 3

            # Create the outer box
            curses.textpad.rectangle(
                stdscr,
                start_y,     # uly
                start_x,     # ulx
                end_y,       # lry
                end_x        # lrx
            )

            # Create edit window
            editwin = curses.newwin(
                end_y - start_y - 2,   # nlines
                end_x - start_x - 2,   # ncols
                start_y + 1,           # begin_y
                start_x + 1            # begin_x
            )

            # Add title and instructions if there's room
            if max_y > 1:
                stdscr.addstr(0, 2, f"Editing - {option.name} "[:max_x-4])
            if max_y > 3:
                stdscr.addstr(max_y - 2, 2, f"Press {curses.keyname(self.app.abort_key).decode()} to abort "[:max_x-4])

            stdscr.refresh()
            editwin.move(0, 0)
            editwin.clrtoeol()
            editwin.addstr(0, 0, str(option.value))
            editwin.refresh()

            return editwin

        editwin = redraw_window()

        def validate_input(ch):
            if ch == curses.KEY_RESIZE:
                nonlocal editwin
                editwin = redraw_window()
                return -1  # Special value to indicate resize
            elif ch == self.app.abort_key:
                raise KeyboardInterrupt
            elif ch in (curses.ascii.CR, curses.ascii.NL):
                return 7
            return ch

        box = curses.textpad.Textbox(editwin, insert_mode=True)

        try:
            content = box.edit(validate_input)
        except KeyboardInterrupt:
            option.value = original_value
            curses.curs_set(0)
            return

        # Only update if not aborted
        try:
            new_value = content.replace('\n', '').strip()
            if option.option_type == ConfigOptionType.INT:
                # Handle hex format
                if new_value.lower().startswith('0x'):
                    option.value = int(new_value, 16)
                # Handle binary format
                elif new_value.lower().startswith('0b'):
                    option.value = int(new_value, 2)
                # Handle decimal format
                else:
                    option.value = int(new_value)
            elif option.option_type == ConfigOptionType.STRING:
                option.value = new_value
        except ValueError:
            option.value = original_value

        curses.curs_set(0)

    def _edit_multiple_choice_option(self, stdscr, option):
        curses.curs_set(0)
        max_y, max_x = stdscr.getmaxyx()
        current_choice = option.value if option.value is not None else 0
        original_choice = option.value
        while True:
            stdscr.clear()
            stdscr.addstr(0, 2, f"Editing - {option.name} "[:max_x-4])
            stdscr.addstr(curses.LINES - 2, 2, f"Press {curses.keyname(self.app.abort_key).decode()} abort ")
            for idx, choice in enumerate(option.choices):
                if idx == current_choice:
                    stdscr.attron(curses.color_pair(1))
                if 3 + idx < stdscr.getmaxyx()[0]:
                    stdscr.addstr(3 + idx, 4, " " * (len(choice) + 4))
                    stdscr.addstr(3 + idx, 4, choice)
                if idx == current_choice:
                    stdscr.attroff(curses.color_pair(1))
            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_UP and current_choice > 0:
                current_choice -= 1
            elif key == curses.KEY_DOWN and current_choice < len(option.choices) - 1:
                current_choice += 1
            elif key in (curses.KEY_ENTER, 10, 13):
                option.value = current_choice
                break
            elif key == self.app.abort_key:
                option.value = original_choice
                break

    def _save_config(self, stdscr, output_diff):
        serializer.write_config(self.app, output_diff)
        stdscr.clear()
        stdscr.addstr(0, 0, "Configuration saved successfully.")
        stdscr.addstr(1, 0, "Press any key to continue.")
        stdscr.refresh()
        stdscr.getch()
