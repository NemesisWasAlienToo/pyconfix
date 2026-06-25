# MIT License
# 
# Copyright 2025 Nemesis
# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the “Software”), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:
# The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.
# THE SOFTWARE IS PROVIDED “AS IS”, WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

def tokenize(expression: str):
    """Splits an expression string into tokens."""
    i = 0
    n = len(expression)
    tokens = []
    while i < n:
        char = expression[i]
        if char.isspace():
            i += 1
            continue
        # Handle hexadecimal (0x) and binary (0b) prefixes
        if char == '0' and i + 1 < n and expression[i+1].lower() in ('x', 'b'):
            prefix = expression[i:i+2].lower()
            start = i
            i += 2
            # Parse hex digits
            if prefix == '0x':
                while i < n and (expression[i].isdigit() or expression[i].lower() in 'abcdef'):
                    i += 1
            # Parse binary digits
            elif prefix == '0b':
                while i < n and expression[i] in '01':
                    i += 1
            tokens.append(expression[start:i])
        # Numeric literal: digit or dot (with digit following)
        elif char.isdigit() or (char == '.' and i + 1 < n and expression[i+1].isdigit()):
            start = i
            dot_count = 0
            if char == '.':
                dot_count += 1
            i += 1
            while i < n and (expression[i].isdigit() or (expression[i] == '.' and dot_count == 0)):
                if expression[i] == '.':
                    dot_count += 1
                i += 1
            tokens.append(expression[start:i])
        elif char.isalpha() or char == '_':  # Identifier token
            start = i
            while i < n and (expression[i].isalnum() or expression[i] == '_'):
                i += 1
            tokens.append(expression[start:i])
        elif char == "'":
            start = i
            i += 1
            while i < n and expression[i] != "'":
                i += 1
            i += 1  # include closing quote
            tokens.append(expression[start:i])
        elif char in ('&', '|', '!', '=', '>', '<', '+', '-', '*', '/', '^', '%'):
            # Check for two-character operators
            if i + 1 < n and expression[i:i+2] in ('&&', '||', '==', '!=', '>=', '<=', '>>', '<<'):
                tokens.append(expression[i:i+2])
                i += 2
            else:
                tokens.append(char)
                i += 1
        elif char in ('(', ')'):
            tokens.append(char)
            i += 1
        else:
            raise ValueError(f"Unexpected character: {char}")
    return tokens

def shunting_yard(tokens, precedence=None):
    """
    Converts a list of tokens (in infix notation) to a postfix list.
    Precedence mapping:
      !   : 7
      **  : 6 (power)
      *, /, % : 5
      +, - : 4
      >>, <<, & : 3
      ==, !=, >, <, >=, <= : 2
      &&  : 1
      ||, | : 0
    """
    if precedence is None:
        precedence = {
            '!': 7,
            '**': 6,
            '*': 5, '/': 5, '%': 5,
            '+': 4, '-': 4,
            '>>': 3, '<<': 3, '&': 3, '^': 3,
            '==': 2, '!=': 2, '>': 2, '<': 2, '>=': 2, '<=': 2,
            '&&': 1,
            '||': 0, '|': 0,
        }
    right_associative = {'!', '**'}
    output = []
    operators = []
    for token in tokens:
        # Check if token is numeric, identifier, or a quoted string.
        if token.replace('.', '', 1).isdigit() or token.isalnum() or (token.startswith("'") and token.endswith("'")) or '_' in token:
            output.append(token)
        elif token in precedence:
            if token in right_associative:
                while operators and operators[-1] != '(' and precedence[operators[-1]] > precedence[token]:
                    output.append(operators.pop())
            else:
                while operators and operators[-1] != '(' and precedence[operators[-1]] >= precedence[token]:
                    output.append(operators.pop())
            operators.append(token)
        elif token == '(':
            operators.append(token)
        elif token == ')':
            while operators and operators[-1] != '(':
                output.append(operators.pop())
            if operators and operators[-1] == '(':
                operators.pop()
            else:
                raise ValueError("Mismatched parentheses")
    while operators:
        op = operators.pop()
        if op in ('(', ')'):
            raise ValueError("Mismatched parentheses")
        output.append(op)
    return output

class BooleanExpressionParser:
    """
    Evaluates boolean and arithmetic expressions using tokenizing,
    postfix conversion, and evaluation routines.
    """
    def __init__(self, getter, enumerator=None):
        self.getter = getter
        self.enumerator = enumerator if enumerator is not None else {}

    def eval_operator(self, op, right, left=None):
        if op == '!':
            return not bool(right)
        elif op == '&&':
            return bool(left) and bool(right)
        elif op == '||':
            return bool(left) or bool(right)
        elif op == '==':
            return left == right
        elif op == '!=':
            return left != right
        elif op == '>':
            return left > right
        elif op == '<':
            return left < right
        elif op == '>=':
            return left >= right
        elif op == '<=':
            return left <= right
        elif op == '+':
            return left + right
        elif op == '-':
            return left - right
        elif op == '*':
            return left * right
        elif op == '/':
            return left / right
        elif op == '**':
            return left ** right
        elif op == '%':
            return left % right
        elif op == '&':
            return left & right
        elif op == '|':
            return left | right
        elif op == '^':
            return left ^ right
        elif op == '>>':
            return left >> right
        elif op == '<<':
            return left << right
        else:
            raise ValueError(f"Unknown operator: {op}")

    def evaluate_postfix(self, tokens):
        """
        Evaluates a postfix expression given:
        - tokens: list of tokens in postfix order,
        - operand_func: a function that returns the value for a given token,
        - eval_operator: a function that applies an operator.
        """
        stack = []
        for token in tokens:
            if token == 'true':
                stack.append(True)
            elif token == 'false':
                stack.append(False)
            elif token.replace('.', '', 1).isdigit():
                if '.' in token:
                    stack.append(float(token))
                else:
                    stack.append(int(token))
            # @TODO Optimize this, this can be done during tokenization
            elif token.lower().startswith('0x'):
                stack.append(int(token, 16))
            elif token.lower().startswith('0b'):
                stack.append(int(token, 2))
            elif token.isalnum() or (token.startswith("'") and token.endswith("'")) or '_' in token:
                if token.startswith("'") and token.endswith("'"):
                    stack.append(token[1:-1])
                else:
                    stack.append(self.getter(token))
            else:
                if token == '!':
                    if not stack:
                        raise ValueError("Missing operand for '!'")
                    right = stack.pop()
                    stack.append(self.eval_operator(token, right))
                else:
                    if len(stack) < 2:
                        raise ValueError(f"Missing operands for '{token}'")
                    right = stack.pop()
                    left = stack.pop()
                    stack.append(self.eval_operator(token, right, left))
        if len(stack) != 1:
            raise ValueError("Invalid expression: extra items remain on the stack")
        return stack[0]
