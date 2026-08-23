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
    name, parsed = _load_file_options(core, path)
    core.config_name = name
    core.add_options(*parsed)

def _load_file_options(core, path):
    if not os.path.exists(path):
        raise ValueError(f"Config file '{path}' does not exist.")
    data = read(path)
    if len(data.keys()) != 1:
        raise ValueError(f"Json file {path} has more than one top entry")
    name, options = next(iter(data.items()))
    base_path = os.path.dirname(os.path.abspath(path))
    parsed = parse_options(core, options, base_path)
    return name, parsed

# Short aliases accepted for the wordier option fields, so a schema can say e.g.
# "deps" instead of "dependencies". Like the canonical field names, these keys
# are reserved and cannot be used as option names.
_FIELD_ALIASES = {
    "deps": "dependencies",
    "desc": "description",
    "opts": "options",
    "def": "default",
}

# Every key the schema parser treats as an option field (canonical names, their
# short aliases, and the `include` directive). These are reserved: they cannot be
# used as option names, since a name and a field share the same dict namespace.
_RESERVED_NAMES = (
    {"type", "default", "choices", "description", "data",
     "dependencies", "requires", "options", "include"}
    | set(_FIELD_ALIASES)
)


def _normalize_fields(name, option_data):
    """Rewrite any short field aliases (e.g. ``deps``) to their canonical names.

    Raises if both an alias and its canonical field are set on the same option.
    """
    normalized = dict(option_data)
    for alias, canonical in _FIELD_ALIASES.items():
        if alias in normalized:
            if canonical in normalized:
                raise ValueError(
                    f"Option '{name}' sets both '{alias}' and '{canonical}'")
            normalized[canonical] = normalized.pop(alias)
    return normalized


def parse_options(core, options_data, base_path=None):
    """Build the top-level options for one schema section into a list.

    Nested group children are attached to their group; only the returned
    top-level options should be handed to ``core.add_options``. An ``include``
    directive is resolved in place: the referenced files' options are inserted at
    the include's location, so an include inside a group's options becomes part
    of that group. The included file's own top-level name is discarded.
    """
    if base_path is None:
        base_path = os.getcwd()
    parsed_options = []
    for key, value in options_data.items():
        if key == 'include':
            for include_file in value:
                include_path = os.path.join(base_path, include_file)
                if not os.path.exists(include_path):
                    raise ValueError(f"A non-existing file was included: {include_path}")
                name, options = _load_file_options(core, include_path)
                parsed_options.extend(options)
            continue
        if key in _RESERVED_NAMES:
            raise ValueError(
                f"'{key}' is a reserved schema field name and cannot be used as "
                "an option name")
        parsed_options.append(_parse_option(core, key, value, base_path))
    return parsed_options

def _parse_option(core, name, option_data, base_path=None):
    if not isinstance(option_data, dict):
        if isinstance(option_data, list):
            option_data = {'choices': option_data}
        else:
            option_data = {'default': option_data}

    option_data = _normalize_fields(name, option_data)

    if 'requires' in option_data:
        # 'requires' must be a callable, which JSON cannot express; it may be
        # supported in the schema later, but for now it is Python-API only.
        raise ValueError(
            f"Option '{name}': 'requires' is not supported in the JSON schema; "
            "define it via the Python API instead")

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
            description=option_data.get('description', custom_type.description),
            dependencies=option_data.get('dependencies', custom_type.dependencies),
        )
    if option.option_type == ConfigOptionType.GROUP and 'options' in option_data:
        option.options = parse_options(core, option_data['options'], base_path)
    elif option.option_type == ConfigOptionType.ENUM:
        # Built as STRING above, so ConfigOption.__init__ did not coerce an
        # out-of-range default; do it here (mirroring the ENUM constructor path)
        # instead of letting choices.index() raise on a bad default.
        if option.default not in option.choices:
            option.default = option.choices[0]
        option.value = option.choices.index(option.default)

    option.dependencies = _compile_dependencies(core, option)
    return option


def _enum_choice_exists(options, key):
    """True if ``key`` names a choice of some ENUM option — used when an enum
    choice appears as a bare token in a dependency (e.g. ``MODE == DEBUG``)."""
    key_upper = key.upper()
    for opt in options:
        if opt.option_type == ConfigOptionType.GROUP:
            if _enum_choice_exists(opt.options, key):
                return True
        elif opt.option_type == ConfigOptionType.ENUM:
            if any(choice.upper() == key_upper for choice in opt.choices):
                return True
    return False


def _compile_dependencies(core, option):
    """Compile ``option.dependencies`` into a ``predicate(x) -> bool``.

    Name resolution reuses ``core._get`` (case-insensitive, descends into groups)
    rather than re-walking the option tree, so there is a single resolver shared
    with attribute access. The predicate is evaluated lazily, by which point the
    whole tree has been registered.
    """
    if not option.dependencies:
        return lambda x: True
    if callable(option.dependencies):
        return lambda x: option.dependencies(x)

    root_upper = option.name.upper()

    def getter(key):
        if key.upper() == root_upper:
            raise ValueError(f"Cycle detected in the dependency of {option.name}: '{option.name}'")
        opt = core._get(key)
        if opt is not None:
            if opt.option_type == ConfigOptionType.ENUM:
                return opt.choices[opt.value] if opt.value is not None else opt.default
            return opt.value if opt.value is not None else opt.default
        # A bare enum choice used as a literal token (e.g. LEVEL == DEBUG).
        if _enum_choice_exists(core.options, key):
            return key
        raise ValueError(f"Invalid token: {key}")

    parser = BooleanExpressionParser(getter=getter)
    return lambda x: parser.evaluate_postfix(option.postfix_dependencies)


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
                if opt.option_type in [ConfigOptionType.GROUP, ConfigOptionType.ACTION]:
                    opt.requires = combine(group_requires, opt.requires)
            if opt.option_type == ConfigOptionType.GROUP:
                cascade_group(opt.options, opt.dependencies, opt.requires)

    cascade_group(core.options)


# --------------------------------------------------------------------------- #
# Saved-selection loading and writing
# --------------------------------------------------------------------------- #

def read_config_files(config_files):
    """Read and merge saved-configuration files into a single dict.

    Every listed file must exist; a missing file raises ``ValueError``. Callers
    that want "load it only if it's there" should check existence first.
    """
    saved_config = {}
    for config_file in config_files:
        if not os.path.exists(config_file):
            raise ValueError(f"Invalid config file: {config_file}")
        try:
            saved_config.update(read(config_file))
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid json file: {config_file}") from e
    return saved_config


def write_config(output_file, config_data, save_func=None):
    """Emit the current configuration to ``output_file``.

    Core produces the data (diff or full dump); this module writes it and then
    invokes the user's optional ``save_func``.
    """
    write(output_file, config_data)
    if save_func:
        save_func(config_data)
