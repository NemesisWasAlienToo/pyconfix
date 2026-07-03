"""Unit tests for the Core manager (pyconfix.core) in isolation.

Core is the heart of the library, so it gets the most direct coverage here:
aliases, applying selections, availability, value sync, flatten, dump/diff,
attribute/get access, and action execution — all built by hand (no files, no
runner, no curses) so failures point straight at core.
"""

import pytest

from pyconfix import Core, ConfigOption, ConfigOptionType


def opt(name, type_, **kw):
    return ConfigOption(name=name, option_type=type_, **kw)


def action(c, name=None, dependencies=None, requires=None):
    """Register an ACTION option directly on a Core.

    The ``action_option`` decorator sugar now lives on the runner; Core still
    owns action *execution*, which is what these tests exercise, so they build
    the option and register it via ``add_options`` here.
    """
    def decorator(func):
        c.add_options(ConfigOption(
            name=name or func.__name__,
            option_type=ConfigOptionType.ACTION,
            default=func,
            dependencies=dependencies,
            requires=requires,
            description=func.__doc__ or "",
        ))
        return func
    return decorator


@pytest.fixture
def core():
    """A hand-built Core covering the option kinds and a callable dependency."""
    c = Core()
    c.add_options(
        opt("FLAG", ConfigOptionType.BOOL, default=True),
        opt("N", ConfigOptionType.INT, default=5, dependencies=lambda cfg: cfg.FLAG),
        opt("MODE", ConfigOptionType.ENUM, default="B", choices=["A", "B", "C"]),
        opt("EXT", ConfigOptionType.EXTERNAL, default="os"),
        opt("G", ConfigOptionType.GROUP, expanded=True, options=[
            opt("SUB", ConfigOptionType.BOOL, default=False),
        ]),
    )
    return c


# --------------------------------------------------------------------------- #
# Aliases
# --------------------------------------------------------------------------- #

def test_register_alias_and_duplicate_guard():
    c = Core()
    c.register_alias("tri", ConfigOptionType.ENUM, ["A", "B"])
    with pytest.raises(ValueError):
        c.register_alias("tri", ConfigOptionType.ENUM, ["A", "B"])


def test_option_from_alias_builds_option():
    c = Core()
    c.register_alias("tri", ConfigOptionType.ENUM, ["A", "B"])
    o = c.option_from_alias("tri", name="X")
    assert o.name == "X" and o.option_type == ConfigOptionType.ENUM


def test_option_from_alias_requires_name():
    c = Core()
    c.register_alias("tri", ConfigOptionType.ENUM, ["A", "B"])
    with pytest.raises(ValueError):
        c.option_from_alias("tri")


def test_option_from_alias_unknown_raises():
    c = Core()
    with pytest.raises(ValueError):
        c.option_from_alias("nope", name="X")


def test_add_options_returns_and_appends():
    c = Core()
    o = opt("A", ConfigOptionType.BOOL, default=True)
    ret = c.add_options(o)
    assert ret == (o,)
    assert c.options == [o]


# --------------------------------------------------------------------------- #
# _get lookup
# --------------------------------------------------------------------------- #

def test_get_is_case_insensitive(core):
    assert core._get("flag").name == "FLAG"


def test_get_finds_group_and_nested_child(core):
    assert core._get("G").option_type == ConfigOptionType.GROUP
    assert core._get("SUB").name == "SUB"


def test_get_unknown_returns_none(core):
    assert core._get("NOPE") is None


# --------------------------------------------------------------------------- #
# Availability
# --------------------------------------------------------------------------- #

def test_available_when_no_dependency(core):
    assert core._is_option_available(core._get("MODE")) is True


def test_available_follows_callable_dependency(core):
    assert core._is_option_available(core._get("N")) is True
    core._get("FLAG").value = False
    assert core._is_option_available(core._get("N")) is False


def test_non_callable_dependency_raises(core):
    bad = core._get("MODE")
    bad.dependencies = "not-callable"
    with pytest.raises(ValueError):
        core._is_option_available(bad)


# --------------------------------------------------------------------------- #
# Value sync
# --------------------------------------------------------------------------- #

def test_sync_blanks_disabled_and_restores_enabled(core):
    n = core._get("N")
    core._sync_option_value(n, available=False)
    assert n.value is None
    core._sync_option_value(n, available=True)
    assert n.value == 5   # restored from default


def test_sync_restores_enum_to_default_index(core):
    m = core._get("MODE")
    core._sync_option_value(m, available=False)
    assert m.value is None
    core._sync_option_value(m, available=True)
    assert m.value == 1   # index of default "B"


# --------------------------------------------------------------------------- #
# apply_config
# --------------------------------------------------------------------------- #

def test_apply_sets_values_and_defaults(core):
    core.apply_config({"N": 42})
    assert core.N == 42
    assert core.MODE == "B"          # untouched -> default


def test_apply_enum_by_choice_string(core):
    core.apply_config({"MODE": "C"})
    assert core.MODE == "C"
    assert core._get("MODE").value == 2


def test_apply_overlay_takes_precedence(core):
    core.apply_config({"N": 1}, overlay={"N": 99})
    assert core.N == 99


# --------------------------------------------------------------------------- #
# Flatten
# --------------------------------------------------------------------------- #

def test_flatten_includes_expanded_group_children_with_depth(core):
    core.apply_config({})
    flat = core._flatten_options(core.options)
    names = {o.name: d for o, d in flat}
    assert names["G"] == 0
    assert names["SUB"] == 1


def test_flatten_hides_disabled_unless_show_disabled(core):
    core._get("FLAG").value = False      # disables N (depends on FLAG)
    hidden = [o.name for o, _ in core._flatten_options(core.options)]
    assert "N" not in hidden
    core.show_disabled = True
    shown = [o.name for o, _ in core._flatten_options(core.options)]
    assert "N" in shown


# --------------------------------------------------------------------------- #
# dump / diff
# --------------------------------------------------------------------------- #

def test_dump_shapes(core):
    core.apply_config({})
    d = core.dump()
    assert d["FLAG"] is True
    assert d["MODE"] == "B"           # enum -> choice string
    assert d["SUB"] is False          # group child flattened to top level
    assert "G" not in d               # the group itself is not emitted


def test_dump_disabled_is_none(core):
    core.apply_config({})
    core._get("FLAG").value = False
    assert core.dump()["N"] is None


def test_diff_reports_only_changed_and_available(core):
    core.apply_config({"N": 7})
    assert core.diff() == {"N": 7}


# --------------------------------------------------------------------------- #
# Attribute / get access
# --------------------------------------------------------------------------- #

def test_attribute_enum_returns_choice_string(core):
    core.apply_config({})
    assert core.MODE == "B"


def test_attribute_group_returns_children_list(core):
    assert core.G == core._get("G").options


def test_attribute_unknown_raises(core):
    with pytest.raises(AttributeError):
        _ = core.NOPE


def test_get_missing_returns_default(core):
    assert core.get("NOPE", "fallback") == "fallback"


# --------------------------------------------------------------------------- #
# Actions
# --------------------------------------------------------------------------- #

def test_action_returns_value_and_trace():
    c = Core()

    @action(c)
    def build(x):
        return 42

    assert c.build() == (42, ["build"])


def test_action_result_is_cached_within_one_execution():
    c = Core()
    calls = []

    @action(c)
    def leaf(x):
        calls.append(1)
        return 7

    @action(c)
    def parent(x):
        return x.leaf() + x.leaf()

    value, trace = c.parent()
    assert value == 14
    assert calls == [1]                 # leaf body ran once; second call cached
    assert trace.count("leaf") == 2     # both references recorded in the trace


def test_action_requires_gate_blocks_body():
    c = Core()
    calls = []

    @action(c, requires=lambda x: False)
    def gated(x):
        calls.append(1)
        return 1

    value, _ = c.gated()
    assert value is None
    assert calls == []                  # body never ran


def test_action_self_cycle_detected():
    c = Core()

    @action(c)
    def loop(x):
        return x.loop()

    with pytest.raises(AttributeError):
        c.loop()


# --------------------------------------------------------------------------- #
# Actions: unknown tokens referenced inside a running action
# --------------------------------------------------------------------------- #

def test_action_body_unknown_token_raises_clean_attributeerror():
    c = Core()

    @action(c)
    def act(x):
        return x.NO_SUCH_OPTION

    with pytest.raises(AttributeError) as ei:
        c.act()
    msg = str(ei.value)
    assert "NoneType" not in msg          # not the masked None deref
    assert "NO_SUCH_OPTION" in msg        # names the offending key


def test_action_requires_unknown_token_raises_clean_attributeerror():
    c = Core()

    @action(c, requires=lambda x: x.NO_SUCH_OPTION)
    def act(x):
        return 1

    with pytest.raises(AttributeError) as ei:
        c.act()
    assert "NoneType" not in str(ei.value)


# --------------------------------------------------------------------------- #
# String dependency expressions supplied through the Python API
# --------------------------------------------------------------------------- #

def test_add_options_string_dependency_is_evaluated():
    c = Core()
    c.add_options(
        opt("F", ConfigOptionType.BOOL, default=True),
        opt("N", ConfigOptionType.INT, default=1, dependencies="F"),
    )
    c.apply_config({})
    assert c._is_option_available(c._get("N")) is True
    c._get("F").value = False
    assert c._is_option_available(c._get("N")) is False


def test_add_options_expression_dependency_is_evaluated():
    c = Core()
    c.add_options(
        opt("LEVEL", ConfigOptionType.INT, default=5),
        opt("HIGH", ConfigOptionType.BOOL, default=True, dependencies="LEVEL >= 3"),
    )
    c.apply_config({})
    assert c._is_option_available(c._get("HIGH")) is True
    c._get("LEVEL").value = 1
    assert c._is_option_available(c._get("HIGH")) is False


def test_action_option_string_dependency_disables_action():
    c = Core()
    c.add_options(opt("F", ConfigOptionType.BOOL, default=False))

    @action(c, dependencies="F")
    def gated(x):
        return 1

    c.apply_config({})
    # F is False -> the action is unavailable; attribute access yields the
    # disabled action shape (None, []) rather than crashing.
    assert c.gated() == (None, [])
    c._get("F").value = True
    assert c.gated() == (1, ["gated"])
