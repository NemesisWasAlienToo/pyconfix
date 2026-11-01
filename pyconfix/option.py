# MIT License
# 
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

from enum import StrEnum
from .parser import *

class ConfigOptionType(StrEnum):
    BOOL = "bool"
    INT = "int"
    STRING="string"
    ENUM = "enum"
    ACTION= "action"
    GROUP = "group"
    EXTERNAL = "external"

def _enum_choice_exists(config, key):
    """True if ``key`` names a choice of some ENUM option — used when an enum
    choice appears as a bare token in a dependency (e.g. ``MODE == DEBUG``)."""
    key_upper = key.upper()
    return any(
        opt.option_type == ConfigOptionType.ENUM
        and any(choice.upper() == key_upper for choice in opt.choices)
        for opt in config.option_map.values()
    )


class ConfigOption:
    VALUE_TYPES = {
        ConfigOptionType.BOOL: bool,
        ConfigOptionType.INT: int,
        ConfigOptionType.STRING: str,
    }

    def __init__(self, name, default=None, option_type:ConfigOptionType=None, data=None, description="",
                 dependencies=None, options=None, choices=None, expanded=False, needs=None, do_not_cache=False):
        if any(c.isspace() for c in name):
            raise ValueError(f"Option name cannot contain white space: {name}")

        # When no type is given, deduce it from the provided value — mirroring the
        # JSON short forms (choices -> enum, then bool/int/string), plus the
        # Python-only cases (callable -> action, options -> group).
        if option_type is None:
            if choices:
                option_type = ConfigOptionType.ENUM
            elif isinstance(default, bool):
                option_type = ConfigOptionType.BOOL
            elif isinstance(default, int):
                option_type = ConfigOptionType.INT
            elif isinstance(default, str):
                option_type = ConfigOptionType.STRING
            elif callable(default):
                option_type = ConfigOptionType.ACTION
            elif options is not None:
                option_type = ConfigOptionType.GROUP
            else:
                raise ValueError(
                    f"Option '{name}': cannot deduce a type; pass 'option_type' or "
                    "a value to infer it from (default, choices or options)")

        # For custom types from python API, user can jsut create factory functions
        # no fancy custom type detection is needed
        try:
            option_type = ConfigOptionType(option_type)
        except Exception:
            raise ValueError(f"Option '{name}' has an invalid type '{option_type}'")
        
        if option_type == ConfigOptionType.ENUM:
            if len(choices or []) < 1:
                raise ValueError(f"Multiple choice option {name} must have at least one choice")
            if default not in (choices or []):
                default = choices[0]
            if any(' ' in choice for choice in (choices or [])):
                raise ValueError(f"Choice names cannot contain white space: in option {name}")

        if option_type == ConfigOptionType.ACTION and not callable(default):
            raise ValueError(f"Action option {name} must have a callable default value")

        if option_type != ConfigOptionType.ACTION and option_type != ConfigOptionType.GROUP and needs:
            raise ValueError(f"The 'needs' parameter is only valid for action and group options, not {option_type} options")
        
        if needs:
            if not callable(needs):
                raise ValueError(f"The 'needs' for option {name} must be a callable")

        if option_type == ConfigOptionType.GROUP and not isinstance(options, list):
            raise ValueError(f"Group option {name} must have a list of options")

        if option_type == ConfigOptionType.ENUM and not isinstance(choices, list):
            raise ValueError(f"Multiple choice option {name} must have a list of choices")

        if option_type == ConfigOptionType.EXTERNAL and dependencies:
            raise ValueError(f"External option {name} cannot have dependencies or evaluator")

        if option_type == ConfigOptionType.EXTERNAL and callable(default):
            raise ValueError(f"External option {name} cannot have a callable default")

        self.name = name
        self.option_type = option_type
        self.default = default
        # Not the setter: a schema option is built as STRING before its real type
        # is known, and defaults are not user values.
        self._value = default
        self.data = data
        self.description = description
        self.dependencies = self._compile_dependencies(dependencies)
        self.options = options or []
        self.choices = choices or []
        self.expanded = expanded
        self.needs = needs
        self.do_not_cache = do_not_cache

    def _compile_dependencies(self, dependencies):
        """Compile a dependency expression into a ``predicate(x) -> bool``.

        ``x`` is the evaluation session, so names resolve when the predicate runs.
        By then the whole tree is registered, whatever order options were added in.
        """
        if not dependencies:
            return None
        if callable(dependencies):
            return dependencies
        if not isinstance(dependencies, str):
            raise ValueError(f"The 'dependencies' for option {self.name} must be a string or a callable")

        self.postfix_dependencies = shunting_yard(tokenize(dependencies))

        def getter(x, key):
            if x.get_option(key) is None:
                # A bare enum choice used as a literal token (e.g. LEVEL == DEBUG).
                if _enum_choice_exists(x.config, key):
                    return key
                raise ValueError(f"Invalid token: {key}")
            # Resolve through the evaluation session `x`, so values match attribute
            # access and the chain of options being evaluated carries over (cycles).
            return getattr(x, key)

        return lambda x: BooleanExpressionParser().evaluate_postfix(
            self.postfix_dependencies, getter=lambda key: getter(x, key))

    @property
    def value(self):
        """The current value. An enum holds the name of its choice."""
        return self._value

    @value.setter
    def value(self, value):
        """Store a value, raising ValueError if it does not fit the option's type.

        None is how a disabled option is stored.
        """
        if self.option_type == ConfigOptionType.ENUM:
            valid = value in self.choices
        else:
            valid = isinstance(value, self.VALUE_TYPES.get(self.option_type, object))
        if value is not None and not valid:
            raise ValueError(f"Invalid value '{value}' for {self.option_type} option '{self.name}'")
        self._value = value

    def to_dict(self):
        return {
            'name': self.name,
            'type': self.option_type,
            'default': self.default,
            'data': self.data,
            'description': self.description,
            'dependencies': self.dependencies,
            'options': [opt.to_dict() for opt in self.options],
            'choices': self.choices,
            'needs': self.needs,
            'do_not_cache': self.do_not_cache,
        }
    
    def clone_with(self, **kwargs):
        """
        This method creates a copy of the current instance and updates its attributes with the values 
        specified in the keyword arguments.
        """
        params = {
            'name': self.name,
            'option_type': self.option_type,
            'default': self.default,
            'data': self.data,
            'description': self.description,
            'dependencies': self.dependencies,
            'options': self.options,
            'choices': self.choices,
            'expanded': self.expanded,
            'needs': self.needs,
            'do_not_cache': self.do_not_cache,
        }
        params.update(kwargs)
        return ConfigOption(**params)
