"""Unit tests for the Core manager (pyconfix.core) in isolation.

Core is the heart of the library, so it gets the most direct coverage here:
aliases, applying selections, availability, value sync, dump/diff,
attribute/get access, and action execution — all built by hand (no files, no
runner, no curses) so failures point straight at core. (Flattening for display
lives on the TUI now and is covered in test_tui_smoke.)
"""

import pytest

from pyconfix import Core, ConfigOption, ConfigOptionType


def opt(name, type_, **kw):
    return ConfigOption(name=name, option_type=type_, **kw)


def action(c, name=None, dependencies=None, needs=None):
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
            needs=needs,
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


def test_register_alias_non_enum_raises():
    c = Core()
    with pytest.raises(ValueError):
        c.register_alias("weird", ConfigOptionType.BOOL, ["A", "B"])


def test_register_alias_skip_duplicate_returns_existing():
    c = Core()
    o = ConfigOption(name="tri", option_type=ConfigOptionType.ENUM, choices=["A", "B"])
    first = c._register_alias(o)
    again = c._register_alias(o, skip_duplicate_check=True)
    assert again is first


def test_option_from_alias_builtin_type_name():
    # An unregistered name that is a built-in ConfigOptionType is accepted.
    c = Core()
    o = c.option_from_alias("bool", name="X", default=True)
    assert o.name == "X"
    assert o.option_type == ConfigOptionType.BOOL


def test_add_options_returns_and_appends():
    c = Core()
    o = opt("A", ConfigOptionType.BOOL, default=True)
    ret = c.add_options(o)
    assert ret == (o,)
    assert c.options == [o]


def test_add_options_raises_on_duplicate_within_call():
    c = Core()
    with pytest.raises(ValueError):
        c.add_options(
            opt("X", ConfigOptionType.BOOL, default=True),
            opt("X", ConfigOptionType.BOOL, default=False),
        )


def test_add_options_raises_on_duplicate_across_calls():
    c = Core()
    c.add_options(opt("X", ConfigOptionType.BOOL, default=True))
    with pytest.raises(ValueError):
        c.add_options(opt("X", ConfigOptionType.INT, default=1))


def test_add_options_duplicate_check_is_case_insensitive():
    c = Core()
    c.add_options(opt("Flag", ConfigOptionType.BOOL, default=True))
    with pytest.raises(ValueError):
        c.add_options(opt("FLAG", ConfigOptionType.BOOL, default=False))


def test_add_options_rejects_name_colliding_with_nested_child():
    c = Core()
    c.add_options(opt("G", ConfigOptionType.GROUP, options=[
        opt("SUB", ConfigOptionType.BOOL, default=True),
    ]))
    with pytest.raises(ValueError):
        c.add_options(opt("SUB", ConfigOptionType.INT, default=1))


def test_add_options_rejected_call_leaves_state_unchanged():
    c = Core()
    c.add_options(opt("A", ConfigOptionType.BOOL, default=True))
    with pytest.raises(ValueError):
        # second option duplicates "A" -> whole call is rejected
        c.add_options(opt("B", ConfigOptionType.BOOL, default=True),
                      opt("A", ConfigOptionType.BOOL, default=False))
    assert [o.name for o in c.options] == ["A"]   # "B" was not added
    assert c._get("B") is None


def test_add_options_rejected_call_name_is_reusable():
    # A name from a rejected call must not linger in the index; validate-then-
    # commit means "NEW" was never registered, so it can still be added later.
    c = Core()
    c.add_options(opt("A", ConfigOptionType.BOOL, default=True))
    with pytest.raises(ValueError):
        c.add_options(opt("NEW", ConfigOptionType.BOOL, default=True),
                      opt("A", ConfigOptionType.BOOL, default=False))
    c.add_options(opt("NEW", ConfigOptionType.BOOL, default=True))
    assert c._get("NEW").name == "NEW"


def test_add_options_with_parent_adds_child():
    c = Core()
    g = opt("G", ConfigOptionType.GROUP, options=[])
    c.add_options(g)
    child = opt("CHILD", ConfigOptionType.BOOL, default=True)
    c.add_options(child, parent=g)
    assert child in g.options          # nested under the group
    assert child not in c.options      # not added at the top level
    assert c._get("CHILD") is child    # indexed for O(1) lookup


def test_add_options_with_parent_rejects_duplicate():
    c = Core()
    g = opt("G", ConfigOptionType.GROUP, options=[])
    c.add_options(g)
    c.add_options(opt("CHILD", ConfigOptionType.BOOL, default=True), parent=g)
    # same name, whether re-added into the group or at the top level
    with pytest.raises(ValueError):
        c.add_options(opt("CHILD", ConfigOptionType.INT, default=1), parent=g)
    with pytest.raises(ValueError):
        c.add_options(opt("CHILD", ConfigOptionType.INT, default=1))


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


def test_apply_invalid_enum_value_raises_named_error(core):
    # A stale/hand-edited config with a choice that no longer exists is a real
    # error: raise a clear, named message rather than a bare "not in list".
    with pytest.raises(ValueError) as ei:
        core.apply_config({"MODE": "NO_LONGER_A_CHOICE"})
    msg = str(ei.value)
    assert "MODE" in msg
    assert "NO_LONGER_A_CHOICE" in msg


def test_apply_blank_enum_value_restores_default(core):
    # An empty value is treated as "unset" and restores the default.
    core.apply_config({"MODE": ""})
    assert core.MODE == "B"                      # the default
    assert core._get("MODE").value == 1


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


def test_action_needs_gate_blocks_body():
    c = Core()
    calls = []

    @action(c, needs=lambda x: False)
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


def test_action_body_reads_other_option_types():
    # An action body reaches other options through the execution session, which
    # resolves enum -> choice string, group -> children list, and plain values.
    c = Core()
    c.add_options(
        opt("MODE", ConfigOptionType.ENUM, default="B", choices=["A", "B", "C"]),
        opt("FLAG", ConfigOptionType.BOOL, default=True),
        opt("G", ConfigOptionType.GROUP, options=[
            opt("SUB", ConfigOptionType.BOOL, default=False),
        ]),
    )

    @action(c)
    def probe(x):
        return (x.MODE, x.FLAG, x.G)

    c.apply_config({})
    (mode, flag, group), _ = c.probe()
    assert mode == "B"                              # enum -> choice string
    assert flag is True                             # plain value
    assert [o.name for o in group] == ["SUB"]       # group -> children list


def test_action_body_reads_unavailable_option_and_action():
    # Inside a running action, an unavailable non-action reads as None and an
    # unavailable action reads as a no-op callable returning None.
    c = Core()
    c.add_options(
        opt("FLAG", ConfigOptionType.BOOL, default=False),
        opt("N", ConfigOptionType.INT, default=5, dependencies=lambda cfg: cfg.FLAG),
    )

    @action(c, dependencies=lambda x: x.FLAG)
    def gated(x):
        return 99

    @action(c)
    def probe(x):
        return (x.N, x.gated)

    c.apply_config({})
    (n_val, gated_ref), _ = c.probe()
    assert n_val is None                # unavailable non-action -> None
    assert callable(gated_ref)
    assert gated_ref() is None          # unavailable action -> lambda: None


def test_action_needs_unknown_token_raises_clean_attributeerror():
    c = Core()

    @action(c, needs=lambda x: x.NO_SUCH_OPTION)
    def act(x):
        return 1

    with pytest.raises(AttributeError) as ei:
        c.act()
    assert "NoneType" not in str(ei.value)


# --------------------------------------------------------------------------- #
# Dependencies via the Python API use callables; string expressions are reserved
# for the JSON schema only.
# --------------------------------------------------------------------------- #

def test_add_options_callable_dependency_is_evaluated():
    c = Core()
    c.add_options(
        opt("F", ConfigOptionType.BOOL, default=True),
        opt("N", ConfigOptionType.INT, default=1, dependencies=lambda cfg: cfg.F),
    )
    c.apply_config({})
    assert c._is_option_available(c._get("N")) is True
    c._get("F").value = False
    assert c._is_option_available(c._get("N")) is False


def test_action_option_callable_dependency_disables_action():
    c = Core()
    c.add_options(opt("F", ConfigOptionType.BOOL, default=False))

    @action(c, dependencies=lambda x: x.F)
    def gated(x):
        return 1

    c.apply_config({})
    # F is False -> the action is unavailable; attribute access yields the
    # disabled action shape (None, []) rather than crashing.
    assert c.gated() == (None, [])
    c._get("F").value = True
    assert c.gated() == (1, ["gated"])


def test_python_api_string_dependency_is_rejected():
    # String dependency expressions are for the JSON schema; through the Python
    # API a callable must be used, so a raw string is rejected when evaluated.
    c = Core()
    c.add_options(opt("N", ConfigOptionType.INT, default=1, dependencies="F"))
    with pytest.raises(ValueError):
        c._is_option_available(c._get("N"))
