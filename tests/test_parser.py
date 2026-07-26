"""Unit tests for the expression parser (pyconfix.parser).

Covers tokenization, operator precedence/associativity and evaluation in
isolation — including the fixed behaviors: `**` is a single right-associative
operator, and the bitwise operators bind above comparisons.
"""

import pytest

from pyconfix.parser import tokenize, shunting_yard, BooleanExpressionParser


def ev(expr, **values):
    """Tokenize -> postfix -> evaluate, resolving identifiers from ``values``."""
    parser = BooleanExpressionParser(getter=lambda k: values[k])
    return parser.evaluate_postfix(shunting_yard(tokenize(expr)))


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
    parser = BooleanExpressionParser(getter=lambda k: None)
    with pytest.raises(ValueError):
        parser.evaluate_postfix(["!"])


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
    parser = BooleanExpressionParser(getter=lambda k: None)
    with pytest.raises(ValueError):
        parser.eval_operator("??", 1, 1)


def test_float_literal_in_postfix():
    assert ev("1.5 + 0.5") == 2.0


def test_extra_items_on_stack_raises():
    parser = BooleanExpressionParser(getter=lambda k: None)
    with pytest.raises(ValueError):
        parser.evaluate_postfix(["1", "2"])   # two operands, no operator
