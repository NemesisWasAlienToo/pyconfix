# MIT License
#
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Reading and writing of files for pyconfix.

This module owns *file* concerns: turning files on disk into plain Python data
and back. It knows nothing about options: :mod:`schema` turns the data of a
schema file into options, and core produces the data for a saved configuration.

File formats are pluggable via a small registry, so new formats (YAML, TOML,
kconfig, ...) can be added with ``register_format`` without touching the rest of
the library. A format only has to turn a file into plain data, and a malformed
file into a ``ValueError``. JSON is built in.
"""

import json
import os


# --------------------------------------------------------------------------- #
# Pluggable file formats
# --------------------------------------------------------------------------- #

class ConfigFormat:
    """Base class for a file format handler.

    Subclass and implement ``read``/``write``, set ``extensions``, then register
    with :func:`register_format`.
    """
    extensions = ()

    def available(self):
        """Whether this format can be used here. A format with an optional
        dependency overrides this, so it is not offered when that is missing."""
        return True

    def read(self, path):
        raise NotImplementedError

    def write(self, path, data):
        raise NotImplementedError


class JsonFormat(ConfigFormat):
    extensions = (".json",)

    def read(self, path):
        with open(path, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid json file: {path}") from e

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


def extensions():
    """Every registered extension, oldest format first, so JSON comes first."""
    return [ext for fmt in reversed(_FORMATS) for ext in fmt.extensions]


def available_extensions():
    """Like :func:`extensions`, leaving out formats that are not available here."""
    return [ext for fmt in reversed(_FORMATS) if fmt.available() for ext in fmt.extensions]


def read(path):
    """Read a file into plain Python data using the format for its extension."""
    return _format_for(path).read(path)


def write(path, data):
    """Write plain Python data to a file using the format for its extension."""
    _format_for(path).write(path, data)


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
        saved_config.update(read(config_file))
    return saved_config


def write_config(output_file, config_data, save_func=None):
    """Emit the current configuration to ``output_file``.

    Core produces the data (diff or full dump); this module writes it and then
    invokes the user's optional ``save_func``.
    """
    write(output_file, config_data)
    if save_func:
        save_func(config_data)
