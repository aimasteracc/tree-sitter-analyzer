"""Hyphae recursive-descent parser.

Grammar (mirrors mycelium RFC-0003, MVP subset)::

    SelectorList := Selector (',' Selector)*
    Selector     := SimpleSelector ((WS | '>' | '~') SimpleSelector)*
    SimpleSelector := Base Attribute* PseudoClass*
    Base         := HASH | DOT | STAR
    Attribute    := '[' IDENT '=' value ']'
    PseudoClass  := COLON ('(' PseudoArg ')')?
    PseudoArg    := NUMBER | IDENT(path) | SelectorList
"""

from __future__ import annotations

from .ast import (
    AttributeSelector,
    Combined,
    PseudoClass,
    Selector,
    SelectorList,
    SimpleSelector,
)
from .lexer import Token, tokenize

_BASE_TOKENS = frozenset({"HASH", "DOT", "STAR"})
_COMBINATORS = {"GT": ">", "TILDE": "~"}


class HyphaeSyntaxError(ValueError):
    """Raised when a Hyphae selector string is malformed."""


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self._tokens = tokens
        self._pos = 0

    def _peek(self) -> Token:
        return self._tokens[self._pos]

    def _advance(self) -> Token:
        tok = self._tokens[self._pos]
        self._pos += 1
        return tok

    def _expect(self, type_: str) -> Token:
        tok = self._peek()
        if tok.type != type_:
            raise HyphaeSyntaxError(f"expected {type_}, got {tok.type}")
        return self._advance()

    def _skip_ws(self) -> None:
        while self._peek().type == "WS":
            self._advance()

    # -- entry ---------------------------------------------------------------
    def parse(self) -> SelectorList:
        selectors: list[Selector] = []
        self._skip_ws()
        selectors.append(self._parse_selector())
        while True:
            self._skip_ws()
            if self._peek().type == "COMMA":
                self._advance()
                self._skip_ws()
                selectors.append(self._parse_selector())
            else:
                break
        if self._peek().type not in {"EOF", "RPAREN"}:
            raise HyphaeSyntaxError(f"unexpected trailing {self._peek().type}")
        return SelectorList(tuple(selectors))

    # -- selector with combinators ------------------------------------------
    def _parse_selector(self) -> Selector:
        left: Selector = self._parse_simple()
        while True:
            combinator = self._next_combinator()
            if combinator is None:
                break
            right = self._parse_simple()
            left = Combined(left=left, combinator=combinator, right=right)
        return left

    def _next_combinator(self) -> str | None:
        """Return the combinator joining the current and next simple selector.

        ``>`` / ``~`` are explicit; a WS followed by another base is a descendant
        combinator; a WS followed by ``,``/``)``/EOF is decorative and consumed.
        """
        tok = self._peek()
        if tok.type in _COMBINATORS:
            self._advance()
            self._skip_ws()
            return _COMBINATORS[tok.type]
        if tok.type == "WS":
            # Look past the whitespace.
            save = self._pos
            self._skip_ws()
            nxt = self._peek()
            if nxt.type in _BASE_TOKENS:
                return " "  # descendant
            if nxt.type in _COMBINATORS:
                comb = _COMBINATORS[nxt.type]
                self._advance()
                self._skip_ws()
                return comb
            # Decorative whitespace (before comma / close / EOF).
            self._pos = save
            return None
        return None

    # -- simple selector -----------------------------------------------------
    def _parse_simple(self) -> SimpleSelector:
        tok = self._peek()
        if tok.type == "HASH":
            self._advance()
            base = ("name", tok.value)
        elif tok.type == "DOT":
            self._advance()
            base = ("kind", tok.value)
        elif tok.type == "STAR":
            self._advance()
            base = ("universal", "")
        else:
            raise HyphaeSyntaxError(f"expected a base selector, got {tok.type}")

        attributes: list[AttributeSelector] = []
        pseudos: list[PseudoClass] = []
        while True:
            t = self._peek().type
            if t == "LBRACKET":
                attributes.append(self._parse_attribute())
            elif t == "COLON":
                pseudos.append(self._parse_pseudo())
            else:
                break
        return SimpleSelector(
            base=base,
            attributes=tuple(attributes),
            pseudo_classes=tuple(pseudos),
        )

    def _parse_attribute(self) -> AttributeSelector:
        self._expect("LBRACKET")
        name_tok = self._peek()
        if name_tok.type != "IDENT":
            raise HyphaeSyntaxError(
                f"attribute name must be IDENT, got {name_tok.type}"
            )
        self._advance()
        self._expect("EQ")
        value = self._read_value_text()
        self._expect("RBRACKET")
        return AttributeSelector(name=name_tok.value, value=value)

    def _read_value_text(self) -> str:
        """Read an attribute value: IDENT path, or a #name / .kind literal."""
        tok = self._peek()
        if tok.type == "IDENT":
            self._advance()
            return tok.value
        if tok.type in {"HASH", "DOT"}:
            self._advance()
            return tok.value
        if tok.type == "NUMBER":
            self._advance()
            return tok.value
        raise HyphaeSyntaxError(f"attribute value expected, got {tok.type}")

    def _parse_pseudo(self) -> PseudoClass:
        colon = self._expect("COLON")
        name = colon.value
        if self._peek().type != "LPAREN":
            return PseudoClass(name=name, arg=None)
        self._advance()  # (
        self._skip_ws()
        arg = self._parse_pseudo_arg()
        self._skip_ws()
        self._expect("RPAREN")
        return PseudoClass(name=name, arg=arg)

    def _parse_pseudo_arg(self) -> SelectorList | int | str:
        tok = self._peek()
        if tok.type == "NUMBER":
            self._advance()
            return int(tok.value)
        if tok.type == "IDENT":
            self._advance()
            return tok.value  # path, e.g. src/lib.rs
        # Otherwise a nested selector list (#x, .kind, *).
        return self.parse()


def parse(text: str) -> SelectorList:
    """Parse a Hyphae selector string into a :class:`SelectorList`."""
    return _Parser(tokenize(text)).parse()
