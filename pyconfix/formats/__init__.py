# MIT License
#
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""File formats, one module each. Adding a format means adding a file here.

A format module has ``extensions``, ``available()`` and ``read(path)``. ``read`` turns
a file into plain data, and a malformed file into a ``ValueError``. Writing is not
part of a format: configurations are always saved as JSON.
"""

import importlib
import pkgutil


def _discover():
    # JSON first: it wins when a file exists in several formats, and is the fallback.
    names = sorted((module.name for module in pkgutil.iter_modules(__path__)),
                   key=lambda name: (name != "json_format", name))
    return [importlib.import_module(f"{__name__}.{name}") for name in names]


FORMATS = _discover()
