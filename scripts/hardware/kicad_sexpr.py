"""Small lossless-atom S-expression reader/writer for generated KiCad artifacts."""
from __future__ import annotations

import json
import re
from pathlib import Path


class Atom(str):
    """A KiCad bare atom, as opposed to a quoted string."""


def parse(text: str):
    tokens = re.findall(r'\(|\)|"(?:\\.|[^"\\])*"|[^\s()]+', text)
    stack = []
    root = None
    for token in tokens:
        if token == '(':
            node = []
            if stack:
                stack[-1].append(node)
            else:
                root = node
            stack.append(node)
        elif token == ')':
            stack.pop()
        else:
            stack[-1].append(json.loads(token) if token.startswith('"') else Atom(token))
    if stack:
        raise ValueError('Unclosed S-expression')
    return root


def read(path):
    return parse(Path(path).read_text(encoding='utf-8-sig'))


def dumps(node, level=0):
    if isinstance(node, Atom):
        return str(node)
    if isinstance(node, str):
        return json.dumps(node, ensure_ascii=False)
    if isinstance(node, (float, int)):
        return str(round(node, 6))
    if not any(isinstance(x, list) for x in node):
        return '(' + ' '.join(dumps(x, level + 1) for x in node) + ')'
    parts = []
    for item in node:
        if isinstance(item, list):
            parts.append('\n' + '  ' * (level + 1) + dumps(item, level + 1))
        else:
            parts.append((' ' if parts else '') + dumps(item, level + 1))
    return '(' + ''.join(parts) + '\n' + '  ' * level + ')'


def write(path, node):
    Path(path).write_text(dumps(node) + '\n', encoding='utf-8')


def child(node, tag, default=None):
    return next((x for x in node if isinstance(x, list) and x and x[0] == tag), default)


def children(node, tag):
    return [x for x in node if isinstance(x, list) and x and x[0] == tag]


def walk(node, tag):
    if not isinstance(node, list):
        return
    if node and node[0] == tag:
        yield node
    for item in node:
        if isinstance(item, list):
            yield from walk(item, tag)


def a(tag, *values):
    return [Atom(tag), *values]
