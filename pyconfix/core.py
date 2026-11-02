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

It knows nothing about files (that is :mod:`schema` and :mod:`serializer`),
nothing about the terminal (that is :mod:`tui`) and nothing about orchestration (that is
:mod:`runner`). Those higher layers drive this manager.
"""

from .option import *

def _enum_choice_exists(config, key):
    """True if ``key`` names a choice of some ENUM option — used when an enum
    choice appears as a bare token in a dependency (e.g. ``MODE == DEBUG``)."""
    return any(
        opt.option_type == ConfigOptionType.ENUM and key in opt.choices
        for opt in config.option_map.values()
    )

class EvaluationSession:
    """Evaluates dependencies and actions for one top-level call.

    This is what dependency, ``needs`` and action functions receive as ``x``. One
    session per call means nothing is shared between threads or stored on the
    core. ``cache`` keeps each option's results for the session, unless the option
    sets ``do_not_cache``. ``stack`` is the chain being evaluated (popped on
    return, so a revisit is a real cycle and diamonds are fine).
    """

    def __init__(self, config):
        self.config = config
        self.cache = {}
        self.stack = {}
        self.trace = []

    def invalidate_cache(self):
        """Forget cached results, so the next evaluation sees current values."""
        self.cache.clear()

    def _evaluate(self, option, kind, compute):
        # `kind` keeps an option's availability, needs and action result apart.
        key = (kind, option.name)
        if not option.do_not_cache and key in self.cache:
            return self.cache[key]
        if key in self.stack:
            names = [name for _, name in self.stack]
            names = names[list(self.stack).index(key):] + [option.name]
            # ValueError, not AttributeError: this runs inside __getattr__, where
            # an AttributeError would be swallowed by get()/hasattr().
            raise ValueError(f"Dependency cycle detected: {' -> '.join(names)}")
        self.stack[key] = True
        result = compute()
        self.stack.pop(key)
        if not option.do_not_cache:
            self.cache[key] = result
        return result

    def _needs_met(self, opt):
        # A group's needs apply to everything inside it, outermost first.
        if opt.parent and not self._needs_met(opt.parent):
            return False
        return not opt.needs or self._evaluate(opt, "needs", lambda: opt.needs(self))

    def _execute_action(self, opt):
        self.trace.append(opt.name)
        if not self._needs_met(opt):
            return False
        return self._evaluate(opt, "action", lambda: opt.default(self))

    def _is_option_available(self, option):
        # A disabled group disables everything inside it.
        if option.parent and not self._is_option_available(option.parent):
            return False
        if not option.dependencies: return True
        if not callable(option.dependencies): raise ValueError('Not callable dependencies')
        return self._evaluate(option, "available", lambda: option.dependencies(self))

    def get_option(self, name):
        return self.config.get_option(name)

    def get(self, key, default=None):
        """Get an option's value by its name, or ``default`` for an unknown key."""
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default

    def __getattr__(self, name):
        opt = self.config.get_option(name)
        if opt is None:
            if _enum_choice_exists(self.config, name):
                return name
            raise AttributeError(f"Invalid key: '{name}'")
        if not self._is_option_available(opt):
            if opt.option_type == ConfigOptionType.ACTION:
                return lambda: None
            return None
        if opt.option_type == ConfigOptionType.ACTION:
            return lambda: self._execute_action(opt)
        elif opt.option_type == ConfigOptionType.GROUP:
            return opt.options
        return opt.value


class Core:
    def __init__(self):
        self.options = []
        self.aliases = {}
        self.config_name = ""
        # Map of every registered option name (upper-cased) -> the option
        # itself. Kept across calls so duplicate names are rejected globally,
        # and used as an O(1) index for `_get` instead of walking the tree.
        self.option_map = {}

    def _register_alias(self, alias_option: ConfigOption, skip_duplicate_check=False):
        """Register an alias and guard against accidental duplicates."""
        if alias_option.option_type not in (ConfigOptionType.ENUM, ConfigOptionType.ACTION):
            raise ValueError("Only ENUM and ACTION aliases are supported for now")
        if alias_option.name in list(ConfigOptionType):
            raise ValueError(f"Alias '{alias_option.name}' has the name of a built-in type")

        existing = self.aliases.get(alias_option.name)
        if existing:
            if not skip_duplicate_check:
                raise ValueError(f"Alias '{alias_option.name}' already exists")
            else:
                return existing
        self.aliases[alias_option.name] = alias_option
        return alias_option

    def register_alias(self, name, option_type, choices=None, default=None, **params):
        """
        Register an alias type that can be reused when defining options. ENUM aliases
        take ``choices``. ACTION aliases take a ``default`` body, and any other keyword
        is a default value for an argument of that body.
        """
        alias_option = ConfigOption(
            name=name,
            option_type=option_type,
            choices=choices,
            default=default,
            **params,
        )
        return self._register_alias(alias_option)

    def option_from_alias(self, alias_name, name=None, **kwargs):
        """
        Create a ConfigOption from a registered alias without mutating config.options.
        """
        if name is None:
            raise ValueError("You must provide a 'name' parameter when creating an option from an alias")
        kwargs['name'] = name
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

    def add_options(self, *options, parent=None):
        """
        Append ConfigOption instances, registering their names — and the names
        of any nested group children — so names stay globally unique.

        By default the options are added at the top level; pass ``parent`` (a
        group option) to add them as its children instead. Either way every name
        is indexed for O(1) lookup.

        Raises ValueError if a name is already registered (from an earlier call
        or elsewhere in this one). Validation happens before anything is added,
        so a rejected call leaves the option tree unchanged.
        """
        new_entries = {}

        def claim(option):
            key = option.name.upper()
            if key in self.option_map or key in new_entries:
                raise ValueError(f"Duplicate option name: '{option.name}'")
            new_entries[key] = option
            for child in option.options:
                claim(child)

        for option in options:
            claim(option)

        self.option_map.update(new_entries)
        for option in options:
            option.parent = parent
        for option in new_entries.values():
            for child in option.options:
                child.parent = option
        target = parent.options if parent is not None else self.options
        target.extend(options)
        return options

    def _apply_config_to_options(self, options, saved_config):
        for option in options:
            if option.option_type == ConfigOptionType.GROUP:
                self._apply_config_to_options(option.options, saved_config)
            elif option.name in saved_config:
                value = saved_config[option.name]
                # A saved config file may be stale: a blank enum restores the default.
                if option.option_type == ConfigOptionType.ENUM and not value:
                    value = option.default
                option.value = value

    def create_evaluation_session(self):
        """Create a session for evaluating options against the current values.

        Cached results live as long as the session, so sharing one across
        several checks (a whole TUI redraw, say) evaluates each option once.
        Create a new session after any value changes, or it keeps returning the
        old answers. Options with ``do_not_cache`` are always recomputed.

        A session is not thread-safe; use one per thread.
        """
        return EvaluationSession(self)

    def _is_option_available(self, option):
        return self.create_evaluation_session()._is_option_available(option)

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
            option.value = option.default

    def _execute_action(self, option):
        session = self.create_evaluation_session()
        return session._execute_action(option), session.trace

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
                value_to_save = option.default if option.value is None else option.value
                config_data[option.name] = None if not self._is_option_available(option) else value_to_save
        return config_data

    def __getattr__(self, name):
        opt = self.get_option(name)
        if opt is None:
            if _enum_choice_exists(self, name):
                return name
            raise AttributeError(f"Invalid key: '{name}'")
        if not self._is_option_available(opt):
            if opt.option_type == ConfigOptionType.ACTION:
                return lambda : (None, [])
            return None
        if opt.option_type == ConfigOptionType.ACTION:
            return lambda : self._execute_action(opt)
        elif opt.option_type == ConfigOptionType.GROUP:
            return opt.options
        return opt.value

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
            opt = self.get_option(key)
            if value != opt.default:
                diff[key] = value
        return diff

    def get_option(self, name):
        """
        Get an option by its name.
        """
        return self.option_map.get(name.upper())

    def get(self, key, default=None):
        """
        Get an option's value by its name.

        Unknown keys should behave like a safe lookup and return the provided
        fallback value instead of raising an AttributeError.
        """
        try:
            return self.__getattr__(key)
        except AttributeError:
            return default
