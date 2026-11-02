"""Unit tests for the ConfigOption data model (pyconfix.option).

Covers the validation matrix, enum default/index handling, dependency
precompilation, and clone_with / to_dict.
"""

import pytest

from pyconfix import ConfigOption, ConfigOptionType, Core
from pyconfix.schema import parse_options


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


# --------------------------------------------------------------------------- #
# Type deduction from the value (option_type omitted); default is positional #2
# --------------------------------------------------------------------------- #

def test_default_is_second_positional_arg():
    o = ConfigOption("HOST", "localhost")
    assert o.name == "HOST" and o.default == "localhost"
    assert o.option_type == ConfigOptionType.STRING


def test_deduce_bool_int_string():
    assert ConfigOption("B", True).option_type == ConfigOptionType.BOOL
    assert ConfigOption("N", 5).option_type == ConfigOptionType.INT
    assert ConfigOption("S", "hi").option_type == ConfigOptionType.STRING


def test_deduce_bool_before_int():
    # bool is a subclass of int, so False must still deduce BOOL (not INT)
    assert ConfigOption("B", False).option_type == ConfigOptionType.BOOL


def test_deduce_enum_from_choices():
    o = ConfigOption("LEVEL", choices=["A", "B", "C"])
    assert o.option_type == ConfigOptionType.ENUM
    assert o.default == "A"                      # first choice
    o2 = ConfigOption("LEVEL", "B", choices=["A", "B", "C"])
    assert o2.default == "B"                     # positional default respected


def test_deduce_action_from_callable():
    o = ConfigOption("build", lambda x: 1)
    assert o.option_type == ConfigOptionType.ACTION


def test_deduce_group_from_options():
    child = ConfigOption("C", False)
    o = ConfigOption("G", options=[child])
    assert o.option_type == ConfigOptionType.GROUP
    assert o.options == [child]


def test_explicit_type_overrides_deduction():
    # an explicit option_type is honoured even if the value would deduce otherwise
    o = ConfigOption(name="X", option_type=ConfigOptionType.EXTERNAL, default="static")
    assert o.option_type == ConfigOptionType.EXTERNAL


def test_cannot_deduce_type_raises():
    with pytest.raises(ValueError):
        ConfigOption("NOPE")                     # no type, no value to infer from


def test_group_requires_list_options():
    ConfigOption(name="G", option_type=ConfigOptionType.GROUP, options=[])  # ok
    with pytest.raises(ValueError):
        ConfigOption(name="G", option_type=ConfigOptionType.GROUP)  # options=None


# --------------------------------------------------------------------------- #
# Enum handling
# --------------------------------------------------------------------------- #

def test_enum_value_is_the_default_choice():
    o = ConfigOption(name="E", option_type=ConfigOptionType.ENUM,
                     default="B", choices=["A", "B", "C"])
    assert o.value == "B"


def test_enum_default_coerced_to_first_choice_when_absent():
    o = ConfigOption(name="E", option_type=ConfigOptionType.ENUM,
                     default="ZZZ", choices=["A", "B"])
    assert o.default == "A"
    assert o.value == "A"


def test_enum_without_choices_raises():
    with pytest.raises(ValueError):
        ConfigOption(name="E", option_type=ConfigOptionType.ENUM, choices=[])


def test_enum_choice_with_whitespace_raises():
    with pytest.raises(ValueError):
        ConfigOption(name="E", option_type=ConfigOptionType.ENUM,
                     default="a", choices=["a", "b c"])


def test_enum_choices_must_be_a_list_not_other_sequence():
    # A non-empty, non-list sequence (tuple) is rejected as choices.
    with pytest.raises(ValueError):
        ConfigOption(name="E", option_type=ConfigOptionType.ENUM,
                     default="a", choices=("a", "b"))


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


def test_needs_only_on_action_or_group():
    with pytest.raises(ValueError):
        ConfigOption(name="B", option_type=ConfigOptionType.BOOL, default=True,
                     needs=lambda x: True)


def test_needs_must_be_callable():
    with pytest.raises(ValueError):
        ConfigOption(name="A", option_type=ConfigOptionType.ACTION,
                     default=lambda x: 1, needs=5)


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


# --------------------------------------------------------------------------- #
# Assigning value checks it against the option's type
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("default, wrong", [
    (False, "yes"), (False, 1), (3, "abc"), ("x", 5),
])
def test_assigning_wrong_type_raises_and_keeps_value(default, wrong):
    o = ConfigOption("O", default)
    with pytest.raises(ValueError, match="O"):
        o.value = wrong
    assert o.value == default


@pytest.mark.parametrize("default, right", [(False, True), (3, -4), (3, True), ("x", "y")])
def test_assigning_right_type_is_stored(default, right):
    o = ConfigOption("O", default)
    o.value = right
    assert o.value == right


@pytest.mark.parametrize("default", [False, 3, "x"])
def test_assigning_none_is_allowed(default):
    o = ConfigOption("O", default)
    o.value = None
    assert o.value is None


def enum_option():
    return ConfigOption("E", "B", choices=["A", "B", "C"])


@pytest.mark.parametrize("value", ["C", None])
def test_assigning_enum(value):
    o = enum_option()
    o.value = value
    assert o.value == value


@pytest.mark.parametrize("wrong", ["NOPE", 0, 1, True])
def test_assigning_invalid_enum_raises_and_keeps_value(wrong):
    o = enum_option()
    with pytest.raises(ValueError, match="E"):
        o.value = wrong
    assert o.value == "B"


def test_external_value_is_not_checked():
    o = ConfigOption("X", option_type=ConfigOptionType.EXTERNAL, default="s")
    o.value = 5
    assert o.value == 5


def test_action_value_is_not_checked():
    o = ConfigOption("X", option_type=ConfigOptionType.ACTION, default=lambda x: 1)
    o.value = None
    assert o.value is None


# --------------------------------------------------------------------------- #
# A default of the wrong type is rejected once, where it is written, so it can
# never fail later when a disabled option is re-enabled and gets its default back.
# Written before the fix.
# --------------------------------------------------------------------------- #

WRONG_DEFAULTS = [
    (ConfigOptionType.BOOL, "yes"),
    (ConfigOptionType.BOOL, 1),
    (ConfigOptionType.INT, "abc"),
    (ConfigOptionType.STRING, 5),
]


@pytest.mark.parametrize("option_type, default", WRONG_DEFAULTS)
def test_wrong_type_default_is_rejected_on_creation(option_type, default):
    with pytest.raises(ValueError, match="X"):
        ConfigOption("X", default, option_type=option_type)


@pytest.mark.parametrize("option_type, default", WRONG_DEFAULTS)
def test_wrong_type_default_is_rejected_in_schema(option_type, default):
    with pytest.raises(ValueError, match="X"):
        parse_options(Core(), {"X": {"type": str(option_type), "default": default}})


@pytest.mark.parametrize("option_type", [
    ConfigOptionType.BOOL, ConfigOptionType.INT, ConfigOptionType.STRING,
])
def test_missing_default_is_allowed(option_type):
    assert ConfigOption("X", option_type=option_type).value is None


@pytest.mark.parametrize("default", [False, 3, "x"])
def test_valid_default_comes_back_after_re_enabling(default):
    core, option = Core(), ConfigOption("X", default)
    core.add_options(option)
    core._sync_option_value(option, available=False)
    core._sync_option_value(option, available=True)
    assert option.value == default


# --------------------------------------------------------------------------- #
# Later assignment is checked wherever it comes from
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("default, wrong", [
    (False, "yes"), (False, 1), (3, "abc"), ("x", 5),
])
def test_wrong_type_through_apply_config_keeps_value(default, wrong):
    core, option = Core(), ConfigOption("X", default)
    core.add_options(option)
    with pytest.raises(ValueError, match="X"):
        core.apply_config({"X": wrong})
    assert option.value == default


def test_wrong_type_through_get_option_keeps_value():
    core = Core()
    core.add_options(ConfigOption("X", 3))
    with pytest.raises(ValueError, match="X"):
        core.get_option("X").value = "abc"
    assert core.X == 3


# --------------------------------------------------------------------------- #
# Enum getting an invalid value
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("wrong", ["NOPE", "b", "", 0, 1, True, 1.0])
def test_invalid_enum_assignment_keeps_value(wrong):
    o = enum_option()
    with pytest.raises(ValueError, match="E"):
        o.value = wrong
    assert o.value == "B"


@pytest.mark.parametrize("wrong", ["NOPE", 1, True])
def test_invalid_enum_through_apply_config_keeps_value(wrong):
    core, option = Core(), enum_option()
    core.add_options(option)
    with pytest.raises(ValueError, match="E"):
        core.apply_config({"E": wrong})
    assert option.value == "B"


def test_invalid_enum_default_becomes_first_choice_in_schema():
    option = parse_options(Core(), {"E": {"choices": ["A", "B"], "default": "NOPE"}})[0]
    assert option.value == "A"


def test_enum_comes_back_as_default_after_re_enabling():
    core, option = Core(), enum_option()
    core.add_options(option)
    core._sync_option_value(option, available=False)
    core._sync_option_value(option, available=True)
    assert option.value == "B"


def test_enum_with_changed_choices_rejects_its_old_default_on_re_enabling():
    core, option = Core(), enum_option()
    core.add_options(option)
    option.choices = ["A", "C"]
    core._sync_option_value(option, available=False)
    with pytest.raises(ValueError, match="E"):
        core._sync_option_value(option, available=True)


@pytest.mark.parametrize("choices", [[1, 2], [True, False], ["A", 1], ["A", None], ["A B", "C"]])
def test_enum_choices_must_be_strings_without_white_space(choices):
    with pytest.raises(ValueError, match="E"):
        ConfigOption("E", option_type=ConfigOptionType.ENUM, choices=choices)


def test_enum_choices_must_be_strings_in_schema():
    with pytest.raises(ValueError, match="E"):
        parse_options(Core(), {"E": {"choices": [1, 2]}})

