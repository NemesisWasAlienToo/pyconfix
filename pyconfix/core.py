# MIT License
#
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

"""Core configuration manager for pyconfix.

Holds the option tree and everything about options: registering aliases and
options, building options from parsed schema data, evaluating dependencies,
flattening/searching for display, executing actions, applying saved selections
and dumping/diffing the current configuration.

It knows nothing about files (that is :mod:`serializer`), nothing about the
terminal (that is :mod:`tui`) and nothing about orchestration (that is
:mod:`runner`). Those higher layers drive this manager.
"""

from .option import *


class Core:
    def __init__(self):
        self.options = []
        self.aliases = {}
        self.config_name = ""
        # Names of every registered option (upper-cased), kept across calls so
        # duplicates are rejected globally, not just within a single add.
        self.option_names = set()

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
        Append ConfigOption instances, registering their names — and the names
        of any nested group children — so names stay globally unique.

        Raises ValueError if a name is already registered (from an earlier call
        or elsewhere in this one). Validation happens before anything is added,
        so a rejected call leaves the option tree unchanged.
        """
        new_keys = set()

        def claim(option):
            key = option.name.upper()
            if key in self.option_names or key in new_keys:
                raise ValueError(f"Duplicate option name: '{option.name}'")
            new_keys.add(key)
            for child in option.options:
                claim(child)

        for option in options:
            claim(option)

        self.option_names |= new_keys
        self.options.extend(options)
        return options

    def _claim_name(self, name):
        """Reserve a single option name, raising if it is already registered.

        Used when options are appended one at a time (e.g. the decorator API)
        rather than through :meth:`add_options`, so those names take part in the
        same global uniqueness guarantee.
        """
        key = name.upper()
        if key in self.option_names:
            raise ValueError(f"Duplicate option name: '{name}'")
        self.option_names.add(key)

    def _apply_config_to_options(self, options, saved_config):
        for option in options:
            if option.option_type == ConfigOptionType.GROUP:
                self._apply_config_to_options(option.options, saved_config)
            elif option.name in saved_config:
                value = saved_config[option.name]
                if option.option_type == ConfigOptionType.ENUM:
                    # A saved config file is user-facing and may be stale. An
                    # empty/blank value restores the default; any other value
                    # that is not a valid choice is a real error, so raise a
                    # clear, named message instead of a bare "not in list".
                    choice = value if value else option.default
                    if choice not in option.choices:
                        raise ValueError(
                            f"Invalid value '{value}' for enum option '{option.name}'; "
                            f"expected one of {option.choices}"
                        )
                    option.value = option.choices.index(choice)
                else:
                    option.value = value

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
                if opt is None:
                    raise AttributeError(f"Invalid key: '{name}'")
                if not self.config._is_option_available(opt):
                    if opt.option_type == ConfigOptionType.ACTION:
                        return lambda: None
                    return None
                if opt.option_type == ConfigOptionType.ENUM:
                    return opt.choices[opt.value] if opt.value is not None else None
                elif opt.option_type == ConfigOptionType.ACTION:
                    return lambda: self._execute_action(opt)
                elif opt.option_type == ConfigOptionType.GROUP:
                    return opt.options
                return opt.value

        return ExecutionSession(self, option.name)._execute_action(option), trace

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
                if opt.name.upper() == key_upper:
                    return True, opt
                if opt.option_type == ConfigOptionType.GROUP:
                    found, value = get_impl(key, opt.options)
                    if found:
                        return True, value
            return False, None
        found, value = get_impl(key)
        if not found:
            return None
        return value

    # ----------------------------------------------------------------------- #
    # Applying selections and producing output data
    # ----------------------------------------------------------------------- #

    def apply_config(self, saved_config=None):
        """Apply saved selections (a dict) to the options.

        The serializer reads any config files into ``saved_config``; this method
        is where the selections are imported onto the option tree.
        """
        saved_config = dict(saved_config) if saved_config else {}
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
            # dump() already emits None for unavailable options, so reuse that
            # instead of recomputing availability for every key.
            if value is None:
                continue
            opt = self._get(key)
            if value != opt.default:
                diff[key] = value
        return diff

    def get(self, key, default=None):
        """
        Get an option by its name.

        Unknown keys should behave like a safe lookup and return the provided
        fallback value instead of raising an AttributeError.
        """
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default
