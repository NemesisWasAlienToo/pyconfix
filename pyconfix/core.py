# MIT License
# 
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import json
import curses
import curses.textpad
import os
import textwrap
import sys

from .parser import *
from .option import *

class pyconfix:
    def __init__(self, schem_files=["pyconfixfile.json"], output_file="output_config.json",
                 save_func=None, expanded=False, show_disabled=False):
        self.schem_files = schem_files
        self.output_file = output_file
        self.save_func = save_func
        self.show_disabled = show_disabled
        self.expanded = expanded
        self.options = []
        self.aliases = {}
        self.config_name = ""

        self.save_key = ord('s')
        self.save_diff_key = ord('d')
        self.quite_key = ord('q')
        self.collapse_key = ord('c')
        self.search_key = ord('/')
        self.help_key = ord('h')
        self.abort_key = 1  # Ctrl+A
        self.description_key = 4  # Ctrl+D

    def _register_alias(self, alias_option: ConfigOption, skip_duplicate_check=False):
        """Register an alias and guard against accidental duplicates."""
        if alias_option.option_type != ConfigOptionType.ENUM:
            raise ValueError("Only ENUM aliases are supported for now")

        existing = self.aliases.get(alias_option.name)
        if existing:
            if not skip_duplicate_check:
                raise ValueError(f"Alias '{alias_option.name}' already exists")
            else:
                return existing
        self.aliases[alias_option.name] = alias_option
        return alias_option

    def register_alias(self, name, option_type, choices):
        """
        Register an alias type that can be reused when defining options. Currently only ENUM aliases are supported.
        """
        alias_option = ConfigOption(
            name=name,
            option_type=option_type,
            choices=choices,
        )
        return self._register_alias(alias_option)

    def option_from_alias(self, alias_name, **kwargs):
        """
        Create a ConfigOption from a registered alias without mutating config.options.
        """
        if 'name' not in kwargs:
            raise ValueError("You must provide a 'name' parameter when creating an option from an alias")
        custom_type = self.aliases.get(alias_name)
        if custom_type is None:
            try:
                alias_name = ConfigOptionType(alias_name)
                custom_type = ConfigOption(
                    name=alias_name,
                    option_type=alias_name,
                    default=kwargs.get('default'),
                )
            except Exception:
                known = ", ".join(sorted(self.aliases.keys())) or "<none>"
                raise ValueError(f"Alias '{alias_name}' is not registered. Known aliases: {known}")
        return custom_type.clone_with(**kwargs)

    def add_options(self, *options):
        """
        Convenience helper to append multiple ConfigOption instances.
        """
        self.options.extend(options)
        return options

    def _show_help(self, stdscr):
        help_text = [
            "Help Page",
            "",
             "Keybindings:",
             "  Navigate                  : Arrow Up/Down",
             "  Select/Toggle option      : Enter",
            f"  Save configuration        : {curses.keyname(self.save_key).decode()}",
            f"  Save diff configuration   : {curses.keyname(self.save_diff_key).decode()}",
            f"  Quit                      : {curses.keyname(self.quite_key).decode()}",
            f"  Collapse/Expand group     : {curses.keyname(self.collapse_key).decode()}",
            f"  Search                    : {curses.keyname(self.search_key).decode()}",
            f"  Show help page            : {curses.keyname(self.help_key).decode()}",
            f"  Show description          : {curses.keyname(self.description_key).decode()}",
            f"  Exit search               : {curses.keyname(self.abort_key).decode()}",
            f"  Exit input box            : {curses.keyname(self.abort_key).decode()}",
             "",
             "How it works:",
             "  - Use the arrow keys to navigate through the options.",
             "  - Press Enter to select or toggle an option.",
             "  - Options that depend on other options will be shown or hidden based on their dependencies.",
             "  - Use the search function to quickly find options by name.",
            f"  - Collapse/Expand groups : {curses.keyname(self.collapse_key).decode()}",
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
            elif key == ord('q') or key == self.abort_key:
                break

    def _apply_config_to_options(self, options, saved_config):
        for option in options:
            if option.option_type == ConfigOptionType.GROUP:
                self._apply_config_to_options(option.options, saved_config)
            elif option.name in saved_config:
                value = saved_config[option.name]
                option.value = option.choices.index(value if value else option.default) if option.option_type == ConfigOptionType.ENUM else value
            else:
                option.value = option.default if option.option_type != ConfigOptionType.ENUM else option.choices.index(option.default)

    def _is_option_available(self, option):
        def _is_option_available_impl(option, root):
            if not option.dependencies:
                return True
            if not callable(option.dependencies): raise ValueError('Not callable dependencies')
            return option.dependencies(self)
        return _is_option_available_impl(option, option.name)

    def _sync_option_value(self, option, available):
        """Keep an option's value in sync with its availability.

        Disabling an option blanks its value; re-enabling restores it from the
        default. This must run wherever availability is (re)evaluated so the
        bookkeeping stays correct in both the normal and search views.
        """
        if not available:
            if option.option_type != ConfigOptionType.GROUP:
                option.value = None
        elif option.value is None:
            option.value = option.choices.index(option.default) if option.option_type == ConfigOptionType.ENUM else option.default

    def _flatten_options(self, options, depth=0):
        flat_options = []
        for option in options:
            available = self._is_option_available(option)
            self._sync_option_value(option, available)
            if not available and not self.show_disabled:
                continue
            flat_options.append((option, depth))
            if option.option_type == ConfigOptionType.GROUP and option.expanded:
                flat_options.extend(self._flatten_options(option.options, depth + 1))
        return flat_options

    def _search_options(self, options, query, depth=0):
        flat_options = []
        for option in options:
            available = self._is_option_available(option)
            self._sync_option_value(option, available)
            if self.show_disabled or available:
                if option.option_type == ConfigOptionType.GROUP:
                    option.expanded = True
                if query.lower() in option.name.lower():
                    flat_options.extend(self._flatten_options([option], depth))
                elif option.option_type == ConfigOptionType.GROUP:
                    nested_options = self._search_options(option.options, query, depth + 1)
                    if nested_options:
                        flat_options.append((option, depth))
                        flat_options.extend(nested_options)
        return flat_options
    
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
                if callable(option.default):
                    option.value = option.default()
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

    def _menu_loop(self, stdscr):
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
            stdscr.addstr(0, 2, f" {self.config_name or 'Unnamed'} ")
            max_y, max_x = stdscr.getmaxyx()
            if not search_mode and max_y > 2:
                info = f"'{curses.keyname(self.quite_key).decode()}': Exit, '{curses.keyname(self.save_key).decode()}': Save, '{curses.keyname(self.collapse_key).decode()}': Collapse Group, '/': Search, '{curses.keyname(self.help_key).decode()}': Help"
                stdscr.addstr(max_y - 2, 2, info[:max_x - 5])

            flat_options = self._search_options(self.options, search_query) if search_mode else self._flatten_options(self.options)
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
                    stdscr.addstr(max_y - 2, 2, f"Press {curses.keyname(self.abort_key).decode()} to abort search")
            stdscr.refresh()
            key = stdscr.getch()
            if key == curses.KEY_RESIZE:
                continue
            if search_mode:
                if key in (curses.KEY_BACKSPACE, 127):
                    search_query = search_query[:-1]
                elif key == self.abort_key:
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
                elif key == self.description_key:
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
                elif key == self.save_key:
                    self._save_config(stdscr, False)
                elif key == self.save_diff_key:
                    self._save_config(stdscr, True)
                elif key == self.quite_key or key == self.abort_key:
                    break
                elif key == self.collapse_key:
                    current_row = self._collapse_current_group(flat_options, current_row, search_mode)
                elif key == self.search_key:
                    search_mode, search_query, current_row = True, "", 0
                elif key == self.help_key:
                    self._show_help(stdscr)
                elif key == self.description_key:
                    selected_option, _ = flat_options[current_row]
                    self._description_page(stdscr, selected_option)
    
    def _execute_action(self, option):
        trace = []
        class ExecutionSession:
            def __init__(self, config, root):
                self.config = config
                self.cache = {}
                self.root = root

            def _execute_action(self, opt):
                trace.append(opt.name)
                if opt.requires and not opt.requires(self):
                    return None
                if opt.name in self.cache:
                    return self.cache[opt.name]
                value = opt.default(self)
                self.cache[opt.name] = value
                return value

            def __getattr__(self, name):
                if name == self.root:
                    raise AttributeError(f"Cycle detected: '{name}'")
                opt = self.config._get(name)
                if not self.config._is_option_available(opt):
                    if opt.option_type == ConfigOptionType.ACTION:
                        return lambda: None
                    return None
                if opt is None:
                    raise AttributeError(f"Invalid key: '{name}'")
                if opt.option_type == ConfigOptionType.ENUM:
                    return opt.choices[opt.value] if opt.value is not None else None
                elif opt.option_type == ConfigOptionType.ACTION:
                    return lambda: self._execute_action(opt)
                elif opt.option_type == ConfigOptionType.GROUP:
                    return opt.options
                return opt.value
            
        return ExecutionSession(self, option.name)._execute_action(option), trace

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
            self._execute_action(selected_option)
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
                stdscr.addstr(max_y - 2, 2, f"Press {curses.keyname(self.abort_key).decode()} to abort "[:max_x-4])
            
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
            elif ch == self.abort_key:
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
            stdscr.addstr(curses.LINES - 2, 2, f"Press {curses.keyname(self.abort_key).decode()} abort ")
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
            elif key == self.abort_key:
                option.value = original_choice
                break

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

    def _write_config(self, output_diff=True):
        config_data = self.diff() if output_diff else self.dump()
        with open(self.output_file, 'w') as f:
            json.dump(config_data, f, indent=4)
        if self.save_func:
            self.save_func(config_data, self, output_diff)

    def _save_config(self, stdscr, output_diff):
        self._write_config(output_diff)
        stdscr.clear()
        stdscr.addstr(0, 0, "Configuration saved successfully.")
        stdscr.addstr(1, 0, "Press any key to continue.")
        stdscr.refresh()
        stdscr.getch()

    def _dump(self, options):
        config_data = {}
        for option in options:
            if option.option_type == ConfigOptionType.ACTION:
                continue
            if option.option_type == ConfigOptionType.GROUP:
                nested_data = self._dump(option.options)
                if not self._is_option_available(option):
                    nested_data = {nested_key: None for nested_key in nested_data}
                config_data.update(nested_data)
            else:
                # option.default is the choice string for enums, so this emits a
                # string for the disabled/None path just like the active path below.
                default_value = option.default
                value_to_save = default_value if option.value is None else (
                    option.choices[option.value] if option.option_type == ConfigOptionType.ENUM
                    else option.value)
                config_data[option.name] = None if not self._is_option_available(option) else value_to_save
        return config_data
    
    def __getattr__(self, name):
        opt = self._get(name)
        if opt is None:
            raise AttributeError(f"Invalid key: '{name}'")
        if not self._is_option_available(opt):
            if opt.option_type == ConfigOptionType.ACTION:
                return lambda : (None, [])
            return None
        if opt.option_type == ConfigOptionType.ENUM:
            return opt.choices[opt.value] if opt.value is not None else None
        elif opt.option_type == ConfigOptionType.ACTION:
            return lambda : self._execute_action(opt)
        elif opt.option_type == ConfigOptionType.GROUP:
            return opt.options
        return opt.value
    
    def _get(self, key):
        def get_impl(key, options_list=self.options):
            key_upper = key.upper()
            for opt in options_list:
                if opt.option_type == ConfigOptionType.GROUP:
                    found, value = get_impl(key, opt.options)
                    if found:
                        return True, value
                # Compare names in a case-insensitive manner.
                elif opt.name.upper() == key_upper:
                    return True, opt
            return False, None
        found, value = get_impl(key)
        if not found:
            return None
        return value
    
    def _create_action_decorator(self, group=None):
        class GroupProxy:
            def __init__(self, group):
                self.group = group

            def get(self):
                return self.group

            def action_option(self, name=None, dependencies=None, requires=None):
                def decorator(func):
                    option_name = name or func.__name__
                    new_option = ConfigOption(
                        name=option_name,
                        option_type=ConfigOptionType.ACTION,
                        default=func,
                        dependencies=dependencies,
                        requires=requires,
                        description=func.__doc__ or ""
                    )
                    self.group.options.append(new_option)
                    return func
                return decorator
        if group != None:
            return GroupProxy(group)
        else:
            return GroupProxy(self)
        
    def _parse_file(self, filepath):
        if not os.path.exists(filepath): sys.exit(f"Config file '{filepath}' does not exist.")
        with open(filepath, 'r') as f:
            config_data = json.load(f)
            if (len(config_data.keys()) != 1): sys.exit(f"Json file {filepath} has more than one top entry")

            base_path = os.path.dirname(os.path.abspath(filepath))
            self.config_name, value = next(iter(config_data.items()))
            self.options += self._parse_options(value, base_path)

    # @TODO: Fix callable group dependencies
    def _parse_options(self, options_data, base_path):
        parsed_options = []
        for key, value in options_data.items():
            if key == 'include':
                # Handle includes relative to current file
                for include_file in value:
                    include_path = os.path.join(base_path, include_file)
                    if not os.path.exists(include_path):
                        raise ValueError(f"A non-existing file was included: {include_path}")
                    self._parse_file(include_path)
            else:
                parsed_options.append(self._parse_option(key, value, base_path))
        return parsed_options
    
    def _parse_option(self, name, option_data, base_path):

        if not isinstance(option_data, dict):
            if isinstance(option_data, list):
                option_data = {'choices': option_data}
            else:
                option_data = {'default': option_data}

        option_type_name = ''
        def_value = option_data.get('default', None)
        if 'type' in option_data:
            option_type_name = option_data['type']
        elif 'choices' in option_data:
            def_value = def_value or option_data['choices'][0]
            option_type_name = ConfigOptionType.ENUM
        elif isinstance(def_value, bool):
            option_type_name = ConfigOptionType.BOOL
        elif isinstance(def_value, int):
            option_type_name = ConfigOptionType.INT
        elif isinstance(def_value, str):
            option_type_name = ConfigOptionType.STRING
        elif 'options' in option_data:
            option_type_name = ConfigOptionType.GROUP
            option_data = {'options': option_data['options']}
        else:
            option_type_name = ConfigOptionType.GROUP
            option_data = {'options': option_data}

        option = ConfigOption(
            name=name,
            option_type=ConfigOptionType.STRING,
            default=option_data.get('default', def_value),
            description=option_data.get('description'),
            data=option_data.get('data'),
            dependencies=option_data.get('dependencies', ""),
            requires=option_data.get('requires', ""),
            choices=option_data.get('choices', []),
            expanded=self.expanded,
            options=[]
        )
        try:
            option.option_type = ConfigOptionType(option_type_name)
        except ValueError:
            custom_type = self.aliases.get(option_type_name)
            if custom_type is None:
                raise ValueError(f"Type {option_type_name} for option '{name}' is not a valid type")

            option = custom_type.clone_with(
                name=name,
                default=option_data.get('default', custom_type.default),
                # default=option_data.get('default', def_value),
                description=option_data.get('description', custom_type.description),
                dependencies=option_data.get('dependencies', custom_type.dependencies),
            )
        if option.option_type == ConfigOptionType.GROUP and 'options' in option_data:
            option.options = self._parse_options(option_data['options'], base_path)
        elif option.option_type == ConfigOptionType.ENUM:
            option.value = option.choices.index(option.default)
        
        def _is_option_available_impl(option, root):
            def getter_function_impl(key, options_list):
                key_upper = key.upper()
                if key_upper == root:
                    raise ValueError(f"Cycle detected in the dependency of {option.name}: '{root}'")
                for opt in options_list:
                    if opt.option_type == ConfigOptionType.GROUP:
                        found, value = getter_function_impl(key, opt.options)
                        if found:
                            return True, value
                    # Compare names in a case-insensitive manner.
                    elif opt.name.upper() == key_upper:
                        if not _is_option_available_impl(opt, root):
                            return True, False
                        default_value = opt.default
                        if opt.option_type == ConfigOptionType.ENUM:
                            default_value = opt.choices.index(opt.default)
                            return True, opt.choices[opt.value] if opt.value is not None else default_value
                        return True, opt.value if opt.value is not None else default_value
                    # If an enum value being parsed as key instead of a key name
                    elif opt.option_type == ConfigOptionType.ENUM:
                        for choice in opt.choices:
                            if choice.upper() == key_upper:
                                return True, key
                return False, None

            def getter_function(key):
                found, value = getter_function_impl(key, self.options)
                if not found:
                    raise ValueError(f"Invalid token: {key}")
                return value

            if not option.dependencies:
                return lambda x: True
            if callable(option.dependencies):
                return lambda x:option.dependencies(x)
            else:
                parser = BooleanExpressionParser(getter=getter_function)
                return lambda x:parser.evaluate_postfix(option.postfix_dependencies)
        option.dependencies = _is_option_available_impl(option, option.name)
        return option

    def load_schem(self, schem_files):
        """
        Load configuration schema from files.
        :param schem_files: List of paths to JSON schema files.
        """
        # Parse each config file in the list
        for schem_file in schem_files:
            self._parse_file(os.path.join(os.getcwd(), schem_file))

        def combine(a, b):
            if a is None:
                return b
            if b is None:
                return a
            
            if not callable(a) or not callable(b):
                raise ValueError("Combining non-callable")
            return lambda x: a(x) and b(x)

        def cascade_group(options, group_dependencies = None, group_requires = None):
            """Cascade dependencies and requires from groups to their options."""
            for opt in options:
                if group_dependencies:
                    opt.dependencies = combine(group_dependencies, opt.dependencies)
                if group_requires:
                    opt.requires = combine(group_requires, opt.requires)
                if opt.option_type == ConfigOptionType.GROUP:
                    cascade_group(opt.options, opt.dependencies, opt.requires)

        cascade_group(self.options)

    def apply_config(self, config_files=[], overlay=None):
        """
        Apply configuration from a file or overlay.
        :param overlay: Optional dictionary to override settings.
        """
        saved_config = {}
        for config_file in config_files:
            if not os.path.exists(config_file):
                raise ValueError(f"Invalid config file: {config_file}")
            with open(config_file, 'r') as f:
                try:
                    saved_config.update(json.load(f))
                except json.JSONDecodeError:
                    print(f"Invalid json file: {config_file}")
                    exit(1)

        if overlay:
            saved_config.update(overlay)

        self._apply_config_to_options(self.options, saved_config)

    def dump(self):
        """
        Dumps the current configuration options to a dictionary.
        """
        return self._dump(self.options)
    
    def diff(self):
        """
        Compute and return a dictionary of configuration differences.
        """
        diff = {}
        for key, value in self.dump().items():
            opt = self._get(key)
            av = self._is_option_available(opt)
            if av and (value != opt.default):
                diff[key] = value
        return diff

    def get(self, key, default=None):
        """
        Get an option by its name.
        """
        value = self.__getattr__(key)
        if value is None:
            return default
        return value
    
    def run_main_loop(self):
        """
        Run the main interactive loop using curses.
        """
        curses.wrapper(self._menu_loop)

    def run(self, config_files=[], overlay=None, graphical=True):
        """
        Run the configuration process.
        :param config_file: Optional config file path.
        :param overlay: Optional dict to override settings.
        :param graphical: Use interactive mode if True.
        """
        self.load_schem(self.schem_files)

        if len(config_files) == 0 and os.path.exists(self.output_file):
            config_files = [self.output_file]
        self.apply_config(config_files=config_files, overlay=overlay)
        if graphical:
            self.run_main_loop()

    def action_option(self, name=None, dependencies=None, requires=None):
        """
        Create an action option.
        :param name: Optional action name, defaults to function name.
        :param dependencies: Optional dependency expression or function.
        :param requires: Optional requires function.
        :return: Decorator that registers the action.
        """
        return self._create_action_decorator().action_option(name=name, dependencies=dependencies, requires=requires)

    def group_option(self, name, dependencies=None):
        """
        Create an option group.
        :param name: Group name.
        :param dependencies: Optional dependency expression or function.
        :return: GroupProxy object for adding action options.
        Usage:
            group = config.group_option("my_group", dependencies=None)
            
            @group.action_option()
            def my_action(config):
            '''Action description'''
            ...
        """
        self.options.append(ConfigOption(
            name=name,
            option_type=ConfigOptionType.GROUP,
            dependencies=dependencies,
            options=[]
        ))

        # Get reference to the newly added option
        group_option = self.options[-1]
        return self._create_action_decorator(group=group_option)
