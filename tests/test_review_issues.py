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
from pyconfix.schema import parse_options


def write_schema(tmp_path, monkeypatch, schema, name="schema.json"):
    (tmp_path / name).write_text(json.dumps(schema))
    monkeypatch.chdir(tmp_path)
    return name


def ev(expr, **values):
    return BooleanExpressionParser().evaluate_postfix(
        shunting_yard(tokenize(expr)), getter=lambda k: values[k])


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
    return lambda **overlay: pyconfix().load_schema([name]).apply_config(overlay=overlay)


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


# Checking availability through dependencies is recursive, so a cycle must be
# reported as a ValueError naming the cycle, not a bare RecursionError.

@pytest.mark.parametrize("schema,cycle", [
    ({"A": {"default": True, "deps": "B"},
      "B": {"default": True, "deps": "A"}}, "A -> B -> A"),
    ({"A": {"default": True, "deps": "B"},
      "B": {"default": True, "deps": "C"},
      "C": {"default": True, "deps": "A"}}, "A -> B -> C -> A"),
])
def test_schema_dependency_cycle_raises_named_value_error(tmp_path, monkeypatch, schema, cycle):
    name = write_schema(tmp_path, monkeypatch, {"S": schema})
    cfg = pyconfix().load_schema([name])
    with pytest.raises(ValueError, match=cycle):
        cfg.A


def test_python_dependency_cycle_raises_named_value_error():
    cfg = pyconfix()
    cfg.add_options(
        ConfigOption("A", True, dependencies=lambda x: x.B),
        ConfigOption("B", True, dependencies=lambda x: x.A),
    )
    with pytest.raises(ValueError, match="A -> B -> A"):
        cfg.A


def test_dump_reports_dependency_cycle(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "A": {"default": True, "deps": "B"},
        "B": {"default": True, "deps": "A"}}})
    with pytest.raises(ValueError, match="cycle"):
        pyconfix().load_schema([name]).dump()


def test_failed_cycle_check_does_not_poison_later_lookups(tmp_path, monkeypatch):
    # The in-progress tracking must be cleaned up after an error, so unrelated
    # options still evaluate normally afterwards.
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "A": {"default": True, "deps": "B"},
        "B": {"default": True, "deps": "A"},
        "ON": True,
        "D": {"default": 4, "deps": "ON"}}})
    cfg = pyconfix().load_schema([name])
    with pytest.raises(ValueError):
        cfg.A
    assert cfg.D == 4


# Availability is memoized per top-level lookup: an option reached by several
# routes is evaluated once, so stacked diamonds stay linear, not exponential.

def counted(calls, name, predicate):
    def dependency(x):
        calls[name] = calls.get(name, 0) + 1
        return predicate(x)
    return dependency


def stacked_diamonds(layers, calls):
    options = [ConfigOption("L0", True)]
    for i in range(1, layers):
        prev = f"L{i - 1}"
        options += [
            ConfigOption(f"X{i}", True, dependencies=counted(
                calls, f"X{i}", lambda x, p=prev: getattr(x, p))),
            ConfigOption(f"Y{i}", True, dependencies=counted(
                calls, f"Y{i}", lambda x, p=prev: getattr(x, p))),
            ConfigOption(f"L{i}", True, dependencies=counted(
                calls, f"L{i}", lambda x, a=f"X{i}", b=f"Y{i}": getattr(x, a) and getattr(x, b))),
        ]
    cfg = pyconfix()
    cfg.add_options(*options)
    return cfg


def test_stacked_diamonds_evaluate_each_option_once():
    calls = {}
    cfg = stacked_diamonds(25, calls)
    assert cfg.L24 is True
    assert set(calls.values()) == {1}


def test_cached_false_availability_is_reused():
    calls = {}
    cfg = pyconfix()
    cfg.add_options(
        ConfigOption("OFF", True, dependencies=counted(calls, "OFF", lambda x: False)),
        ConfigOption("TOP", True, dependencies=lambda x: x.OFF or x.OFF),
    )
    assert cfg.TOP is None
    assert calls == {"OFF": 1}


def test_availability_cache_does_not_collide_with_action_value():
    cfg = pyconfix()

    @cfg.action_option(dependencies=lambda x: True)
    def build(x):
        return 7

    cfg.add_options(ConfigOption("USES", True, dependencies=lambda x: x.build() == 7))
    assert cfg.USES is True


def test_availability_cache_does_not_outlive_the_lookup():
    cfg = pyconfix()
    cfg.add_options(
        ConfigOption("M", False),
        ConfigOption("A", 1, dependencies=lambda x: x.M),
    )
    assert cfg.A is None
    cfg.apply_config(overlay={"M": True})
    assert cfg.A == 1


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


def group_of(*options, **kwargs):
    return ConfigOption("G", option_type=ConfigOptionType.GROUP, options=list(options), **kwargs)


def test_enabled_group_leaves_child_enabled():
    cfg = pyconfix()
    group = cfg.group_option("G", dependencies=lambda x: True)
    group.add_options(ConfigOption("CHILD", 5))
    assert cfg.CHILD == 5


def test_group_without_dependencies_leaves_child_enabled():
    cfg = pyconfix()
    group = cfg.group_option("G")
    group.add_options(ConfigOption("CHILD", 5, dependencies=lambda x: True))
    assert cfg.CHILD == 5


def test_child_needs_both_group_and_its_own_dependency():
    core = Core()
    core.add_options(group_of(ConfigOption("CHILD", 5, dependencies=lambda x: False),
                              dependencies=lambda x: True))
    assert core.CHILD is None


def test_nested_group_disables_every_level():
    core = Core()
    inner = ConfigOption("INNER", option_type=ConfigOptionType.GROUP,
                         options=[ConfigOption("LEAF", 1)])
    core.add_options(group_of(inner, dependencies=lambda x: False))
    assert core.INNER is None
    assert core.LEAF is None


def test_group_stays_a_group_for_its_children_when_enabled_again():
    flag = ConfigOption("FLAG", False)
    core = Core()
    core.add_options(flag, group_of(ConfigOption("CHILD", 5), dependencies=lambda x: x.FLAG))
    assert core.CHILD is None
    flag.value = True
    assert core.CHILD == 5


def test_group_predicate_runs_once_per_session():
    calls = []
    cfg = pyconfix()
    group = cfg.group_option("G", dependencies=lambda x: calls.append(1) or True)
    group.add_options(ConfigOption("A", 1), ConfigOption("B", 2))
    session = cfg.create_evaluation_session()
    for name in ("A", "B"):
        session._is_option_available(cfg.get_option(name))
    assert len(calls) == 1


def test_group_do_not_cache_reruns_predicate():
    calls = []
    cfg = pyconfix()
    core = cfg.core
    group = ConfigOption("G", option_type=ConfigOptionType.GROUP, options=[],
                         dependencies=lambda x: calls.append(1) or True, do_not_cache=True)
    core.add_options(group)
    core.add_options(ConfigOption("A", 1), ConfigOption("B", 2), parent=group)
    session = cfg.create_evaluation_session()
    for name in ("A", "B"):
        session._is_option_available(cfg.get_option(name))
    assert len(calls) == 2


def test_rejected_add_options_leaves_parent_unset():
    core = Core()
    group = group_of()
    core.add_options(ConfigOption("TAKEN", 1), group)
    option = ConfigOption("NEW", 1)
    with pytest.raises(ValueError):
        core.add_options(option, ConfigOption("TAKEN", 2), parent=group)
    assert option.parent is None


def test_include_under_a_group_applies_its_dependency():
    other = pyconfix()
    other.add_options(ConfigOption("CHILD", 5))
    cfg = pyconfix()
    group = cfg.group_option("G", dependencies=lambda x: False).get()
    cfg.include(other, parent=group)
    assert cfg.CHILD is None


@pytest.mark.parametrize("group_needs, expected", [
    (lambda x: False, (None, ["act"])),
    (lambda x: True, ("ran", ["act"])),
])
def test_group_needs_applies_to_its_actions(group_needs, expected):
    core = Core()
    group = group_of(needs=group_needs)
    core.add_options(group)
    core.add_options(ConfigOption("act", option_type=ConfigOptionType.ACTION,
                                  default=lambda x: "ran"), parent=group)
    assert core.act() == expected


def test_nested_group_needs_applies_to_its_actions():
    core = Core()
    inner = ConfigOption("INNER", option_type=ConfigOptionType.GROUP, options=[])
    core.add_options(group_of(inner, needs=lambda x: False))
    core.add_options(ConfigOption("act", option_type=ConfigOptionType.ACTION,
                                  default=lambda x: "ran"), parent=inner)
    assert core.act() == (None, ["act"])


def needs_chain(setup_passes=True, own_passes=True, do_not_cache=False):
    """A group whose needs runs a `setup` action, holding actions `act` and `both`."""
    order = []

    def step(name, result):
        return lambda x: order.append(name) or result

    core = Core()
    core.add_options(ConfigOption("setup", option_type=ConfigOptionType.ACTION,
                                  default=step("setup", setup_passes), do_not_cache=do_not_cache))
    group = ConfigOption("G", option_type=ConfigOptionType.GROUP, options=[],
                         needs=lambda x: x.setup(),
                         do_not_cache=do_not_cache)
    core.add_options(group)
    core.add_options(
        ConfigOption("act", option_type=ConfigOptionType.ACTION,
                     default=step("act", "ran"), needs=step("own needs", own_passes)),
        ConfigOption("both", option_type=ConfigOptionType.ACTION,
                     default=lambda x: (x.act(), x.other())),
        ConfigOption("other", option_type=ConfigOptionType.ACTION,
                     default=step("other", "ran")),
        parent=group)
    return core, order


def test_group_needs_runs_before_the_actions_own_needs():
    core, order = needs_chain()
    assert core.act() == ("ran", ["act", "setup"])
    assert order == ["setup", "own needs", "act"]


def test_failing_group_needs_stops_before_the_actions_own_needs():
    core, order = needs_chain(setup_passes=False)
    assert core.act() == (None, ["act", "setup"])
    assert order == ["setup"]


def test_failing_own_needs_stops_the_action_after_group_needs_passed():
    core, order = needs_chain(own_passes=False)
    assert core.act() == (None, ["act", "setup"])
    assert order == ["setup", "own needs"]


def test_group_needs_runs_once_for_all_actions_in_a_run():
    core, order = needs_chain()
    assert core.both()[0] == ("ran", "ran")
    assert order.count("setup") == 1


def test_group_needs_do_not_cache_reruns_for_each_action():
    core, order = needs_chain(do_not_cache=True)
    core.both()
    assert order.count("setup") == 3      # once each for `both`, `act` and `other`


def test_group_needs_runs_again_in_a_new_run():
    core, order = needs_chain()
    core.act()
    core.act()
    assert order.count("setup") == 2


def test_included_group_dependency_cascades(tmp_path, monkeypatch):
    other = pyconfix()
    group = other.group_option("G", dependencies=lambda x: x.HOST_ON)
    group.add_options(ConfigOption("CHILD", 5))

    cfg = pyconfix()
    cfg.add_options(ConfigOption("HOST_ON", False))
    cfg.include(other)
    assert cfg.CHILD is None


def test_group_dependency_cascade_is_not_reapplied_on_second_load(tmp_path, monkeypatch):
    # Each load_schema re-ran the cascade over every option, wrapping already
    # combined predicates again. A child's predicate must not grow per load.
    (tmp_path / "a.json").write_text(json.dumps({"A": {"ONE": 1}}))
    (tmp_path / "b.json").write_text(json.dumps({"B": {"TWO": 2}}))
    monkeypatch.chdir(tmp_path)
    calls = []
    cfg = pyconfix()
    group = cfg.group_option("G", dependencies=lambda x: calls.append(1) or True)
    group.add_options(ConfigOption("K", 1))
    cfg.load_schema(["a.json"])
    cfg.load_schema(["b.json"])
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
    return lambda: pyconfix().load_schema([name])


@pytest.mark.parametrize("key,value", [
    ("FLAG", "yes"),
    ("FLAG", 1),
    ("COUNT", "abc"),
    ("NAME", 5),
])
def test_apply_config_rejects_wrong_type(typed, key, value):
    with pytest.raises(ValueError, match=key):
        typed().apply_config(overlay={key: value})


@pytest.mark.parametrize("key,value", [
    ("FLAG", True),
    ("COUNT", -4),
    ("COUNT", True),
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

@pytest.mark.parametrize("name", list(ConfigOptionType))
def test_alias_cannot_use_builtin_type_name(name):
    core = Core()
    with pytest.raises(ValueError, match=str(name)):
        core.register_alias(str(name), ConfigOptionType.ENUM, ["ON", "OFF"])
    assert core.aliases == {}


def test_alias_with_other_name_is_registered():
    core = Core()
    core.register_alias("tri-state", ConfigOptionType.ENUM, ["ON", "OFF"])
    option = parse_options(core, {"N": {"type": "tri-state", "default": "ON"}})[0]
    assert option.option_type == ConfigOptionType.ENUM


def test_alias_typed_option_keeps_schema_data(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "TRI": {"type": "tri-state", "data": ["WIN32"]}}})
    cfg = pyconfix()
    cfg.register_alias("tri-state", ConfigOptionType.ENUM, ["ON", "MODULE", "OFF"])
    cfg.load_schema([name])
    assert cfg.get_option("TRI").data == ["WIN32"]


# --------------------------------------------------------------------------- #
# 6. include() of a schema-loaded config: its compiled string dependencies must
#    resolve names against the *destination* config, not the source.
# --------------------------------------------------------------------------- #

def test_included_schema_dependency_resolves_in_destination(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "FEATURE": {"default": 7, "deps": "HOST_ON"}}})
    other = pyconfix().load_schema([name])

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
# 8. A string dependency works the same through the Python API and the schema.
#    It compiles when the option is created and names resolve when it is
#    evaluated, so options can be added in any order.
# --------------------------------------------------------------------------- #

def test_string_dependency_may_name_an_option_added_later():
    core = Core()
    core.add_options(ConfigOption("N", 1, dependencies="F"))
    core.add_options(ConfigOption("F", False))
    assert core.N is None
    core.get_option("F").value = True
    assert core.N == 1


def test_string_dependency_with_unknown_name_fails_when_read():
    core = Core()
    core.add_options(ConfigOption("N", 1, dependencies="F"))
    with pytest.raises(AttributeError, match="Invalid key: 'F'"):
        core.N


def test_string_dependency_with_bad_syntax_fails_on_creation():
    with pytest.raises(ValueError):
        ConfigOption("N", 1, dependencies="(F")


def test_dependency_of_the_wrong_type_is_rejected():
    with pytest.raises(ValueError, match="N"):
        ConfigOption("N", 1, dependencies=5)


def test_string_dependency_in_group_child():
    core = Core()
    core.add_options(
        ConfigOption("F", False),
        ConfigOption("G", option_type=ConfigOptionType.GROUP, options=[
            ConfigOption("N", 1, dependencies="F")]))
    assert core.N is None


def test_string_dependency_on_action_option():
    cfg = pyconfix()
    cfg.add_options(ConfigOption("F", False))

    @cfg.action_option(dependencies="F")
    def act(x):
        return 1

    assert cfg.act() == (None, [])


def test_enum_choice_attribute_is_case_sensitive():
    core = Core()
    core.add_options(ConfigOption("MODE", "DEBUG", choices=["DEBUG", "INFO"]))
    assert core.DEBUG == "DEBUG"
    with pytest.raises(AttributeError, match="Invalid key: 'debug'"):
        core.debug


def test_enum_choice_token_in_dependency_is_case_sensitive():
    core = Core()
    core.add_options(
        ConfigOption("MODE", "DEBUG", choices=["DEBUG", "INFO"]),
        ConfigOption("N", 1, dependencies="MODE == debug"))
    with pytest.raises(AttributeError, match="Invalid key: 'debug'"):
        core.N


def test_string_dependency_with_enum_choice_token():
    core = Core()
    core.add_options(
        ConfigOption("MODE", "DEBUG", choices=["DEBUG", "INFO"]),
        ConfigOption("N", 1, dependencies="MODE == DEBUG"))
    assert core.N == 1


def test_schema_string_dependencies_still_allowed(chain):
    assert chain(MASTER=True).A is True


# --------------------------------------------------------------------------- #
# do_not_cache: an option opts out of the per-session cache, so its availability
# and action result are recomputed every time. Actions and dependencies share
# one session class, which owns the caching and checks this flag.
# --------------------------------------------------------------------------- #

def test_do_not_cache_defaults_to_false():
    assert ConfigOption("A", True).do_not_cache is False


def test_do_not_cache_survives_clone_and_to_dict():
    option = ConfigOption("A", True, do_not_cache=True)
    assert option.clone_with(name="B").do_not_cache is True
    assert option.to_dict()["do_not_cache"] is True


def test_do_not_cache_from_schema(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "ON": {"default": True, "do_not_cache": True},
        "OFF": True,
    }})
    cfg = pyconfix().load_schema([name])
    assert cfg.get_option("ON").do_not_cache is True
    assert cfg.get_option("OFF").do_not_cache is False


def test_do_not_cache_is_reserved_in_schema(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {"do_not_cache": True}})
    with pytest.raises(ValueError, match="reserved"):
        pyconfix().load_schema([name])


def test_do_not_cache_on_alias_typed_option(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "TRI": {"type": "tri-state", "do_not_cache": True}}})
    cfg = pyconfix()
    cfg.register_alias("tri-state", ConfigOptionType.ENUM, ["ON", "OFF"])
    cfg.load_schema([name])
    assert cfg.get_option("TRI").do_not_cache is True


@pytest.mark.parametrize("do_not_cache,expected", [(False, 1), (True, 2)])
def test_availability_respects_do_not_cache(do_not_cache, expected):
    calls = {}
    cfg = pyconfix()
    cfg.add_options(
        ConfigOption("SHARED", True, do_not_cache=do_not_cache,
                     dependencies=counted(calls, "SHARED", lambda x: True)),
        ConfigOption("TOP", True, dependencies=lambda x: x.SHARED and x.SHARED),
    )
    assert cfg.TOP is True
    assert calls == {"SHARED": expected}


@pytest.mark.parametrize("do_not_cache,expected", [(False, 1), (True, 2)])
def test_action_result_respects_do_not_cache(do_not_cache, expected):
    runs = []
    cfg = pyconfix()

    @cfg.action_option(do_not_cache=do_not_cache)
    def leaf(x):
        runs.append(1)
        return len(runs)

    @cfg.action_option()
    def parent(x):
        x.leaf()
        return x.leaf()

    value, trace = cfg.parent()
    assert value == expected
    assert len(runs) == expected
    assert trace.count("leaf") == 2


def test_group_action_option_accepts_do_not_cache():
    cfg = pyconfix()
    group = cfg.group_option("G")

    @group.action_option(do_not_cache=True)
    def act(x):
        return 1

    assert cfg.get_option("act").do_not_cache is True


def test_do_not_cache_still_detects_cycles():
    cfg = pyconfix()
    cfg.add_options(
        ConfigOption("A", True, do_not_cache=True, dependencies=lambda x: x.B),
        ConfigOption("B", True, do_not_cache=True, dependencies=lambda x: x.A),
    )
    with pytest.raises(ValueError, match="A -> B -> A"):
        cfg.A


def test_action_cycle_not_through_the_starting_action():
    cfg = pyconfix()

    @cfg.action_option()
    def a(x):
        return x.b()

    @cfg.action_option()
    def b(x):
        return x.c()

    @cfg.action_option()
    def c(x):
        return x.b()

    with pytest.raises(ValueError, match="b -> c -> b"):
        cfg.a()


def test_dependency_reading_a_running_action_is_not_a_cycle():
    # Running an action and checking its availability are separate evaluations.
    cfg = pyconfix()

    @cfg.action_option()
    def outer(x):
        return x.watcher()

    @cfg.action_option(dependencies=lambda x: bool(x.outer))
    def watcher(x):
        return 5

    assert cfg.outer()[0] == 5


# --------------------------------------------------------------------------- #
# 9. A disabled option evaluates to None. Comparing it or doing arithmetic on it
#    must give None (false), not a TypeError that crashes the TUI. Logical
#    operators, == and != already work on None and keep their meaning.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("op", [">", "<", ">=", "<=", "+", "-", "*", "/", "**", "%", "&", "|", "^", ">>", "<<"])
def test_binary_operator_with_none_operand_is_none(op):
    assert ev(f"X {op} 2", X=None) is None
    assert ev(f"2 {op} X", X=None) is None


def test_unary_minus_of_none_is_none():
    assert ev("-X", X=None) is None


@pytest.mark.parametrize("expr, expected", [
    ("X == 2", False),
    ("X != 2", True),
    ("X && 1", False),
    ("X || 1", True),
    ("!X", True),
    ("X ** 2 < 10", None),
    ("(X > 2) || 1", True),
])
def test_none_keeps_logical_and_equality_meaning(expr, expected):
    assert ev(expr, X=None) == expected


def test_option_depending_on_math_over_disabled_option_is_disabled(tmp_path, monkeypatch):
    name = write_schema(tmp_path, monkeypatch, {"S": {
        "MASTER": False,
        "COUNT": {"default": 10, "deps": "MASTER"},
        "SMALL": {"default": True, "deps": "COUNT ** 2 < 10"},
    }})
    cfg = pyconfix().load_schema([name])
    assert cfg.SMALL is None
    assert cfg.dump()["SMALL"] is None
