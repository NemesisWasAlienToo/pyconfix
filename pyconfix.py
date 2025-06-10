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

# --- Utility Functions ---
def tokenize(expression: str):
    """Splits an expression string into tokens."""
    i = 0
    n = len(expression)
    tokens = []
    while i < n:
        char = expression[i]
        if char.isspace():
            i += 1
            continue
        # Handle hexadecimal (0x) and binary (0b) prefixes
        if char == '0' and i + 1 < n and expression[i+1].lower() in ('x', 'b'):
            prefix = expression[i:i+2].lower()
            start = i
            i += 2
            # Parse hex digits
            if prefix == '0x':
                while i < n and (expression[i].isdigit() or expression[i].lower() in 'abcdef'):
                    i += 1
            # Parse binary digits
            elif prefix == '0b':
                while i < n and expression[i] in '01':
                    i += 1
            tokens.append(expression[start:i])
        # Numeric literal: digit or dot (with digit following)
        elif char.isdigit() or (char == '.' and i + 1 < n and expression[i+1].isdigit()):
            start = i
            dot_count = 0
            if char == '.':
                dot_count += 1
            i += 1
            while i < n and (expression[i].isdigit() or (expression[i] == '.' and dot_count == 0)):
                if expression[i] == '.':
                    dot_count += 1
                i += 1
            tokens.append(expression[start:i])
        elif char.isalpha() or char == '_':  # Identifier token
            start = i
            while i < n and (expression[i].isalnum() or expression[i] == '_'):
                i += 1
            tokens.append(expression[start:i])
        elif char == "'":
            start = i
            i += 1
            while i < n and expression[i] != "'":
                i += 1
            i += 1  # include closing quote
            tokens.append(expression[start:i])
        elif char in ('&', '|', '!', '=', '>', '<', '+', '-', '*', '/', '^', '%'):
            # Check for two-character operators
            if i + 1 < n and expression[i:i+2] in ('&&', '||', '==', '!=', '>=', '<=', '>>', '<<'):
                tokens.append(expression[i:i+2])
                i += 2
            else:
                tokens.append(char)
                i += 1
        elif char in ('(', ')'):
            tokens.append(char)
            i += 1
        else:
            raise ValueError(f"Unexpected character: {char}")
    return tokens

def shunting_yard(tokens, precedence=None):
    """
    Converts a list of tokens (in infix notation) to a postfix list.
    Precedence mapping:
      !   : 7
      **  : 6 (power)
      *, /, % : 5
      +, - : 4
      >>, <<, & : 3
      ==, !=, >, <, >=, <= : 2
      &&  : 1
      ||, | : 0
    """
    if precedence is None:
        precedence = {
            '!': 7,
            '**': 6,
            '*': 5, '/': 5, '%': 5,
            '+': 4, '-': 4,
            '>>': 3, '<<': 3, '&': 3, '^': 3,
            '==': 2, '!=': 2, '>': 2, '<': 2, '>=': 2, '<=': 2,
            '&&': 1,
            '||': 0, '|': 0,
        }
    right_associative = {'!', '**'}
    output = []
    operators = []
    for token in tokens:
        # Check if token is numeric, identifier, or a quoted string.
        if token.replace('.', '', 1).isdigit() or token.isalnum() or (token.startswith("'") and token.endswith("'")) or '_' in token:
            output.append(token)
        elif token in precedence:
            if token in right_associative:
                while operators and operators[-1] != '(' and precedence[operators[-1]] > precedence[token]:
                    output.append(operators.pop())
            else:
                while operators and operators[-1] != '(' and precedence[operators[-1]] >= precedence[token]:
                    output.append(operators.pop())
            operators.append(token)
        elif token == '(':
            operators.append(token)
        elif token == ')':
            while operators and operators[-1] != '(':
                output.append(operators.pop())
            if operators and operators[-1] == '(':
                operators.pop()
            else:
                raise ValueError("Mismatched parentheses")
    while operators:
        op = operators.pop()
        if op in ('(', ')'):
            raise ValueError("Mismatched parentheses")
        output.append(op)
    return output

class BooleanExpressionParser:
    """
    Evaluates boolean and arithmetic expressions using tokenizing,
    postfix conversion, and evaluation routines.
    """
    def __init__(self, getter, enumerator=None):
        self.getter = getter
        self.enumerator = enumerator if enumerator is not None else {}

    def eval_operator(self, op, right, left=None):
        if op == '!':
            return not bool(right)
        elif op == '&&':
            return bool(left) and bool(right)
        elif op == '||':
            return bool(left) or bool(right)
        elif op == '==':
            return left == right
        elif op == '!=':
            return left != right
        elif op == '>':
            return left > right
        elif op == '<':
            return left < right
        elif op == '>=':
            return left >= right
        elif op == '<=':
            return left <= right
        elif op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            return left / right
        elif op == '**':
            return left ** right
        elif op == '%':
            return left % right
        elif op == '&':
            return left & right
        elif op == '|':
            return left | right
        elif op == '^':
            return left ^ right
        elif op == '>>':
            return left >> right
        elif op == '<<':
            return left << right
        else:
            raise ValueError(f"Unknown operator: {op}")

    def evaluate_postfix(self, tokens):
        """
        Evaluates a postfix expression given:
        - tokens: list of tokens in postfix order,
        - operand_func: a function that returns the value for a given token,
        - eval_operator: a function that applies an operator.
        """
        stack = []
        for token in tokens:
            if token == 'true':
                stack.append(True)
            elif token == 'false':
                stack.append(False)
            elif token.replace('.', '', 1).isdigit():
                if '.' in token:
                    stack.append(float(token))
                else:
                    stack.append(int(token))
            # @TODO Optimize this, this can be done during tokenization
            elif token.lower().startswith('0x'):
                stack.append(int(token, 16))
            elif token.lower().startswith('0b'):
                stack.append(int(token, 2))
            elif token.isalnum() or (token.startswith("'") and token.endswith("'")) or '_' in token:
                if token.startswith("'") and token.endswith("'"):
                    stack.append(token[1:-1])
                else:
                    stack.append(self.getter(token))
            else:
                if token == '!':
                    if not stack:
                        raise ValueError("Missing operand for '!'")
                    right = stack.pop()
                    stack.append(self.eval_operator(token, right))
                else:
                    if len(stack) < 2:
                        raise ValueError(f"Missing operands for '{token}'")
                    right = stack.pop()
                    left = stack.pop()
                    stack.append(self.eval_operator(token, right, left))
        if len(stack) != 1:
            raise ValueError("Invalid expression: extra items remain on the stack")
        return stack[0]

class ConfigOption:
    def __init__(self, name, option_type, default=None, external=None, data=None, description="",
                 dependencies="", options=None, choices=None, expanded=False, requires=None):
        if any(c.isspace() for c in name):
            raise ValueError(f"Option name cannot contain white space: {name}")
        
        if option_type not in ["bool", "int", "string", "multiple_choice", "action", "group"]:
            raise ValueError(f"Invalid option type {option_type}")
        
        if option_type == "multiple_choice":
            if len(choices or []) < 1:
                raise ValueError(f"Multiple choice option {name} must have at least one choice")
            if default not in (choices or []):
                raise ValueError(f"Invalid default for multiple_choice option {name}: {default}")
            if any(' ' in choice for choice in (choices or [])):
                raise ValueError(f"Choice names cannot contain white space: in option {name}")

        if option_type == "action" and not callable(default):
            raise ValueError(f"Action option {name} must have a callable default value")

        if option_type != "action" and option_type != "group" and requires:
            raise ValueError(f"The 'requires' parameter is only valid for action and group options, not {option_type} options")
        
        if requires:
            if not callable(requires):
                raise ValueError(f"Requires for option {name} must be a callable")

        if option_type == "group" and not isinstance(options, list):
            raise ValueError(f"Group option {name} must have a list of options")

        if option_type == "multiple_choice" and not isinstance(choices, list):
            raise ValueError(f"Multiple choice option {name} must have a list of choices")

        if option_type == "external" and dependencies:
            raise ValueError(f"External option {name} cannot have dependencies or evaluator")

        self.name = name
        self.option_type = option_type
        self.default = default
        self.value = choices.index(default) if (option_type == "multiple_choice") else default
        self.external = external or False
        self.data = data
        self.description = description
        self.dependencies = dependencies
        self.options = options or []
        self.choices = choices or []
        self.expanded = expanded
        self.requires = requires

        if dependencies and not callable(dependencies):
            self.postfix_dependencies = shunting_yard(tokenize(self.dependencies)) if self.dependencies else []

    def to_dict(self):
        return {
            'name': self.name,
            'type': self.option_type,
            'default': self.default,
            'external': self.external,
            'data': self.data,
            'description': self.description,
            'dependencies': self.dependencies,
            'options': [opt.to_dict() for opt in self.options],
            'choices': self.choices,
            'requires': self.requires,
        }

class pyconfix:
    def __init__(self, schem_files=[], output_file="output_config.json", output_diff_config="output_diff_config.json",
                 save_func=None, save_diff_func=None, expanded=False, show_disabled=False):
        self.schem_files = schem_files
        self.output_file = output_file
        self.output_diff_config = output_diff_config
        self.save_func = save_func
        self.save_diff_func = save_diff_func
        self.show_disabled = show_disabled
        self.expanded = expanded
        self.options = []
        self.config_name = ""
        self.graphical = False

        self.save_key = ord('s')
        self.save_diff_key = ord('d')
        self.quite_key = ord('q')
        self.collapse_key = ord('c')
        self.search_key = ord('/')
        self.help_key = ord('h')
        self.abort_key = 1  # Ctrl+A
        self.description_key = 4  # Ctrl+D

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
            if max_y > 2:
                stdscr.addstr(max_y - 2, 2, "Press 'q' to return to the menu or UP/DOWN to scroll")

            if max_y >= 4:
                display_limit = max_y - 3
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

    def _load_schem(self):
        def parse_file(filepath):
            with open(filepath, 'r') as f:
                config_data = json.load(f)
                self.config_name = config_data.get('name', 'Configuration')
                self.options += self._parse_options(config_data['options'])
                
                # Handle includes relative to current file
                base_path = os.path.dirname(os.path.abspath(filepath))
                for include_file in config_data.get('include', []):
                    include_path = os.path.join(base_path, include_file)
                    if not os.path.exists(include_path):
                        print(f"File {filepath} includes a non-existing file: {include_path}")
                        exit()
                    parse_file(include_path)

        # Parse each config file in the list
        for schem_file in self.schem_files:
            parse_file(os.path.join(os.getcwd(), schem_file))

        def combine(a, b):
            if a is None:
                return b
            if b is None:
                return a
            
            if not callable(a) and not callable(b):
                return b + (" && " if b and a else "") + a
            elif callable(a) and callable(b):
                return lambda x: a(x) and b(x)
            else:
                raise ValueError("Cannot mix callable and non-callable in a group's dependencies and requires")

        def cascade_group(options, group_dependencies = None, group_requires = None):
            """Cascade dependencies and requires from groups to their options."""
            for opt in options:
                if group_dependencies:
                    opt.dependencies = combine(group_dependencies, opt.dependencies)
                    # @TODO: Maybe mix this somehow with the constructor or remove the one there
                    opt.postfix_dependencies = shunting_yard(tokenize(opt.dependencies))
                if group_requires:
                    opt.requires = combine(group_requires, opt.requires)
                if opt.option_type == 'group':
                    cascade_group(opt.options, opt.dependencies, opt.requires)

        cascade_group(self.options)

    # @TODO: Fix callable group dependencies
    def _parse_options(self, options_data):
        parsed_options = []
        for option_data in options_data:
            option = ConfigOption(
                name=option_data['name'],
                option_type=option_data['type'],
                default=option_data.get('default'),
                description=option_data.get('description'),
                data=option_data.get('data'),
                dependencies=option_data.get('dependencies', ""),
                requires=option_data.get('requires', ""),
                choices=option_data.get('choices', []),
                expanded=self.expanded,
                options=[]
            )
            if option.option_type == 'group' and 'options' in option_data:
                option.options = self._parse_options(option_data['options'])
            elif option.option_type == 'multiple_choice':
                option.value = option.choices.index(option.default)
            parsed_options.append(option)
        return parsed_options

    def _apply_config(self, config_file=None, overlay=None):
        saved_config = {}
        if config_file:
            if not os.path.exists(config_file):
                print(f"Invalid config file: {config_file}")
                exit()
            with open(config_file, 'r') as f:
                saved_config = json.load(f)
                print(f"File loaded: {config_file}")
        elif os.path.exists(self.output_file):
            with open(self.output_file, 'r') as f:
                saved_config = json.load(f)

        if overlay:
            saved_config.update(overlay)

        self._apply_config_to_options(self.options, saved_config)

    def _apply_config_to_options(self, options, saved_config):
        for option in options:
            if option.option_type == 'group':
                self._apply_config_to_options(option.options, saved_config)
            elif option.name in saved_config:
                value = saved_config[option.name]
                if option.option_type == 'multiple_choice':
                    option.value = option.choices.index(value if value else option.default)
                else:
                    option.value = value
        self._reset_hidden_dependent_options(self.options)

    def _reset_hidden_dependent_options(self, options):
        for option in options:
            if option.option_type == 'group':
                self._reset_hidden_dependent_options(option.options)
            elif not self._is_option_available(option):
                option.value = option.default if option.option_type != 'multiple_choice' else option.choices.index(option.default)

    def _is_option_available(self, option):
        def getter_function_impl(key, options_list):
            key_upper = key.upper()
            for opt in options_list:
                if opt.option_type == "group":
                    value = getter_function_impl(key, opt.options)
                    if value is not None:
                        return value
                # Compare names in a case-insensitive manner.
                elif opt.name.upper() == key_upper:
                    default_value = opt.default
                    if opt.option_type == "multiple_choice":
                        default_value = opt.choices.index(opt.default)
                        return opt.choices[opt.value] if opt.value is not None else default_value
                    return opt.value if opt.value is not None else default_value
                # If an enum value being parsed as key instead of a key name
                elif opt.option_type == "multiple_choice":
                    for choice in opt.choices:
                        if choice.upper() == key_upper:
                            return key
            return None

        def getter_function(key):
            value = getter_function_impl(key, self.options)
            if value is None:
                raise ValueError(f"Invalid token: {key}")
            return value

        if not option.dependencies:
            return True
        if callable(option.dependencies):
            return option.dependencies(self)
        else:
            parser = BooleanExpressionParser(getter=getter_function)
            return parser.evaluate_postfix(option.postfix_dependencies)

    def _flatten_options(self, options, depth=0):
        flat_options = []
        for option in options:
            if not self._is_option_available(option):
                if option.option_type != 'group':
                    option.value = None
                if not self.show_disabled:
                    continue
            else:
                if option.value is None:
                    option.value = option.choices.index(option.default) if option.option_type == 'multiple_choice' else option.default
            flat_options.append((option, depth))
            if option.option_type == 'group' and option.expanded:
                flat_options.extend(self._flatten_options(option.options, depth + 1))
        return flat_options

    def _search_options(self, options, query, depth=0):
        flat_options = []
        for option in options:
            if self.show_disabled or self._is_option_available(option):
                if option.option_type == 'group':
                    nested_options = self._search_options(option.options, query, depth + 1)
                    if nested_options:
                        option.expanded = True
                        flat_options.append((option, depth))
                        flat_options.extend(nested_options)
                elif query.lower() in option.name.lower():
                    flat_options.append((option, depth))
        return flat_options
    
    def _description_page(self, stdscr, option):
        start_index = 0
        while True:
            stdscr.clear()
            stdscr.border(0)
            stdscr.addstr(0, 2, f" {option.name} ")
            max_y, max_x = stdscr.getmaxyx()

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
                display_limit = max_y - 3
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
            indicator = "[+]" if option.option_type == 'group' and not option.expanded else "[-]" if option.option_type == 'group' else ""
            name = f"{indicator} {option.name}" if option.option_type == 'group' else option.name
            value = ""
            if option.external:
                value = f"{option.value} [external]"
            elif option.value is None and option.option_type != 'group':
                value = "[disabled]"
            elif option.option_type == 'multiple_choice':
                value = option.choices[option.value][:10] + "..." if len(option.choices[option.value]) > 10 else option.choices[option.value]
            elif option.option_type == 'bool':
                value = "True" if option.value else "False"
            elif option.option_type in ['int', 'string']:
                value = str(option.value)[:10] + "..." if len(str(option.value)) > 10 else str(option.value)
            display_text = f"{name}: {value}" if value != "" else name
            if option.option_type == 'action':
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
            stdscr.addstr(0, 2, f" {self.config_name} ")
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
        class ExecutionSession:
            def __init__(self, config):
                self.config = config
                self.cache = {}

            def _execute_action(self, option):
                if (not self.config._is_option_available(option)) or (option.requires and not option.requires(self)):
                        return False

                if option.name in self.cache:
                    return self.cache[option.name]
                value = option.default(self)
                self.cache[option.name] = value
                return value

            def __getattr__(self, name):
                opt = self.config._get(name)
                if opt is None:
                    raise AttributeError(f"Invalid key: '{name}'")
                if opt.option_type == "multiple_choice":
                    return opt.choices[opt.value] if opt.value is not None else None
                elif opt.option_type == "action":
                    return lambda : self._execute_action(opt)
                elif opt.option_type == "group":
                    return opt.options
                return opt.value
            
        return ExecutionSession(self)._execute_action(option)

    def _handle_enter(self, flat_options, row, stdscr, search_mode):
        if not flat_options:
            return
        selected_option, _ = flat_options[row]
        if selected_option.value is None and selected_option.option_type not in ['group', 'action']:
            return
        if selected_option.external:
            return
        if selected_option.option_type == 'bool':
            selected_option.value = not selected_option.value
        elif selected_option.option_type == 'group':
            if not search_mode:
                selected_option.expanded = not selected_option.expanded
        elif selected_option.option_type in ['int', 'string']:
            self._edit_option(stdscr, selected_option)
        elif selected_option.option_type == 'multiple_choice':
            self._edit_multiple_choice_option(stdscr, selected_option)
        elif selected_option.option_type == 'action':
            curses.echo()
            curses.nocbreak()
            stdscr.keypad(False)
            curses.endwin()
            self._execute_action(selected_option)
            stdscr = curses.initscr()
            curses.noecho()
            curses.cbreak()
            stdscr.keypad(True)
            

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
            if option.option_type == 'int':
                # Handle hex format
                if new_value.lower().startswith('0x'):
                    option.value = int(new_value, 16)
                # Handle binary format
                elif new_value.lower().startswith('0b'):
                    option.value = int(new_value, 2)
                # Handle decimal format
                else:
                    option.value = int(new_value)
            elif option.option_type == 'string':
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
        if selected_option.option_type == 'group':
            selected_option.expanded = not selected_option.expanded
            if search_mode:
                for option, _ in flat_options:
                    if option in selected_option.options:
                        option.expanded = selected_option.expanded
            return current_row
        for idx, (option, _) in enumerate(flat_options):
            if option.option_type == 'group' and option.expanded and selected_option in option.options:
                option.expanded = False
                return idx
        return current_row

    def _write_config(self, as_diff=True):
        config_data = self.dump()
        with open(self.output_file, 'w') as f:
            json.dump(config_data, f, indent=4)
        if self.save_func:
            self.save_func(config_data, self.options)
        if as_diff:
            config_data = self.diff()
            with open(self.output_diff_config, 'w') as f:
                json.dump(config_data, f, indent=4)
            if self.save_diff_func:
                self.save_diff_func(config_data, self.options)

    def _save_config(self, stdscr, as_diff):
        self._write_config(as_diff)
        stdscr.clear()
        stdscr.addstr(0, 0, "Configuration saved successfully.")
        stdscr.addstr(1, 0, "Press any key to continue.")
        stdscr.refresh()
        stdscr.getch()

    def _dump(self, options):
        config_data = {}
        for option in options:
            if option.option_type == 'action':
                continue
            if option.option_type == 'group':
                nested_data = self._dump(option.options)
                if not self._is_option_available(option):
                    nested_data = {nested_key: None for nested_key in nested_data}
                config_data.update(nested_data)
            else:
                default_value = option.default if option.option_type != 'multiple_choice' else option.choices.index(option.default)
                value_to_save = default_value if option.value is None else (
                    option.choices[option.value] if option.option_type == 'multiple_choice'
                    else option.value)
                config_data[option.name] = None if not self._is_option_available(option) else value_to_save
        return config_data
    
    def __getattr__(self, name):
        opt = self._get(name)
        if opt is None:
            raise AttributeError(f"Invalid key: '{name}'")
        if opt.option_type == "multiple_choice":
            return opt.choices[opt.value] if opt.value is not None else None
        elif opt.option_type == "action":
            return lambda : self._execute_action(opt)
        elif opt.option_type == "group":
            return opt.options
        return opt.value
    
    def _get(self, key):
        def get_impl(key, options_list=self.options):
            key_upper = key.upper()
            for opt in options_list:
                if opt.option_type == "group":
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

    def get(self, key):
        """
        Get an option by its name.
        """
        return self.__getattr__(key)

    def run(self, config_file=None, overlay=None, graphical=True, as_diff=False):
        """
        Run the configuration process.
        Parameters:
            graphical (bool, optional): Indicates whether to run the configuration process
                                         in graphical (interactive) mode. Defaults to True.
            as_diff   (bool, optional): Indicates whether in the cli mode the full configuraion
                                         should be saved or the diff. In graphical mode, this
                                         option has no effect.
        """
        self.graphical = graphical
        self._load_schem()
        self._apply_config(config_file=config_file, overlay=overlay)
        if not graphical:
            self._write_config(as_diff=as_diff)
            return
        curses.wrapper(self._menu_loop)
