"""Unit tests for the expression parser (pyconfix.parser).

Covers tokenization, operator precedence/associativity and evaluation in
isolation — including the fixed behaviors: `**` is a single right-associative
operator, and the bitwise operators bind above comparisons.
"""

import pytest

from pyconfix.parser import tokenize, shunting_yard, BooleanExpressionParser


def ev(expr, **values):
    """Tokenize -> postfix -> evaluate, resolving identifiers from ``values``."""
    return BooleanExpressionParser().evaluate_postfix(
        shunting_yard(tokenize(expr)), getter=lambda k: values[k])


# --------------------------------------------------------------------------- #
# Tokenizer
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("expr,tokens", [
    ("A && B", ["A", "&&", "B"]),
    ("A||B", ["A", "||", "B"]),
    ("!A", ["!", "A"]),
    ("2 ** 3", ["2", "**", "3"]),
    ("2**3", ["2", "**", "3"]),          # ** must not split into * *
    ("a >= 1", ["a", ">=", "1"]),
    ("a << 2", ["a", "<<", "2"]),
    ("x != y", ["x", "!=", "y"]),
    ("0xF", ["0xF"]),
    ("0b1010", ["0b1010"]),
    ("1.5", ["1.5"]),
    ("'localhost'", ["'localhost'"]),
    ("(A + B)", ["(", "A", "+", "B", ")"]),
    ("FOO_BAR", ["FOO_BAR"]),
])
def test_tokenize(expr, tokens):
    assert tokenize(expr) == tokens


def test_tokenize_rejects_unexpected_char():
    with pytest.raises(ValueError):
        tokenize("A @ B")


# --------------------------------------------------------------------------- #
# Precedence & associativity
# --------------------------------------------------------------------------- #

def test_arithmetic_precedence():
    assert ev("2 + 3 * 4") == 14           # * before +
    assert ev("(2 + 3) * 4") == 20         # parens override


def test_power_is_right_associative():
    assert ev("2 ** 3 ** 2") == 512        # 2 ** (3 ** 2)


def test_power_binds_tighter_than_multiply():
    assert ev("3 * 2 ** 2") == 12          # 3 * (2 ** 2)


def test_shift_below_addition():
    assert ev("1 << 2 + 1") == 8           # 1 << (2 + 1)


def test_bitwise_binds_above_comparison():
    # (A | B) == C, not A | (B == C)
    assert ev("A | B == C", A=1, B=2, C=3) is True
    assert ev("BITS & 0xF == 0xE", BITS=0xE) is True


def test_comparison_below_logical():
    assert ev("A == 1 && B == 2", A=1, B=2) is True
    assert ev("A == 1 && B == 2", A=1, B=9) is False


# --------------------------------------------------------------------------- #
# Operators & literals
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("expr,expected", [
    ("10 % 3", 1),
    ("2 - 5", -3),
    ("10 / 4", 2.5),
    ("1 << 4", 16),
    ("255 >> 4", 15),
    ("6 & 3", 2),
    ("6 | 1", 7),
    ("6 ^ 3", 5),
    ("0xFF", 255),
    ("0b101", 5),
])
def test_operators_and_literals(expr, expected):
    assert ev(expr) == expected


def test_boolean_literals_and_logic():
    assert ev("true && false") is False
    assert ev("true || false") is True
    assert ev("!false") is True
    assert ev("!A", A=1) is False


def test_string_equality_uses_quoted_literal():
    assert ev("HOST == 'localhost'", HOST="localhost") is True
    assert ev("HOST == 'localhost'", HOST="dev") is False


def test_identifier_resolution_via_getter():
    assert ev("A && B", A=True, B=True) is True
    assert ev("A && B", A=True, B=False) is False


# --------------------------------------------------------------------------- #
# Errors
# --------------------------------------------------------------------------- #

def test_mismatched_parentheses():
    with pytest.raises(ValueError):
        shunting_yard(tokenize("(A && B"))


def test_missing_binary_operand():
    with pytest.raises(ValueError):
        ev("A &&", A=True)


def test_missing_unary_operand():
    parser = BooleanExpressionParser()
    with pytest.raises(ValueError):
        parser.evaluate_postfix(["!"], getter=lambda k: None)


# --------------------------------------------------------------------------- #
# Extra coverage: leading-dot floats, remaining comparison/error branches
# --------------------------------------------------------------------------- #

def test_tokenize_leading_dot_float():
    # A numeric literal that starts with '.' exercises the dot_count init branch.
    assert tokenize(".5") == [".5"]
    assert tokenize(".5 + .25") == [".5", "+", ".25"]


def test_unary_binds_tighter_than_power_pops_higher_precedence():
    # '!' (prec 10) sits on the operator stack when the right-associative '**'
    # (prec 9) arrives, so '!' is popped first — the right-assoc pop branch.
    assert shunting_yard(tokenize("!A ** B")) == ["A", "!", "B", "**"]


def test_close_paren_without_open_raises():
    with pytest.raises(ValueError):
        shunting_yard(tokenize("A )"))


@pytest.mark.parametrize("expr,expected", [
    ("A != B", True),
    ("A > B", True),
    ("A >= B", True),
    ("B <= A", True),
])
def test_remaining_comparison_operators(expr, expected):
    assert ev(expr, A=5, B=3) is expected


def test_eval_operator_unknown_raises():
    parser = BooleanExpressionParser()
    with pytest.raises(ValueError):
        parser.eval_operator("??", 1, 1)


def test_float_literal_in_postfix():
    assert ev("1.5 + 0.5") == 2.0


def test_extra_items_on_stack_raises():
    parser = BooleanExpressionParser()
    with pytest.raises(ValueError):
        parser.evaluate_postfix(["1", "2"], getter=lambda k: None)   # two operands, no operator


# --------------------------------------------------------------------------- #
# Calls: NAME() runs only when allowed, && and || skip their right side
# --------------------------------------------------------------------------- #

def calling(expr, **functions):
    return BooleanExpressionParser().evaluate_postfix(
        shunting_yard(tokenize(expr)), getter=lambda k: functions[k], allow_calls=True)


def recorder(result):
    calls = []
    return (lambda: calls.append(1) or result), calls


def test_call_has_its_own_token():
    assert shunting_yard(tokenize("A() && B()")) == ["A", "()", "B", "()", "&&"]


def test_call_runs_the_function():
    function, calls = recorder(7)
    assert calling("A()", A=function) == 7
    assert calls == [1]


def test_name_without_call_does_not_run_it():
    function, calls = recorder(7)
    assert calling("A", A=function) is function
    assert calls == []


@pytest.mark.parametrize("expr, first, second, ran_second, expected", [
    ("A() && B()", True, True, True, True),
    ("A() && B()", False, True, False, False),
    ("A() || B()", True, True, False, True),
    ("A() || B()", False, True, True, True),
    ("A() || B()", False, False, True, False),
])
def test_logical_operators_skip_the_right_side(expr, first, second, ran_second, expected):
    a, _ = recorder(first)
    b, b_calls = recorder(second)
    assert calling(expr, A=a, B=b) is expected
    assert bool(b_calls) is ran_second


def test_operands_run_left_to_right():
    order = []
    a = lambda: order.append("a") or 1
    b = lambda: order.append("b") or 2
    assert calling("A() + B()", A=a, B=b) == 3
    assert order == ["a", "b"]


@pytest.mark.parametrize("expr, expected", [
    ("!A()", False),
    ("-A() == -1", True),
    ("(A())", 1),
    ("A() + 1 == 2", True),
    ("(A() && A()) || A()", True),
])
def test_call_inside_larger_expressions(expr, expected):
    assert calling(expr, A=lambda: 1) == expected


def test_calls_are_refused_by_default():
    function, calls = recorder(1)
    with pytest.raises(ValueError, match=r"not allowed in this context: A\(\)"):
        BooleanExpressionParser().evaluate_postfix(["A", "()"], getter=lambda k: function)
    assert calls == []


def test_refused_call_raises_even_if_it_would_be_skipped():
    tokens = shunting_yard(tokenize("false && A()"))
    with pytest.raises(ValueError, match="not allowed"):
        BooleanExpressionParser().evaluate_postfix(tokens, getter=lambda k: None)


@pytest.mark.parametrize("expr", ["A(1)", "A(B)", "A(1, 2)", "A(", "A(()"])
def test_calls_take_no_arguments(expr):
    with pytest.raises(ValueError):
        shunting_yard(tokenize(expr))


def test_calling_a_value_raises():
    with pytest.raises(ValueError, match="'A' cannot be called"):
        calling("A()", A=5)


def test_parentheses_after_an_operator_are_not_a_call():
    assert ev("A && (B)", A=True, B=True) is True


def test_skipped_side_is_not_resolved():
    assert ev("false && A") is False

