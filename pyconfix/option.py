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

class ConfigOption:
    def __init__(self, name, option_type:ConfigOptionType, default=None, data=None, description="",
                 dependencies=None, options=None, choices=None, expanded=False, requires=None):
        if any(c.isspace() for c in name):
            raise ValueError(f"Option name cannot contain white space: {name}")
        
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

        if option_type != ConfigOptionType.ACTION and option_type != ConfigOptionType.GROUP and requires:
            raise ValueError(f"The 'requires' parameter is only valid for action and group options, not {option_type} options")
        
        if requires:
            if not callable(requires):
                raise ValueError(f"Requires for option {name} must be a callable")

        if option_type == ConfigOptionType.GROUP and not isinstance(options, list):
            raise ValueError(f"Group option {name} must have a list of options")

        if option_type == ConfigOptionType.ENUM and not isinstance(choices, list):
            raise ValueError(f"Multiple choice option {name} must have a list of choices")

        if option_type == ConfigOptionType.EXTERNAL and dependencies:
            raise ValueError(f"External option {name} cannot have dependencies or evaluator")

        self.name = name
        self.option_type = option_type
        self.default = default
        self.value = choices.index(default) if (option_type == ConfigOptionType.ENUM) else default
        self.data = data
        self.description = description
        self.dependencies = dependencies
        self.options = options or []
        self.choices = choices or []
        self.expanded = expanded
        self.requires = requires

        if dependencies and not callable(dependencies):
            self.postfix_dependencies = shunting_yard(tokenize(self.dependencies)) if self.dependencies else []

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
            'requires': self.requires,
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
            'requires': self.requires,
        }
        params.update(kwargs)
        return ConfigOption(**params)
