# MIT License
#
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Schema loading for pyconfix: schema files -> options.

This module owns the compact schema syntax: field aliases, reserved names, type
deduction and the ``include`` directive. Reading a file is left to
:mod:`serializer`, so a schema can be in any format registered there, and the
built options are handed to the core manager.
"""

import os
import subprocess

from .option import ConfigOption, ConfigOptionType
from .serializer import available_extensions, extensions, read


def find_schema(stem):
    """Return ``stem`` with the extension of the first schema file that exists.

    Formats are tried oldest first, so JSON comes before anything registered
    later. If no file exists, raises ValueError listing the names it looked for,
    leaving out formats that are not available here.
    """
    for ext in extensions():
        if os.path.exists(stem + ext):
            return stem + ext
    names = [stem + ext for ext in available_extensions()]
    raise ValueError(f"No schema file found, looked for: {', '.join(names)}")


def load_schema(core, schema_files):
    """Read the schema files and load their options into ``core``.

    Each file is read through :mod:`serializer`, so any registered format works.
    The built options are registered on the manager via ``core.add_options``.
    """
    for schema_file in schema_files:
        _load_file(core, os.path.join(os.getcwd(), schema_file))

def _load_file(core, path):
    name, parsed = _load_file_options(core, path)
    core.config_name = name
    core.add_options(*parsed)

def _load_file_options(core, path):
    if not os.path.exists(path):
        raise ValueError(f"Config file '{path}' does not exist.")
    data = read(path)
    if not isinstance(data, dict) or len(data) != 1:
        raise ValueError(f"Schema file {path} must have exactly one top entry")
    name, options = next(iter(data.items()))
    if not isinstance(options, dict):
        raise ValueError(f"Schema file {path}: '{name}' must hold a mapping of options")
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
     "dependencies", "needs", "options", "include", "do_not_cache",
     "aliases"}
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


def shell_action(script):
    """An action body that runs ``script`` in a shell. True if it exits with 0.

    Arguments reach the script as environment variables, so a value is never
    pasted into the script and needs no quoting: read it as ``"$name"``.
    """
    def run(x, **args):
        env = {**os.environ, **{name: str(value) for name, value in args.items()}}
        return subprocess.run(script, shell=True, env=env).returncode == 0
    return run


def _script_succeeds(script):
    """Whether ``script`` exits with 0. This runs while the schema loads."""
    return subprocess.run(script, shell=True, stdout=subprocess.DEVNULL,
                          stderr=subprocess.DEVNULL).returncode == 0


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
    # Before the options, so an option can use an alias defined below it.
    aliases = options_data.get('aliases', {})
    if not isinstance(aliases, dict):
        raise ValueError("'aliases' must be a mapping of alias names")
    for alias_name, alias_data in aliases.items():
        core._register_alias(_parse_option(core, alias_name, alias_data, base_path, is_alias=True))

    parsed_options = []
    for key, value in options_data.items():
        if key == 'aliases':
            continue
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

def _parse_option(core, name, option_data, base_path=None, is_alias=False):
    if not isinstance(option_data, dict):
        if isinstance(option_data, list):
            option_data = {'choices': option_data}
        else:
            option_data = {'default': option_data}

    option_data = _normalize_fields(name, option_data)

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

    extra_fields = {key: value for key, value in option_data.items() if key not in _RESERVED_NAMES}

    default = option_data.get('default', def_value)
    if option_type_name == ConfigOptionType.ACTION and isinstance(default, str):
        default = shell_action(default)
    if option_type_name == ConfigOptionType.EXTERNAL and isinstance(default, str):
        default = _script_succeeds(default)

    if option_type_name in core.aliases:
        custom_type = core.aliases[option_type_name]
        option = core.option_from_alias(
            option_type_name,
            name=name,
            default=option_data.get('default', custom_type.default),
            description=option_data.get('description', custom_type.description),
            data=option_data.get('data', custom_type.data),
            do_not_cache=option_data.get('do_not_cache', custom_type.do_not_cache),
            dependencies=option_data.get('dependencies', custom_type.dependencies),
            needs=option_data.get('needs', custom_type.needs),
            **extra_fields,
        )
    else:
        option = ConfigOption(
            name=name,
            option_type=option_type_name,
            default=default,
            description=option_data.get('description'),
            data=option_data.get('data'),
            dependencies=option_data.get('dependencies', ""),
            needs=option_data.get('needs', ""),
            do_not_cache=option_data.get('do_not_cache', False),
            choices=option_data.get('choices', []),
            **(extra_fields if is_alias else {}),
            options=[]
        )
    if option.option_type == ConfigOptionType.GROUP and 'options' in option_data:
        option.options = parse_options(core, option_data['options'], base_path)

    return option
