"""Regression tests for issues found in the 2026-10-29 project review.

Written before the fixes: every test here pins the *intended* behavior and is
expected to fail until its issue is fixed. Grouped by issue; each section's
header states the bug and the expected behavior.
"""

import json
import sys

import pytest

from pyconfix import pyconfix, Core, ConfigOption, ConfigOptionType
from pyconfix import __main__ as cli
from pyconfix.parser import tokenize, shunting_yard, BooleanExpressionParser


def write_schema(tmp_path, monkeypatch, schema, name="schema.json"):
    (tmp_path / name).write_text(json.dumps(schema))
    monkeypatch.chdir(tmp_path)
    return name


def ev(expr, **values):
    parser = BooleanExpressionParser(getter=lambda k: values[k])
    return parser.evaluate_postfix(shunting_yard(tokenize(expr)))


# --------------------------------------------------------------------------- #
# 1. A disabled option must disable the options that depend on it.
#    The dependency getter falls back to the *default* of an unavailable
#    option, so a dependent sees True even though its parent is disabled.
# --------------------------------------------------------------------------- #

CHAIN_SCHEMA = {"Chain": {
    "MASTER": False,
    "A": {"default": True, "deps": "MASTER"},
    "B": {"default": True, "deps": "A"},
    "C": {"default": 1, "deps": "B"},
}}


@pytest.fixture
def chain(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, CHAIN_SCHEMA)
    return lambda **overlay: pyconfix().load_schem([name]).apply_config(overlay=overlay)


def test_dependent_of_disabled_option_is_disabled(chain):
    cfg = chain()
    assert cfg.A is None
    assert cfg.B is None


def test_disable_propagates_transitively(chain):
    cfg = chain()
    assert cfg.C is None
    assert cfg.dump() == {"MASTER": False, "A": None, "B": None, "C": None}


def test_enabling_root_enables_whole_chain(chain):
    cfg = chain(MASTER=True)
    assert (cfg.A, cfg.B, cfg.C) == (True, True, 1)


def test_diff_omits_transitively_disabled_options(chain):
    assert chain().diff() == {}


# --------------------------------------------------------------------------- #
# 3. Group dependencies must cascade to children for groups built in Python,
#    not only for groups loaded from a schema. Attribute access and dump()
#    must agree.
# --------------------------------------------------------------------------- #

def test_python_group_dependency_disables_child_attribute():
    cfg = pyconfix()
    group = cfg.group_option("G", dependencies=lambda x: False)
    group.add_options(ConfigOption("CHILD", 5))
    assert cfg.CHILD is None


def test_python_group_attribute_access_matches_dump():
    cfg = pyconfix()
    group = cfg.group_option("G", dependencies=lambda x: False)
    group.add_options(ConfigOption("CHILD", 5))
    assert cfg.dump()["CHILD"] == cfg.CHILD


def test_core_group_option_dependency_disables_child():
    core = Core()
    core.add_options(ConfigOption(
        "G", option_type=ConfigOptionType.GROUP, dependencies=lambda x: False,
        options=[ConfigOption("CHILD", 5)]))
    assert core.CHILD is None


def test_python_group_action_disabled_with_group():
    cfg = pyconfix()
    group = cfg.group_option("G", dependencies=lambda x: False)

    @group.action_option()
    def act(x):
        return 1

    assert cfg.act() == (None, [])


def test_included_group_dependency_cascades(tmp_path, monkeypatch):
    other = pyconfix()
    group = other.group_option("G", dependencies=lambda x: x.HOST_ON)
    group.add_options(ConfigOption("CHILD", 5))

    cfg = pyconfix()
    cfg.add_options(ConfigOption("HOST_ON", False))
    cfg.include(other)
    assert cfg.CHILD is None


def test_group_dependency_cascade_is_not_reapplied_on_second_load(tmp_path, monkeypatch):
    # Each load_schem re-ran the cascade over every option, wrapping already
    # combined predicates again. A child's predicate must not grow per load.
    (tmp_path / "a.json").write_text(json.dumps({"A": {"ONE": 1}}))
    (tmp_path / "b.json").write_text(json.dumps({"B": {"TWO": 2}}))
    monkeypatch.chdir(tmp_path)
    calls = []
    cfg = pyconfix()
    group = cfg.group_option("G", dependencies=lambda x: calls.append(1) or True)
    group.add_options(ConfigOption("K", 1))
    cfg.load_schem(["a.json"])
    cfg.load_schem(["b.json"])
    calls.clear()
    assert cfg.K == 1
    assert len(calls) == 1


# --------------------------------------------------------------------------- #
# 4. Applied values must be validated against the option type, and the CLI's
#    -o parser must accept negative integers.
# --------------------------------------------------------------------------- #

TYPED_SCHEMA = {"T": {"FLAG": False, "COUNT": 3, "NAME": "x"}}


@pytest.fixture
def typed(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, TYPED_SCHEMA)
    return lambda: pyconfix().load_schem([name])


@pytest.mark.parametrize("key,value", [
    ("FLAG", "yes"),
    ("FLAG", 1),
    ("COUNT", "abc"),
    ("COUNT", True),
    ("NAME", 5),
])
def test_apply_config_rejects_wrong_type(typed, key, value):
    with pytest.raises(ValueError, match=key):
        typed().apply_config(overlay={key: value})


@pytest.mark.parametrize("key,value", [
    ("FLAG", True),
    ("COUNT", -4),
    ("NAME", "y"),
])
def test_apply_config_accepts_right_type(typed, key, value):
    assert getattr(typed().apply_config(overlay={key: value}), key) == value


def test_apply_config_rejected_value_leaves_option_unchanged(typed):
    cfg = typed()
    with pytest.raises(ValueError):
        cfg.apply_config(overlay={"FLAG": "yes"})
    assert cfg.FLAG is False


def test_cli_option_parses_negative_int(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["pyconfix", "-o", "COUNT=-5"])
    assert cli.parse_args().option == {"COUNT": -5}


# --------------------------------------------------------------------------- #
# 5. An option whose type is a registered alias must keep the schema's `data`
#    (clone_with only forwarded default/description/dependencies).
# --------------------------------------------------------------------------- #

def test_alias_typed_option_keeps_schema_data(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "TRI": {"type": "tri-state", "data": ["WIN32"]}}})
    cfg = pyconfix()
    cfg.register_alias("tri-state", ConfigOptionType.ENUM, ["ON", "MODULE", "OFF"])
    cfg.load_schem([name])
    assert cfg._get("TRI").data == ["WIN32"]


# --------------------------------------------------------------------------- #
# 6. include() of a schema-loaded config: its compiled string dependencies must
#    resolve names against the *destination* config, not the source.
# --------------------------------------------------------------------------- #

def test_included_schema_dependency_resolves_in_destination(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "FEATURE": {"default": 7, "deps": "HOST_ON"}}})
    other = pyconfix().load_schem([name])

    cfg = pyconfix()
    cfg.add_options(ConfigOption("HOST_ON", True))
    cfg.include(other)
    assert cfg.FEATURE == 7


# --------------------------------------------------------------------------- #
# 7. Expression parser: unary minus is supported; an unterminated quoted
#    string is an error instead of being silently accepted.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("expr,values,expected", [
    ("-3 + 5 == 2", {}, True),
    ("A > -1", {"A": 0}, True),
    ("-A == -2", {"A": 2}, True),
    ("2 * -3 == -6", {}, True),
    ("-(1 + 2) == -3", {}, True),
    ("1 - -1 == 2", {}, True),
])
def test_parser_unary_minus(expr, values, expected):
    assert ev(expr, **values) is expected


def test_parser_binary_minus_still_works():
    assert ev("5 - 3 == 2") is True


@pytest.mark.parametrize("expr", ["A == 'abc", "'", "A == 'x' && B == 'y"])
def test_tokenize_unterminated_quote_raises(expr):
    with pytest.raises(ValueError):
        tokenize(expr)


# --------------------------------------------------------------------------- #
# 8. Through the Python API a string dependency is rejected when the option is
#    added, not later when it is first evaluated (see also
#    test_core.test_python_api_string_dependency_is_rejected).
# --------------------------------------------------------------------------- #

def test_add_options_rejects_string_dependency():
    core = Core()
    with pytest.raises(ValueError):
        core.add_options(ConfigOption("N", 1, dependencies="F"))


def test_add_options_rejects_string_dependency_in_group_child():
    core = Core()
    child = ConfigOption("N", 1, dependencies="F")
    with pytest.raises(ValueError):
        core.add_options(ConfigOption(
            "G", option_type=ConfigOptionType.GROUP, options=[child]))
    assert core._get("G") is None


def test_action_option_rejects_string_dependency():
    cfg = pyconfix()
    with pytest.raises(ValueError):
        @cfg.action_option(dependencies="F")
        def act(x):
            return 1


def test_schema_string_dependencies_still_allowed(chain):
    # The JSON schema compiles its strings before adding, so it is unaffected.
    assert chain(MASTER=True).A is True
