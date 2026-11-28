"""JSON with comments and trailing commas (OpenCode's settings), read with the place of every member, so that one member
can be cut out and every other character of the file stays as it was."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

_TOKEN = re.compile(r"""(?P<space>[ \t\r\n]+)
    |(?P<comment>//[^\r\n]*|/\*(?:[^*]|\*(?!/))*\*/)
    |(?P<string>"(?:[^"\\\x00-\x1f]|\\.)*")
    |(?P<mark>[{}\[\]:,])
    |(?P<word>[A-Za-z0-9+\-.]+)""", re.X)


class JsoncError(ValueError):
    def __init__(self, msg: str, text: str, at: int):
        self.line = text.count("\n", 0, at) + 1
        self.column = at - (text.rfind("\n", 0, at) + 1) + 1
        super().__init__(f"{msg}, line {self.line}, column {self.column}")


@dataclass
class Member:
    key: str
    start: int                       # of the key's opening quote
    node: "Node"
    comma: int | None = None         # where the comma after it is, when there is one

    @property
    def end(self) -> int:
        return self.node.end


@dataclass
class Node:
    start: int
    end: int
    value: object
    members: list[Member] = field(default_factory=list)      # of an object
    items: list["Node"] = field(default_factory=list)        # of an array

    def shape(self, without: Member | None = None):
        """What the node says, member by member (a repeated key counts each time), for comparing before and after."""
        if isinstance(self.value, dict):
            return ("object", [(m.key, m.node.shape(without)) for m in self.members if m is not without])
        if isinstance(self.value, list):
            return ("array", [n.shape(without) for n in self.items])
        return ("value", type(self.value).__name__, repr(self.value))


def _tokens(text: str) -> tuple[list[tuple[str, int, int]], list[str]]:
    out, comments, at = [], [], 0
    while at < len(text):
        m = _TOKEN.match(text, at)
        if not m:
            what = "a comment or a string is not closed" if text[at] in '"/' else f"unexpected {text[at]!r}"
            raise JsoncError(what, text, at)
        kind = m.lastgroup
        if kind == "comment":
            comments.append(m.group())
        elif kind != "space":
            out.append((kind, at, m.end()))
        at = m.end()
    return out, comments


def parse(text: str) -> Node:
    """The file as a tree. A file with nothing but comments and space is an empty object."""
    tokens, _ = _tokens(text)
    if not tokens:
        return Node(len(text), len(text), {})
    pos = 0

    def peek() -> str:
        if pos >= len(tokens):
            raise JsoncError("the file ends too early", text, len(text))
        kind, a, b = tokens[pos]
        return text[a:b] if kind == "mark" else kind

    def take() -> tuple[str, int, int]:
        nonlocal pos
        peek()
        pos += 1
        return tokens[pos - 1]

    def scalar(a: int, b: int):
        def refuse(_):
            raise ValueError
        try:
            return json.loads(text[a:b], parse_constant=refuse)
        except ValueError:
            raise JsoncError(f"{text[a:b][:40]} is not a value", text, a) from None

    def value() -> Node:
        kind, a, b = take()
        mark = text[a:b] if kind == "mark" else None
        if mark == "{":
            members: list[Member] = []
            while peek() != "}":
                k, ka, kb = take()
                if k != "string":
                    raise JsoncError("a name in quotes is expected", text, ka)
                key = scalar(ka, kb)
                if peek() != ":":
                    raise JsoncError("':' is expected", text, tokens[pos][1])
                take()
                members.append(Member(key, ka, value()))
                if peek() == ",":
                    members[-1].comma = take()[1]
                elif peek() != "}":
                    raise JsoncError("',' or '}' is expected", text, tokens[pos][1])
            end = take()[2]
            return Node(a, end, {m.key: m.node.value for m in members}, members=members)
        if mark == "[":
            items: list[Node] = []
            while peek() != "]":
                items.append(value())
                if peek() == ",":
                    take()
                elif peek() != "]":
                    raise JsoncError("',' or ']' is expected", text, tokens[pos][1])
            end = take()[2]
            return Node(a, end, [n.value for n in items], items=items)
        if mark is not None:
            raise JsoncError(f"unexpected '{mark}'", text, a)
        return Node(a, b, scalar(a, b))

    try:
        root = value()
    except RecursionError:
        raise JsoncError("it is nested too deeply", text, 0) from None
    if pos < len(tokens):
        raise JsoncError("something follows the end of the settings", text, tokens[pos][1])
    return root


def _objects(node: Node, path: tuple[str, ...]):
    """Every object reached by `path` (each time a name is repeated)."""
    if not path:
        if isinstance(node.value, dict):
            yield node
        return
    for m in node.members:
        if m.key == path[0]:
            yield from _objects(m.node, path[1:])


def _cuts(text: str, obj: Node, i: int) -> list[tuple[int, int]]:
    """The spans to delete to take member i out of obj: the member, its separating comma and, when it had lines to
    itself, those lines."""
    m = obj.members[i]
    start, end, other = m.start, m.end, None
    if m.comma is not None:
        if not text[m.end:m.comma].strip():
            end = m.comma + 1
        else:                                    # a comment sits between the value and its comma: it stays
            other = (m.comma, m.comma + 1)
    elif i and obj.members[i - 1].comma is not None:
        before = obj.members[i - 1].comma         # the last member: the comma before it goes
        other = (before, before + 1)
    line = text.rfind("\n", 0, start) + 1
    rest = re.compile(r"[ \t]*\r?\n").match(text, end)
    if not text[line:start].strip(" \t") and rest:
        start, end = line, rest.end()
    elif m.comma is not None:
        if other is None:
            end = re.compile(r"[ \t]*").match(text, end).end()
    elif other is not None and not text[other[1]:start].strip():
        start, other = other[0], None
    return sorted([(start, end)] + ([other] if other else []))


def _apply(text: str, cuts: list[tuple[int, int]]) -> str:
    for a, b in reversed(cuts):
        text = text[:a] + text[b:]
    return text


def remove(text: str, path: tuple[str, ...], key: str, matches: Callable[[object], bool] = lambda v: True) -> str:
    """`text` without the member `key` of the object at `path`, when its value matches. Everything else stays byte for
    byte. The result is read again and compared; ValueError when it does not say exactly the old settings minus that
    member (then nothing must be written)."""
    while True:
        root = parse(text)
        found = next(((o, i) for o in _objects(root, path) for i, m in enumerate(o.members)
                      if m.key == key and matches(m.node.value)), None)
        if found is None:
            return text
        obj, i = found
        member = obj.members[i]
        cuts = _cuts(text, obj, i)
        for a, b in cuts:                       # outside the member itself only space and its comma may go
            if (text[a:min(b, member.start)] + text[max(a, member.end):b]).strip(" \t\r\n,"):
                raise ValueError("the edit would remove more than the entry")
        new = _apply(text, cuts)
        outside = _tokens(text[:member.start])[1] + _tokens(text[member.end:])[1]
        if parse(new).shape() != root.shape(without=member) or _tokens(new)[1] != outside:
            raise ValueError("the edited file would not say the same as before without the entry")
        text = new
