"""Unit tests for the ConfigOption data model (pyconfix.option).

Covers the validation matrix, enum default/index handling, dependency
precompilation, and clone_with / to_dict.
"""

import pytest

from pyconfix import ConfigOption, ConfigOptionType


# --------------------------------------------------------------------------- #
# Valid construction
# --------------------------------------------------------------------------- #

def test_bool_option():
    o = ConfigOption(name="B", option_type=ConfigOptionType.BOOL, default=True)
    assert o.option_type == ConfigOptionType.BOOL
    assert o.value is True


def test_type_accepts_string_alias():
    o = ConfigOption(name="I", option_type="int", default=3)
    assert o.option_type == ConfigOptionType.INT


def test_group_requires_list_options():
    ConfigOption(name="G", option_type=ConfigOptionType.GROUP, options=[])  # ok
    with pytest.raises(ValueError):
        ConfigOption(name="G", option_type=ConfigOptionType.GROUP)  # options=None


# --------------------------------------------------------------------------- #
# Enum handling
# --------------------------------------------------------------------------- #

def test_enum_value_is_index_of_default():
    o = ConfigOption(name="E", option_type=ConfigOptionType.ENUM,
                     default="B", choices=["A", "B", "C"])
    assert o.value == 1


def test_enum_default_coerced_to_first_choice_when_absent():
    o = ConfigOption(name="E", option_type=ConfigOptionType.ENUM,
                     default="ZZZ", choices=["A", "B"])
    assert o.default == "A"
    assert o.value == 0


def test_enum_without_choices_raises():
    with pytest.raises(ValueError):
        ConfigOption(name="E", option_type=ConfigOptionType.ENUM, choices=[])


def test_enum_choice_with_whitespace_raises():
    with pytest.raises(ValueError):
        ConfigOption(name="E", option_type=ConfigOptionType.ENUM,
                     default="a", choices=["a", "b c"])


# --------------------------------------------------------------------------- #
# Validation errors
# --------------------------------------------------------------------------- #

def test_name_with_whitespace_raises():
    with pytest.raises(ValueError):
        ConfigOption(name="has space", option_type=ConfigOptionType.BOOL, default=True)


def test_invalid_type_raises():
    with pytest.raises(ValueError):
        ConfigOption(name="X", option_type="bogus")


def test_action_requires_callable_default():
    with pytest.raises(ValueError):
        ConfigOption(name="A", option_type=ConfigOptionType.ACTION, default=5)
    ConfigOption(name="A", option_type=ConfigOptionType.ACTION, default=lambda x: 1)  # ok


def test_external_default_cannot_be_callable():
    with pytest.raises(ValueError):
        ConfigOption(name="X", option_type=ConfigOptionType.EXTERNAL, default=lambda: 1)
    ConfigOption(name="X", option_type=ConfigOptionType.EXTERNAL, default="static")  # ok


def test_external_cannot_have_dependencies():
    with pytest.raises(ValueError):
        ConfigOption(name="X", option_type=ConfigOptionType.EXTERNAL,
                     default="s", dependencies="A")


def test_requires_only_on_action_or_group():
    with pytest.raises(ValueError):
        ConfigOption(name="B", option_type=ConfigOptionType.BOOL, default=True,
                     requires=lambda x: True)


def test_requires_must_be_callable():
    with pytest.raises(ValueError):
        ConfigOption(name="A", option_type=ConfigOptionType.ACTION,
                     default=lambda x: 1, requires="not-callable")


# --------------------------------------------------------------------------- #
# Dependency precompilation
# --------------------------------------------------------------------------- #

def test_string_dependency_precompiles_postfix():
    o = ConfigOption(name="X", option_type=ConfigOptionType.INT, default=1,
                     dependencies="A && B")
    assert o.postfix_dependencies  # non-empty postfix token list


def test_callable_dependency_is_not_precompiled():
    o = ConfigOption(name="X", option_type=ConfigOptionType.INT, default=1,
                     dependencies=lambda x: True)
    assert not hasattr(o, "postfix_dependencies")


# --------------------------------------------------------------------------- #
# clone_with / to_dict
# --------------------------------------------------------------------------- #

def test_clone_with_overrides_and_leaves_original_intact():
    original = ConfigOption(name="X", option_type=ConfigOptionType.INT, default=1)
    clone = original.clone_with(name="Y", default=9)
    assert (clone.name, clone.default) == ("Y", 9)
    assert (original.name, original.default) == ("X", 1)


def test_to_dict_includes_nested_group_children():
    child = ConfigOption(name="C", option_type=ConfigOptionType.BOOL, default=False)
    group = ConfigOption(name="G", option_type=ConfigOptionType.GROUP, options=[child])
    d = group.to_dict()
    assert d["name"] == "G"
    assert d["type"] == ConfigOptionType.GROUP
    assert d["options"][0]["name"] == "C"
