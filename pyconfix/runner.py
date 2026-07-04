# MIT License
#
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Top-level runner for pyconfix.

``pyconfix`` is the object users construct. It is the top of the dependency
graph: it owns a :class:`~pyconfix.core.Core` and calls the serializer (files),
core (options) and, when interactive, the TUI (curses). Nothing lower calls back
up here.

All option-related access (``add_options``, ``register_alias``, ``get``,
attribute lookups, actions, ...) is forwarded to the underlying Core, so from a
user's perspective ``pyconfix`` behaves exactly as before while the actual option
logic lives in Core.
"""

from .core import Core
from .option import ConfigOption, ConfigOptionType
from . import serializer


class pyconfix:
    def __init__(self):
        # Bypass __getattr__ during construction.
        object.__setattr__(self, "_core", Core())

    def __getattr__(self, name):
        # Only reached for attributes not found on the runner itself. Everything
        # option-related lives on the Core, so forward there.
        if name == "_core":
            raise AttributeError(name)
        return getattr(self._core, name)

    @property
    def core(self):
        """The underlying option manager."""
        return self._core

    def load_schem(self, schem_files=["pyconfixfile.json"]):
        """Read and import schema files into the core option tree."""
        serializer.load_schema(self._core, schem_files)
        return self

    def apply_config(self, config_files=None, overlay=None):
        """Apply saved selections (and an optional overlay) to the options.

        Every named config file must exist (a missing one raises). With no
        argument nothing is loaded and the schema defaults are kept; callers that
        want to load a saved file "only if it's there" should check existence
        first (see example.py).
        """
        saved_config = serializer.read_config_files(config_files or [])
        if overlay: saved_config.update(overlay)
        self._core.apply_config(saved_config)
        return self

    # ----------------------------------------------------------------------- #
    # Decorator API for registering actions and groups
    # ----------------------------------------------------------------------- #

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
        if group is not None:
            return GroupProxy(group)
        else:
            return GroupProxy(self._core)

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
        self._core.options.append(ConfigOption(
            name=name,
            option_type=ConfigOptionType.GROUP,
            dependencies=dependencies,
            options=[]
        ))

        # Get reference to the newly added option
        group_option = self._core.options[-1]
        return self._create_action_decorator(group=group_option)

    def save(self, output_file="output_config.json", output_diff=False, save_func=None):
        """Write the current configuration to ``output_file``.

        Writes the full dump, or only the diff from defaults when ``output_diff``
        is True, then invokes the optional ``save_func`` with the written data.
        Returns the data that was written.
        """
        config_data = self._core.diff() if output_diff else self._core.dump()
        serializer.write_config(output_file, config_data, save_func)
        return config_data

    def run(self, output_file="output_config.json", show_disabled=False, save_func=None):
        """
        Run the interactive TUI configuration process.
        """
        from .tui import Tui
        Tui(self, output_file=output_file, show_disabled=show_disabled, save_func=save_func).run()
