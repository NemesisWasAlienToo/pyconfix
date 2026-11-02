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

A file is read by the module in :mod:`formats` that handles its extension, and
any file without one is read as JSON. Configurations are always written as JSON.
"""

import json
import os

from .formats import FORMATS


def extensions():
    """Every supported extension, JSON first."""
    return [ext for fmt in FORMATS for ext in fmt.extensions]


def available_extensions():
    """Like :func:`extensions`, leaving out formats that are not available here."""
    return [ext for fmt in FORMATS if fmt.available() for ext in fmt.extensions]


def read(path):
    """Read a file into plain Python data using the format for its extension."""
    ext = os.path.splitext(path)[1].lower()
    fmt = next((fmt for fmt in FORMATS if ext in fmt.extensions), FORMATS[0])
    return fmt.read(path)


def write(path, data):
    """Write plain Python data to a JSON file."""
    with open(path, "w") as f:
        json.dump(data, f, indent=4)


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
