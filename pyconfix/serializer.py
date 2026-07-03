# MIT License
#
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Reading and writing of config files for pyconfix.

This module owns *file* concerns: turning files on disk into plain Python data
and back. It does not know how options work — it hands the parsed data to the
core manager (``core.import_options`` / ``core.apply_config``) and, when writing,
asks core for the data to emit (``core.dump`` / ``core.diff``).

It is intentionally modular: file formats are pluggable via a small registry, so
new formats (YAML, TOML, kconfig, ...) can be added with ``register_format``
without touching the rest of the library. JSON is built in.
"""

import json
import os
import sys

from .parser import BooleanExpressionParser
from .option import ConfigOption, ConfigOptionType


# --------------------------------------------------------------------------- #
# Pluggable file formats
# --------------------------------------------------------------------------- #

class ConfigFormat:
    """Base class for a file format handler.

    Subclass and implement ``read``/``write``, set ``extensions``, then register
    with :func:`register_format`.
    """
    extensions = ()

    def read(self, path):
        raise NotImplementedError

    def write(self, path, data):
        raise NotImplementedError


class JsonFormat(ConfigFormat):
    extensions = (".json",)

    def read(self, path):
        with open(path, "r") as f:
            return json.load(f)

    def write(self, path, data):
        with open(path, "w") as f:
            json.dump(data, f, indent=4)


_DEFAULT_FORMAT = JsonFormat()
_FORMATS = [_DEFAULT_FORMAT]


def register_format(fmt):
    """Register a new file format handler (takes precedence over built-ins)."""
    _FORMATS.insert(0, fmt)
    return fmt


def _format_for(path):
    ext = os.path.splitext(path)[1].lower()
    for fmt in _FORMATS:
        if ext in fmt.extensions:
            return fmt
    return _DEFAULT_FORMAT


def read(path):
    """Read a file into plain Python data using the format for its extension."""
    return _format_for(path).read(path)


def write(path, data):
    """Write plain Python data to a file using the format for its extension."""
    _format_for(path).write(path, data)


# --------------------------------------------------------------------------- #
# Schema loading (files -> core options)
# --------------------------------------------------------------------------- #

def load_schema(core, schem_files):
    """Read the schema files and load their options into ``core``.

    This module owns turning the compact schema syntax into ``ConfigOption``
    objects; the built options are registered on the manager via
    ``core.add_options`` and their dependencies are compiled against the manager's
    option tree. Applying saved selections stays in core.
    """
    for schem_file in schem_files:
        _load_file(core, os.path.join(os.getcwd(), schem_file))
    finalize_dependencies(core)


def _load_file(core, path):
    if not os.path.exists(path):
        sys.exit(f"Config file '{path}' does not exist.")
    data = read(path)
    if len(data.keys()) != 1:
        sys.exit(f"Json file {path} has more than one top entry")

    name, options = next(iter(data.items()))
    base_path = os.path.dirname(os.path.abspath(path))

    # Includes are a file concern; resolve them here. Included options are loaded
    # before the including file's own options (matching the original ordering).
    includes = options.get("include", []) if isinstance(options, dict) else []
    for include_file in includes:
        include_path = os.path.join(base_path, include_file)
        if not os.path.exists(include_path):
            raise ValueError(f"A non-existing file was included: {include_path}")
        _load_file(core, include_path)

    core.config_name = name
    core.add_options(*parse_options(core, options))


# --------------------------------------------------------------------------- #
# Compact-syntax parsing: schema dict -> ConfigOption objects
# --------------------------------------------------------------------------- #

def parse_options(core, options_data):
    """Build the top-level options for one schema section into a list.

    Nested group children are attached to their group; only the returned
    top-level options should be handed to ``core.add_options``.
    """
    parsed_options = []
    for key, value in options_data.items():
        # 'include' is a file directive handled during loading, not an option.
        if key == 'include':
            continue
        parsed_options.append(_parse_option(core, key, value))
    return parsed_options


def _parse_option(core, name, option_data):
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
        expanded=core.expanded,
        options=[]
    )
    try:
        option.option_type = ConfigOptionType(option_type_name)
    except ValueError:
        custom_type = core.aliases.get(option_type_name)
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
        option.options = parse_options(core, option_data['options'])
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
            found, value = getter_function_impl(key, core.options)
            if not found:
                raise ValueError(f"Invalid token: {key}")
            return value

        if not option.dependencies:
            return lambda x: True
        if callable(option.dependencies):
            return lambda x: option.dependencies(x)
        else:
            parser = BooleanExpressionParser(getter=getter_function)
            return lambda x: parser.evaluate_postfix(option.postfix_dependencies)
    option.dependencies = _is_option_available_impl(option, option.name)
    return option


def finalize_dependencies(core):
    """Cascade group dependencies/requires down to child options.

    Called once after all schema files have been loaded.
    """
    def combine(a, b):
        if a is None:
            return b
        if b is None:
            return a

        if not callable(a) or not callable(b):
            raise ValueError("Combining non-callable")
        return lambda x: a(x) and b(x)

    def cascade_group(options, group_dependencies=None, group_requires=None):
        for opt in options:
            if group_dependencies:
                opt.dependencies = combine(group_dependencies, opt.dependencies)
            if group_requires:
                opt.requires = combine(group_requires, opt.requires)
            if opt.option_type == ConfigOptionType.GROUP:
                cascade_group(opt.options, opt.dependencies, opt.requires)

    cascade_group(core.options)


# --------------------------------------------------------------------------- #
# Saved-selection loading and writing
# --------------------------------------------------------------------------- #

def read_config_files(config_files):
    """Read and merge saved-configuration files into a single dict."""
    saved_config = {}
    for config_file in config_files:
        if not os.path.exists(config_file):
            raise ValueError(f"Invalid config file: {config_file}")
        try:
            saved_config.update(read(config_file))
        except json.JSONDecodeError:
            print(f"Invalid json file: {config_file}")
            exit(1)
    return saved_config


def write_config(core, output_diff=True):
    """Emit the current configuration to ``core.output_file``.

    Core produces the data (diff or full dump); this module writes it and then
    invokes the user's optional ``save_func``.
    """
    config_data = core.diff() if output_diff else core.dump()
    write(core.output_file, config_data)
    if core.save_func:
        core.save_func(config_data, core, output_diff)
