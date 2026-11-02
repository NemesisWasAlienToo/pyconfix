# MIT License
#
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""YAML support for schema files.

Everything YAML lives here. PyYAML is optional (``pip install pyconfix[yaml]``), so
it is only imported when a YAML file is read. The rest of the library only sees
the plain data :func:`read` returns, the same shape a JSON file gives.
"""

import importlib.util

extensions = (".yaml", ".yml")


def _import_yaml():
    try:
        import yaml
    except ImportError as e:
        raise ImportError("Reading YAML files needs PyYAML: pip install pyconfix[yaml]") from e
    return yaml


def _loader(yaml):
    """A safe loader that leaves dates as strings, which is all JSON can hold."""
    class Loader(yaml.SafeLoader):
        pass

    Loader.yaml_implicit_resolvers = {
        first: [resolver for resolver in resolvers if resolver[0] != "tag:yaml.org,2002:timestamp"]
        for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    return Loader


def _check_keys(data, path):
    """Reject the keys JSON cannot produce, like ``on:`` (a bool) or ``1:``."""
    if isinstance(data, dict):
        for key, value in data.items():
            if not isinstance(key, str):
                raise ValueError(f"Invalid yaml file: {path}: key {key!r} is not a string")
            _check_keys(value, path)
    elif isinstance(data, list):
        for value in data:
            _check_keys(value, path)


def available():
    return importlib.util.find_spec("yaml") is not None


def read(path):
    yaml = _import_yaml()
    with open(path, "r") as f:
        try:
            data = yaml.load(f, Loader=_loader(yaml))
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid yaml file: {path}") from e
    if not isinstance(data, dict):
        raise ValueError(f"Invalid yaml file: {path}: the top level must be a mapping")
    _check_keys(data, path)
    return data
