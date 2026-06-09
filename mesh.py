"""mesh: a flow-based programming language for agents.

reference implementation — python 3.12, stdlib only.
v0.3.0: modules, http rewrite, tool metadata, execution trace.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import sys
import time
import traceback
import datetime
import uuid
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode, urlparse


# ── AST nodes ────────────────────────────────────────────────────────────────

@dataclass
class Value:
    value: Any
    pos: int = 0

@dataclass
class Ref:
    path: str = ""
    pos: int = 0

@dataclass
class ToolCall:
    name: str
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)
    pos: int = 0

@dataclass
class Pipe:
    left: Any
    right: Any
    pos: int = 0

@dataclass
class Parallel:
    branches: dict[str, list] = field(default_factory=dict)
    pos: int = 0

@dataclass
class Conditional:
    condition: str = ""
    then_steps: list = field(default_factory=list)
    else_steps: list = field(default_factory=list)
    pos: int = 0

@dataclass
class ForEach:
    var: str = ""
    collection: str = ""
    steps: list = field(default_factory=list)
    pos: int = 0

@dataclass
class TryBlock:
    steps: list = field(default_factory=list)
    retries: int = 0
    backoff: float = 0.0
    on_error: list = field(default_factory=list)
    pos: int = 0


# ── errors ───────────────────────────────────────────────────────────────────

@dataclass
class MeshError:
    message: str
    step: str = ""
    pos: int = 0
    retryable: bool = False

    def to_dict(self):
        return {"ok": False, "error": self.message, "step": self.step, "pos": self.pos, "retryable": self.retryable}

@dataclass
class MeshOk:
    data: Any

    def to_dict(self):
        return {"ok": True, "data": self.data}

def ok(data): return MeshOk(data)
def err(msg, step="", pos=0, retryable=False): return MeshError(msg, step, pos, retryable)


# ── lexer ────────────────────────────────────────────────────────────────────

@dataclass
class Token:
    type: str
    value: str
    pos: int = 0

KEYWORDS = {
    "if", "then", "else", "for", "each", "in", "parallel", "branch",
    "retry", "backoff", "on_error", "import", "tool", "description",
    "input", "output", "steps", "loop", "every", "otherwise", "skip",
    "return", "merge", "as", "by", "with", "true", "false", "null"
}

def lex(source: str) -> list[Token]:
    tokens = []
    lines = source.split("\n")
    indent_stack = [0]
    pos = 0

    for line_num, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            pos += len(line) + 1
            continue

        indent = len(line) - len(line.lstrip())
        if indent > indent_stack[-1]:
            tokens.append(Token("INDENT", "", pos))
            indent_stack.append(indent)
        while indent < indent_stack[-1]:
            tokens.append(Token("DEDENT", "", pos))
            indent_stack.pop()
        if indent != indent_stack[-1]:
            while len(indent_stack) > 1 and indent < indent_stack[-1]:
                tokens.append(Token("DEDENT", "", pos))
                indent_stack.pop()
            if indent > indent_stack[-1]:
                tokens.append(Token("INDENT", "", pos))
                indent_stack.append(indent)

        i = 0
        while i < len(stripped):
            c = stripped[i]

            if c in " \t":
                i += 1
                continue

            if c == "\u2192" or (c == "-" and i + 1 < len(stripped) and stripped[i + 1] == ">"):
                tokens.append(Token("PIPE", "\u2192", pos + i))
                i += 1 if c == "\u2192" else 2
                continue

            if c in ('"', "'"):
                quote = c
                j = i + 1
                while j < len(stripped) and stripped[j] != quote:
                    if stripped[j] == "\\":
                        j += 1
                    j += 1
                tokens.append(Token("STRING", stripped[i + 1:j], pos + i))
                i = j + 1
                continue

            if c.isdigit() or (c == "-" and i + 1 < len(stripped) and stripped[i + 1].isdigit()):
                j = i + 1
                while j < len(stripped) and (stripped[j].isdigit() or stripped[j] == "."):
                    j += 1
                tokens.append(Token("NUMBER", stripped[i:j], pos + i))
                i = j
                continue

            if c == "[":
                j = i + 1
                depth = 1
                while j < len(stripped) and depth > 0:
                    if stripped[j] == "[": depth += 1
                    elif stripped[j] == "]": depth -= 1
                    j += 1
                tokens.append(Token("ACCESS", stripped[i:j], pos + i))
                i = j
                continue

            if c == ".":
                tokens.append(Token("DOT", ".", pos + i))
                i += 1
                continue
            if c == ",":
                tokens.append(Token("COMMA", ",", pos + i))
                i += 1
                continue
            if c == ":":
                tokens.append(Token("COLON", ":", pos + i))
                i += 1
                continue
            if c == "=":
                if i + 1 < len(stripped) and stripped[i + 1] == "=":
                    tokens.append(Token("EQUALS", "==", pos + i))
                    i += 2
                else:
                    tokens.append(Token("ASSIGN", "=", pos + i))
                    i += 1
                continue
            if c == "!" and i + 1 < len(stripped) and stripped[i + 1] == "=":
                tokens.append(Token("BANGEQ", "!=", pos + i))
                i += 2
                continue
            if c == "(":
                tokens.append(Token("LPAREN", "(", pos + i))
                i += 1
                continue
            if c == ")":
                tokens.append(Token("RPAREN", ")", pos + i))
                i += 1
                continue
            if c == "|":
                tokens.append(Token("PIPE", "|", pos + i))
                i += 1
                continue

            if c.isalpha() or c == "_" or c == "-":
                j = i
                while j < len(stripped) and (stripped[j].isalnum() or stripped[j] in "_-."):
                    j += 1
                word = stripped[i:j]
                if word in KEYWORDS:
                    tokens.append(Token("KEYWORD", word, pos + i))
                else:
                    tokens.append(Token("WORD", word, pos + i))
                i = j
                continue

            i += 1

        pos += len(line) + 1

    while len(indent_stack) > 1:
        tokens.append(Token("DEDENT", "", pos))
        indent_stack.pop()

    tokens.append(Token("EOF", "", pos))
    return tokens


# ── parser ───────────────────────────────────────────────────────────────────

class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self, offset=0) -> Token:
        idx = self.pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return Token("EOF", "", 0)

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, type: str) -> Token:
        tok = self.advance()
        if tok.type != type:
            raise SyntaxError(f"expected {type}, got {tok.type} ('{tok.value}') at pos {tok.pos}")
        return tok

    def match(self, *types: str) -> Optional[Token]:
        if self.peek().type in types:
            return self.advance()
        return None

    def parse(self) -> list:
        statements = []
        while self.peek().type != "EOF":
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        return statements

    def parse_statement(self):
        tok = self.peek()

        if tok.type == "KEYWORD" and tok.value == "import":
            return self.parse_import()
        if tok.type == "KEYWORD" and tok.value == "tool":
            return self.parse_tool_def()
        if tok.type == "KEYWORD" and tok.value == "parallel":
            return self.parse_parallel()
        if tok.type == "KEYWORD" and tok.value == "for":
            return self.parse_for()
        if tok.type == "KEYWORD" and tok.value == "retry":
            return self.parse_retry()
        if tok.type == "KEYWORD" and tok.value == "loop":
            return self.parse_loop()
        if tok.type == "KEYWORD" and tok.value == "if":
            return self.parse_conditional()

        return self.parse_pipeline()

    def parse_import(self):
        self.advance()
        path_tok = self.expect("STRING")
        alias = None
        if self.peek().type == "KEYWORD" and self.peek().value == "as":
            self.advance()
            alias = self.expect("WORD").value
        return {"type": "import", "path": path_tok.value, "alias": alias, "pos": path_tok.pos}

    def parse_tool_def(self):
        """Parse a tool definition block."""
        tok = self.advance()  # consume 'tool'
        name = self.expect("WORD").value
        self.expect("COLON")
        self.match("NEWLINE", "INDENT")

        meta = {"description": "", "input_type": "any", "output_type": "any", "category": "user"}
        steps = []

        # parse key-value metadata
        while self.peek().type == "WORD" and self.peek().value in ("description", "input", "output", "category"):
            key = self.advance().value
            self.expect("COLON")
            val = self.advance().value
            meta[key] = val

        # parse steps block
        if self.peek().type == "KEYWORD" and self.peek().value == "steps":
            self.advance()
            self.expect("COLON")
            self.match("NEWLINE", "INDENT")
            steps = self._parse_block()

        # skip remaining indented content
        while self.peek().type not in ("DEDENT", "EOF"):
            if self.peek().type == "KEYWORD" and self.peek().value == "steps":
                break
            self.advance()

        if self.peek().type == "DEDENT":
            self.match("DEDENT")

        return {"type": "tool_def", "name": name, "meta": meta, "steps": steps, "pos": tok.pos}

    def parse_parallel(self):
        tok = self.advance()
        self.expect("COLON")
        self.match("NEWLINE", "INDENT")
        branches = {}
        while self.peek().type != "DEDENT" and self.peek().type != "EOF":
            if self.peek().type == "KEYWORD" and self.peek().value == "branch":
                self.advance()
                name = self.expect("WORD").value
                self.expect("COLON")
                self.match("NEWLINE", "INDENT")
                steps = self._parse_block()
                branches[name] = steps
            else:
                self.advance()
        self.match("DEDENT")
        return Parallel(branches=branches, pos=tok.pos)

    def parse_for(self):
        tok = self.advance()
        self.expect("KEYWORD")  # 'each'
        var = self.expect("WORD").value
        collection_parts = []
        while self.peek().type not in ("COLON", "NEWLINE", "EOF"):
            collection_parts.append(self.advance().value)
        collection = " ".join(collection_parts)
        self.match("COLON")
        self.match("NEWLINE", "INDENT")
        steps = self._parse_block()
        return ForEach(var=var, collection=collection, steps=steps, pos=tok.pos)

    def parse_retry(self):
        tok = self.advance()
        retries = int(self.expect("NUMBER").value)
        backoff = 0.0
        if self.match("COMMA"):
            if self.peek().type == "KEYWORD" and self.peek().value == "backoff":
                self.advance()
                backoff = float(self.expect("NUMBER").value)
        self.expect("COLON")
        self.match("NEWLINE", "INDENT")
        steps = self._parse_block()
        return TryBlock(steps=steps, retries=retries, backoff=backoff, pos=tok.pos)

    def parse_loop(self):
        tok = self.advance()
        self.expect("KEYWORD")  # 'every'
        interval = self.expect("NUMBER").value
        self.expect("COLON")
        self.match("NEWLINE", "INDENT")
        steps = self._parse_block()
        return {"type": "loop", "interval": int(interval), "steps": steps, "pos": tok.pos}

    def parse_conditional(self):
        tok = self.advance()
        cond_parts = []
        while self.peek().type not in ("COLON", "NEWLINE", "EOF"):
            cond_parts.append(self.advance().value)
        condition = " ".join(cond_parts)
        self.match("COLON")
        self.match("NEWLINE", "INDENT")
        then_steps = self._parse_block()
        else_steps = []
        if self.peek().type == "KEYWORD" and self.peek().value == "else":
            self.advance()
            self.expect("COLON")
            self.match("NEWLINE", "INDENT")
            else_steps = self._parse_block()
        return Conditional(condition=condition, then_steps=then_steps, else_steps=else_steps, pos=tok.pos)

    def parse_pipeline(self):
        left = self.parse_step()
        while self.match("PIPE"):
            right = self.parse_step()
            left = Pipe(left=left, right=right, pos=0)
        return left

    def parse_step(self):
        tok = self.peek()

        if tok.type == "DOT":
            return self.parse_ref()

        if tok.type == "STRING":
            self.advance()
            return Value(value=tok.value, pos=tok.pos)
        if tok.type == "NUMBER":
            self.advance()
            v = tok.value
            return Value(value=float(v) if "." in v else int(v), pos=tok.pos)
        if tok.type == "KEYWORD" and tok.value == "true":
            self.advance()
            return Value(value=True, pos=tok.pos)
        if tok.type == "KEYWORD" and tok.value == "false":
            self.advance()
            return Value(value=False, pos=tok.pos)
        if tok.type == "KEYWORD" and tok.value == "null":
            self.advance()
            return Value(value=None, pos=tok.pos)

        if tok.type == "WORD":
            return self.parse_tool_call()

        self.advance()
        return None

    def parse_ref(self):
        self.expect("DOT")
        path = "."
        if self.peek().type == "WORD":
            path += self.advance().value
        if self.peek().type == "ACCESS":
            path += self.advance().value
        return Ref(path=path, pos=0)

    def parse_tool_call(self):
        name = self.expect("WORD").value
        args = []
        kwargs = {}
        flags = []

        while self.peek().type in ("WORD", "STRING", "NUMBER", "DOT"):
            tok = self.peek()
            if tok.type == "WORD" and self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == "ASSIGN":
                key = self.advance().value
                self.advance()
                val = self.advance()
                kwargs[key] = self._coerce_value(val)
            elif tok.type == "WORD" and tok.value.startswith("--"):
                flags.append(self.advance().value)
            else:
                args.append(self._coerce_value(self.advance()))

        return ToolCall(name=name, args=args, kwargs=kwargs, flags=flags, pos=0)

    def _parse_block(self) -> list:
        statements = []
        while self.peek().type not in ("DEDENT", "EOF"):
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        self.match("DEDENT")
        return statements

    def _skip_block(self):
        self.match("NEWLINE", "INDENT")
        depth = 1
        while depth > 0 and self.peek().type != "EOF":
            if self.peek().type == "INDENT":
                depth += 1
            elif self.peek().type == "DEDENT":
                depth -= 1
            self.advance()

    def _coerce_value(self, tok: Token) -> Any:
        if tok.type == "STRING":
            return tok.value
        if tok.type == "NUMBER":
            return float(tok.value) if "." in tok.value else int(tok.value)
        if tok.type == "KEYWORD":
            if tok.value == "true": return True
            if tok.value == "false": return False
            if tok.value == "null": return None
        return tok.value


# ── tool metadata + registry ─────────────────────────────────────────────────

@dataclass
class ToolMeta:
    name: str
    fn: Callable
    description: str = ""
    input_type: str = "any"
    output_type: str = "any"
    category: str = "core"

class ToolRegistry:
    def __init__(self):
        self.tools: dict[str, ToolMeta] = {}
        self._register_builtins()

    def register(self, name: str, fn: Callable, description: str = "",
                 input_type: str = "any", output_type: str = "any", category: str = "core"):
        self.tools[name] = ToolMeta(name, fn, description, input_type, output_type, category)

    def get(self, name: str) -> Optional[Callable]:
        meta = self.tools.get(name)
        return meta.fn if meta else None

    def get_meta(self, name: str) -> Optional[ToolMeta]:
        return self.tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self.tools.keys())

    def list_by_category(self) -> dict[str, list[str]]:
        cats: dict[str, list[str]] = {}
        for name, meta in sorted(self.tools.items()):
            cats.setdefault(meta.category, []).append(name)
        return cats

    def load_pack(self, path: str):
        """Load a tool pack from a JSON or YAML file."""
        with open(path) as f:
            if path.endswith((".yaml", ".yml")):
                # minimal yaml: each tool is a doc with name, description, code
                try:
                    import yaml
                    data = yaml.safe_load(f)
                except ImportError:
                    # fallback: parse manually
                    data = json.load(f)
            else:
                data = json.load(f)

        if isinstance(data, list):
            for tool in data:
                name = tool.get("name", "")
                desc = tool.get("description", "")
                cat = tool.get("category", "custom")
                if name and name not in self.tools:
                    self.register(name, self._print, desc, "any", "any", cat)
        elif isinstance(data, dict) and "tools" in data:
            for tool in data["tools"]:
                name = tool.get("name", "")
                desc = tool.get("description", "")
                cat = tool.get("category", "custom")
                if name and name not in self.tools:
                    self.register(name, self._print, desc, "any", "any", cat)

    # ── core tools ──

    def _register_builtins(self):
        # io
        self.register("print", self._print, "print data to stdout", "any", "any", "io")
        self.register("log", self._log, "log a message with level", "any", "any", "io")
        self.register("return", self._return_passthrough, "return data unchanged", "any", "any", "io")
        self.register("save", self._save, "save data to a json file", "any", "any", "io")
        self.register("load", self._load, "load data from a json file", "any", "any", "io")
        self.register("format", self._format, "format data with template string", "any", "string", "io")

        # json
        self.register("json.parse", self._json_parse, "parse json string", "string", "any", "json")
        self.register("json.stringify", self._json_stringify, "serialize to json", "any", "string", "json")

        # collections
        self.register("filter", self._filter, "filter list by truthiness", "list", "list", "collections")
        self.register("map", self._map, "extract field from list of dicts", "list", "list", "collections")
        self.register("count", self._count, "count items", "any", "number", "collections")
        self.register("first", self._first, "get first item", "any", "any", "collections")
        self.register("last", self._last, "get last item", "any", "any", "collections")
        self.register("take", self._take, "take first n items", "list", "list", "collections")
        self.register("skip", self._skip, "skip first n items", "list", "list", "collections")
        self.register("sort", self._sort, "sort list", "list", "list", "collections")
        self.register("unique", self._unique, "deduplicate list", "list", "list", "collections")
        self.register("flatten", self._flatten, "flatten nested lists", "list", "list", "collections")
        self.register("merge", self._merge, "merge dict values into list", "dict", "list", "collections")
        self.register("length", self._length, "get length", "any", "number", "collections")
        self.register("keys", self._keys, "get dict keys", "dict", "list", "collections")
        self.register("values", self._values, "get dict values", "dict", "list", "collections")
        self.register("group", self._group_by, "group list items by field", "list", "dict", "collections")

        # type
        self.register("type", self._type, "get type name", "any", "string", "type")
        self.register("string", self._string, "convert to string", "any", "string", "type")
        self.register("number", self._number, "convert to number", "any", "number", "type")
        self.register("trim", self._trim, "trim whitespace", "string", "string", "type")

        # http
        self.register("http.get", self._http_get, "http get request with auth/headers", "any", "any", "http")
        self.register("http.post", self._http_post, "http post with body and auth", "any", "any", "http")
        self.register("http.put", self._http_put, "http put request", "any", "any", "http")
        self.register("http.patch", self._http_patch, "http patch request", "any", "any", "http")
        self.register("http.delete", self._http_delete, "http delete request", "any", "any", "http")

        # system
        self.register("shell", self._shell, "run shell command", "any", "any", "system")
        self.register("env", self._env, "get environment variable", "any", "string", "system")
        self.register("now", self._now, "current timestamp", "any", "string", "system")
        self.register("uuid", self._uuid, "generate uuid", "any", "string", "system")
        self.register("wait", self._wait, "sleep for seconds", "any", "any", "system")

        # string
        self.register("upper", self._upper, "uppercase string", "string", "string", "string")
        self.register("lower", self._lower, "lowercase string", "string", "string", "string")
        self.register("replace", self._replace, "replace substring", "string", "string", "string")
        self.register("split", self._split, "split string by delimiter", "string", "list", "string")
        self.register("join", self._join, "join list with delimiter", "list", "string", "string")
        self.register("contains", self._contains, "check if string contains substring", "string", "boolean", "string")

        # math
        self.register("add", self._add, "add two numbers", "number", "number", "math")
        self.register("sub", self._sub, "subtract two numbers", "number", "number", "math")
        self.register("mul", self._mul, "multiply two numbers", "number", "number", "math")
        self.register("div", self._div, "divide two numbers", "number", "number", "math")

    # ── io tools ──

    @staticmethod
    def _print(data, **kw):
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2, default=str))
        else:
            print(data)
        return data

    @staticmethod
    def _log(data, *args, **kw):
        level = args[0] if args else kw.get("level", "info")
        msg = args[1] if len(args) > 1 else str(data)
        print(f"[{level}] {msg}")
        return data

    @staticmethod
    def _return_passthrough(data, **kw):
        return data

    @staticmethod
    def _format(data, *args, **kw):
        template = args[0] if args else kw.get("as", "{{.}}")
        if isinstance(data, dict):
            result = template
            for key, val in data.items():
                result = result.replace("{{." + key + "}}", str(val))
                result = result.replace("{" + key + "}", str(val))
            return result
        if isinstance(data, list):
            return "\n".join(str(item) for item in data)
        return str(data)

    @staticmethod
    def _save(data, *args, **kw):
        path = args[0] if args else kw.get("path", "output.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return data

    @staticmethod
    def _load(data=None, *args, **kw):
        path = args[0] if args else data
        with open(str(path)) as f:
            return json.load(f)

    # ── json tools ──

    @staticmethod
    def _json_parse(data, **kw):
        if isinstance(data, str):
            return json.loads(data)
        return data

    @staticmethod
    def _json_stringify(data, **kw):
        return json.dumps(data, indent=2, default=str)

    # ── collection tools ──

    @staticmethod
    def _filter(data, *args, **kw):
        if not isinstance(data, (list, tuple)):
            return data
        return [x for x in data if x]

    @staticmethod
    def _map(data, *args, **kw):
        if not isinstance(data, (list, tuple)):
            return data
        field = args[0] if args else kw.get("field", "")
        if field:
            return [x.get(field) if isinstance(x, dict) else getattr(x, field, None) for x in data]
        return data

    @staticmethod
    def _count(data, **kw):
        if hasattr(data, "__len__"):
            return len(data)
        return 0

    @staticmethod
    def _first(data, **kw):
        if isinstance(data, (list, tuple)) and data:
            return data[0]
        return data

    @staticmethod
    def _last(data, **kw):
        if isinstance(data, (list, tuple)) and data:
            return data[-1]
        return data

    @staticmethod
    def _take(data, *args, **kw):
        n = int(args[0]) if args else kw.get("n", 10)
        if isinstance(data, (list, tuple)):
            return data[:n]
        return data

    @staticmethod
    def _skip(data, *args, **kw):
        n = int(args[0]) if args else kw.get("n", 0)
        if isinstance(data, (list, tuple)):
            return data[n:]
        return data

    @staticmethod
    def _sort(data, *args, **kw):
        if not isinstance(data, (list, tuple)):
            return data
        key = kw.get("by", "")
        if key:
            return sorted(data, key=lambda x: x.get(key, 0) if isinstance(x, dict) else getattr(x, key, 0))
        return sorted(data, key=str)

    @staticmethod
    def _unique(data, *args, **kw):
        if not isinstance(data, (list, tuple)):
            return data
        seen = set()
        result = []
        for item in data:
            k = str(item)
            if k not in seen:
                seen.add(k)
                result.append(item)
        return result

    @staticmethod
    def _flatten(data, **kw):
        if not isinstance(data, (list, tuple)):
            return data
        result = []
        for item in data:
            if isinstance(item, (list, tuple)):
                result.extend(item)
            else:
                result.append(item)
        return result

    @staticmethod
    def _merge(data, **kw):
        if isinstance(data, dict):
            result = []
            for v in data.values():
                if isinstance(v, list):
                    result.extend(v)
                else:
                    result.append(v)
            return result
        return data

    @staticmethod
    def _length(data, **kw):
        return len(data) if hasattr(data, "__len__") else 0

    @staticmethod
    def _keys(data, **kw):
        return list(data.keys()) if isinstance(data, dict) else []

    @staticmethod
    def _values(data, **kw):
        return list(data.values()) if isinstance(data, dict) else []

    @staticmethod
    def _group_by(data, *args, **kw):
        if not isinstance(data, (list, tuple)):
            return data
        field = args[0] if args else kw.get("by", "")
        if not field:
            return data
        groups: dict = {}
        for item in data:
            k = item.get(field, "unknown") if isinstance(item, dict) else getattr(item, field, "unknown")
            groups.setdefault(str(k), []).append(item)
        return groups

    # ── type tools ──

    @staticmethod
    def _type(data, **kw):
        return type(data).__name__

    @staticmethod
    def _string(data, **kw):
        return str(data)

    @staticmethod
    def _number(data, **kw):
        try:
            return float(data)
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _trim(data, **kw):
        return str(data).strip()

    # ── http tools (v2) ──

    # rate limiting: track per domain
    _rate_limits: dict[str, float] = {}

    @classmethod
    def _http_get(cls, data=None, *args, **kw):
        url = args[0] if args else data
        if not url:
            return err("http.get requires a url")
        return cls._http_request("GET", str(url), None, **kw)

    @classmethod
    def _http_post(cls, data=None, *args, **kw):
        url = args[0] if args else data
        body = kw.get("body", {})
        return cls._http_request("POST", str(url), body, **kw)

    @classmethod
    def _http_put(cls, data=None, *args, **kw):
        url = args[0] if args else data
        body = kw.get("body", {})
        return cls._http_request("PUT", str(url), body, **kw)

    @classmethod
    def _http_patch(cls, data=None, *args, **kw):
        url = args[0] if args else data
        body = kw.get("body", {})
        return cls._http_request("PATCH", str(url), body, **kw)

    @classmethod
    def _http_delete(cls, data=None, *args, **kw):
        url = args[0] if args else data
        return cls._http_request("DELETE", str(url), None, **kw)

    @classmethod
    def _http_request(cls, method: str, url: str, body=None, **kw):
        """Generic http request with auth, headers, rate limiting."""
        # rate limiting
        domain = urlparse(url).netloc
        min_interval = kw.get("rate_limit", 0)  # min seconds between calls to same domain
        if min_interval > 0 and domain in cls._rate_limits:
            elapsed = time.time() - cls._rate_limits[domain]
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

        # build headers
        headers = {"User-Agent": "mesh/0.3"}
        headers.update(kw.get("headers", {}))

        # auth
        if "bearer" in kw:
            headers["Authorization"] = f"Bearer {kw['bearer']}"
        elif "token" in kw:
            headers["Authorization"] = f"Bearer {kw['token']}"
        elif "api_key" in kw:
            headers["X-API-Key"] = kw["api_key"]

        # query params
        params = kw.get("params", {})
        if params:
            url = url + ("&" if "?" in url else "?") + urlencode(params)

        # body
        req_body = None
        if body is not None:
            if isinstance(body, (dict, list)):
                req_body = json.dumps(body).encode("utf-8")
                headers.setdefault("Content-Type", "application/json")
            elif isinstance(body, str):
                req_body = body.encode("utf-8")
            else:
                req_body = body

        timeout = kw.get("timeout", 30)
        follow_redirects = kw.get("follow_redirects", True)

        try:
            req = Request(url, data=req_body, headers=headers, method=method)
            cls._rate_limits[domain] = time.time()

            with urlopen(req, timeout=timeout) as resp:
                resp_body = resp.read().decode("utf-8")
                result = {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": resp_body,
                }
                # auto-parse json
                content_type = resp.headers.get("Content-Type", "")
                if "json" in content_type:
                    try:
                        result["json"] = json.loads(resp_body)
                    except json.JSONDecodeError:
                        pass
                return result

        except HTTPError as e:
            retryable = e.code >= 500
            body_text = ""
            try:
                body_text = e.read().decode("utf-8")
            except Exception:
                pass
            return err(
                f"http {method} {url} -> {e.code}: {e.reason}",
                step=f"http.{method.lower()}",
                retryable=retryable,
            )
        except URLError as e:
            return err(f"http error: {e.reason}", retryable=True)
        except Exception as e:
            return err(f"http error: {e}", retryable=True)

    # ── system tools ──

    @staticmethod
    def _shell(data=None, *args, **kw):
        cmd = args[0] if args else data
        if not cmd:
            return err("shell requires a command")
        result = subprocess.run(str(cmd), shell=True, capture_output=True, text=True, timeout=kw.get("timeout", 60))
        return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}

    @staticmethod
    def _env(data=None, *args, **kw):
        name = args[0] if args else data
        return os.environ.get(str(name), "")

    @staticmethod
    def _now(data=None, **kw):
        return datetime.datetime.now().isoformat()

    @staticmethod
    def _uuid(data=None, **kw):
        return str(uuid.uuid4())

    @staticmethod
    def _wait(data, *args, **kw):
        seconds = float(args[0]) if args else kw.get("seconds", 1)
        time.sleep(seconds)
        return data

    # ── string tools ──

    @staticmethod
    def _upper(data, **kw):
        return str(data).upper()

    @staticmethod
    def _lower(data, **kw):
        return str(data).lower()

    @staticmethod
    def _replace(data, *args, **kw):
        old = args[0] if len(args) > 0 else kw.get("old", "")
        new = args[1] if len(args) > 1 else kw.get("new", "")
        return str(data).replace(str(old), str(new))

    @staticmethod
    def _split(data, *args, **kw):
        delim = args[0] if args else kw.get("by", " ")
        return str(data).split(str(delim))

    @staticmethod
    def _join(data, *args, **kw):
        sep = args[0] if args else kw.get("with", " ")
        if isinstance(data, (list, tuple)):
            return str(sep).join(str(x) for x in data)
        return str(data)

    @staticmethod
    def _contains(data, *args, **kw):
        substr = args[0] if args else kw.get("in", "")
        return str(substr) in str(data)

    # ── math tools ──

    @staticmethod
    def _add(data, *args, **kw):
        b = float(args[0]) if args else kw.get("to", 0)
        return float(data) + b

    @staticmethod
    def _sub(data, *args, **kw):
        b = float(args[0]) if args else kw.get("by", 0)
        return float(data) - b

    @staticmethod
    def _mul(data, *args, **kw):
        b = float(args[0]) if args else kw.get("by", 1)
        return float(data) * b

    @staticmethod
    def _div(data, *args, **kw):
        b = float(args[0]) if args else kw.get("by", 1)
        if b == 0:
            return err("division by zero")
        return float(data) / b


# ── executor ─────────────────────────────────────────────────────────────────

class Executor:
    def __init__(self, registry: ToolRegistry | None = None, dry_run: bool = False):
        self.registry = registry or ToolRegistry()
        self.log: list[dict] = []
        self.dry_run = dry_run
        self._import_stack: list[str] = []  # circular import detection

    def execute(self, statements: list, input_data=None) -> Any:
        data = input_data
        for stmt in statements:
            data = self._exec_node(stmt, data)
        return data

    def execute_with_trace(self, statements: list, input_data=None):
        """Execute and yield (step_num, step_name, input, output, duration) for each tool call."""
        data = input_data
        step_num = 0
        for stmt in statements:
            # collect all tool calls in this statement
            tool_calls = self._collect_tools(stmt)
            for tc in tool_calls:
                step_num += 1
                fn = self.registry.get(tc.name)
                meta = self.registry.get_meta(tc.name)
                desc = meta.description if meta else tc.name
                yield {
                    "step": step_num,
                    "tool": tc.name,
                    "description": desc,
                    "input": data,
                    "input_type": type(data).__name__,
                } if self.dry_run else None

            data = self._exec_node(stmt, data)

            if step_num > 0 and not self.dry_run:
                yield {
                    "step": step_num,
                    "output": data,
                    "output_type": type(data).__name__,
                }

        statements_trace = statements  # keep for reuse
        return data

    def _collect_tools(self, node) -> list[ToolCall]:
        """Collect all tool calls from a statement (for trace)."""
        if node is None:
            return []
        if isinstance(node, ToolCall):
            return [node]
        if isinstance(node, Pipe):
            return self._collect_tools(node.left) + self._collect_tools(node.right)
        if isinstance(node, Parallel):
            calls = []
            for steps in node.branches.values():
                for step in steps:
                    calls.extend(self._collect_tools(step))
            return calls
        if isinstance(node, Conditional):
            return self._collect_tools_from_list(node.then_steps) + self._collect_tools_from_list(node.else_steps)
        if isinstance(node, ForEach):
            return self._collect_tools_from_list(node.steps)
        if isinstance(node, TryBlock):
            return self._collect_tools_from_list(node.steps) + self._collect_tools_from_list(node.on_error)
        return []

    def _collect_tools_from_list(self, steps) -> list[ToolCall]:
        calls = []
        for step in steps:
            calls.extend(self._collect_tools(step))
        return calls

    def _exec_node(self, node, data):
        if node is None:
            return data

        if isinstance(node, Value):
            return node.value

        if isinstance(node, Ref):
            return self._resolve_ref(node, data)

        if isinstance(node, ToolCall):
            return self._exec_tool(node, data)

        if isinstance(node, Pipe):
            left_result = self._exec_node(node.left, data)
            return self._exec_node(node.right, left_result)

        if isinstance(node, Parallel):
            return self._exec_parallel(node, data)

        if isinstance(node, Conditional):
            return self._exec_conditional(node, data)

        if isinstance(node, ForEach):
            return self._exec_foreach(node, data)

        if isinstance(node, TryBlock):
            return self._exec_try(node, data)

        if isinstance(node, dict):
            return self._exec_dict(node, data)

        return data

    def _resolve_ref(self, ref: Ref, data):
        if not ref.path or ref.path == ".":
            return data

        path = ref.path.lstrip(".")
        if "[" in path:
            field, slice_part = path.split("[", 1)
            slice_part = slice_part.rstrip("]")
            current = data
            if field and isinstance(current, dict):
                current = current.get(field)
            elif field and isinstance(current, (list, tuple)):
                try:
                    current = current[int(field)]
                except (ValueError, IndexError):
                    return None
            if ":" in slice_part:
                parts = slice_part.split(":")
                start = int(parts[0]) if parts[0] else 0
                end = int(parts[1]) if len(parts) > 1 and parts[1] else None
                if end is not None:
                    return current[start:end]
                return current[start:]
            else:
                return current[int(slice_part)]
        else:
            if isinstance(data, dict):
                return data.get(path)
            return getattr(data, path, None)

    def _exec_tool(self, call: ToolCall, data):
        if self.dry_run:
            self._log("dry-run", f"would call: {call.name} with data={type(data).__name__}", call.pos)
            return data

        fn = self.registry.get(call.name)
        if fn is None:
            self._log("error", f"unknown tool: {call.name}", call.pos)
            return err(f"unknown tool: {call.name}", step=call.name, pos=call.pos)

        start = time.time()
        try:
            result = fn(data, *call.args, **call.kwargs)
            duration = (time.time() - start) * 1000
            self._log("ok", f"{call.name}", call.pos, duration=duration,
                      input_type=type(data).__name__, output_type=type(result).__name__)
            return result
        except Exception as e:
            duration = (time.time() - start) * 1000
            self._log("error", f"{call.name}: {e}", call.pos, duration=duration)
            return err(str(e), step=call.name, pos=call.pos, retryable=True)

    def _exec_parallel(self, node: Parallel, data):
        results = {}
        for name, steps in node.branches.items():
            branch_data = data
            for step in steps:
                branch_data = self._exec_node(step, branch_data)
            results[name] = branch_data
        return results

    def _exec_conditional(self, node: Conditional, data):
        condition_result = self._eval_condition(node.condition, data)
        if condition_result:
            for step in node.then_steps:
                data = self._exec_node(step, data)
        elif node.else_steps:
            for step in node.else_steps:
                data = self._exec_node(step, data)
        return data

    def _eval_condition(self, condition: str, data) -> bool:
        condition = condition.strip()
        if "==" in condition:
            left, right = condition.split("==", 1)
            return self._eval_expr(left.strip(), data) == self._eval_expr(right.strip(), data)
        if "!=" in condition:
            left, right = condition.split("!=", 1)
            return self._eval_expr(left.strip(), data) != self._eval_expr(right.strip(), data)
        return bool(condition)

    def _eval_expr(self, expr: str, data):
        expr = expr.strip()
        if expr.startswith("."):
            return self._resolve_ref(Ref(path=expr), data)
        if expr.startswith('"') and expr.endswith('"'):
            return expr[1:-1]
        if expr == "true": return True
        if expr == "false": return False
        if expr == "null": return None
        try: return int(expr)
        except ValueError:
            try: return float(expr)
            except ValueError: return expr

    def _exec_foreach(self, node: ForEach, data):
        collection = self._eval_expr(node.collection, data)
        if not isinstance(collection, (list, tuple)):
            return data
        results = []
        for item in collection:
            item_data = item
            for step in node.steps:
                item_data = self._exec_node(step, item_data)
            results.append(item_data)
        return results

    def _exec_try(self, node: TryBlock, data):
        last_result = data
        for attempt in range(node.retries + 1):
            try:
                for step in node.steps:
                    last_result = self._exec_node(step, last_result)
                return last_result
            except Exception as e:
                if node.backoff > 0 and attempt < node.retries:
                    time.sleep(node.backoff * (attempt + 1))
                if attempt == node.retries:
                    if node.on_error:
                        for step in node.on_error:
                            last_result = self._exec_node(step, last_result)
                    return err(str(e), retryable=False)
        return last_result

    def _exec_dict(self, node: dict, data):
        if node.get("type") == "import":
            return self._exec_import(node, data)
        if node.get("type") == "tool_def":
            self._exec_tool_def(node)
            return data
        if node.get("type") == "loop":
            for step in node.get("steps", []):
                data = self._exec_node(step, data)
        return data

    def _exec_import(self, node: dict, data):
        path = node["path"]
        alias = node.get("alias")

        # resolve path: relative to cwd, then MESH_PATH
        resolved = path
        if not os.path.isfile(resolved):
            mesh_path = os.environ.get("MESH_PATH", "")
            for prefix in mesh_path.split(":"):
                candidate = os.path.join(prefix, path)
                if os.path.isfile(candidate):
                    resolved = candidate
                    break

        if not os.path.isfile(resolved):
            return err(f"import not found: {path}")

        # circular import detection
        if resolved in self._import_stack:
            return err(f"circular import: {' -> '.join(self._import_stack)} -> {resolved}")

        self._import_stack.append(resolved)
        try:
            with open(resolved) as f:
                source = f.read()
            sub_registry = ToolRegistry()
            sub_registry.tools = self.registry.tools  # share tools
            sub_executor = Executor(registry=sub_registry)
            sub_executor._import_stack = self._import_stack
            ast = Parser(lex(source)).parse()
            sub_executor.execute(ast, data)
        except Exception as e:
            self._log("error", f"import {path}: {e}", node.get("pos", 0))
        finally:
            self._import_stack.pop()

        return data

    def _exec_tool_def(self, node: dict):
        """Register a user-defined tool from a tool_def block."""
        name = node["name"]
        meta = node.get("meta", {})
        steps = node.get("steps", [])

        if not steps:
            return

        def tool_fn(data, *args, **kw):
            sub_registry = ToolRegistry()
            sub_registry.tools = self.registry.tools
            sub_executor = Executor(registry=sub_registry)
            result = data
            for step in steps:
                result = sub_executor._exec_node(step, result)
            return result

        self.registry.register(
            name, tool_fn,
            description=meta.get("description", ""),
            input_type=meta.get("input_type", "any"),
            output_type=meta.get("output_type", "any"),
            category=meta.get("category", "user"),
        )

    def _log(self, level: str, message: str, pos: int = 0, duration: float = 0,
             input_type: str = "", output_type: str = ""):
        entry = {
            "level": level, "message": message, "pos": pos,
            "time": time.time(), "duration_ms": round(duration, 2),
            "input_type": input_type, "output_type": output_type,
        }
        self.log.append(entry)


# ── module loader ────────────────────────────────────────────────────────────

class ModuleLoader:
    """Load and manage mesh modules."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.loaded: dict[str, dict] = {}  # path -> module info

    def load(self, path: str) -> dict:
        if path in self.loaded:
            return self.loaded[path]

        search_paths = ["."] + os.environ.get("MESH_PATH", "").split(":")
        resolved = None
        for prefix in search_paths:
            candidate = os.path.join(prefix.strip(), path)
            if os.path.isfile(candidate):
                resolved = os.path.abspath(candidate)
                break

        if not resolved:
            return {"error": f"module not found: {path}"}

        with open(resolved) as f:
            source = f.read()

        tokens = lex(source)
        parser = Parser(tokens)
        ast = parser.parse()

        module_info = {
            "path": resolved,
            "source": source,
            "ast": ast,
            "tools": [],
            "exports": [],
        }

        # extract tool defs
        for stmt in ast:
            if isinstance(stmt, dict) and stmt.get("type") == "tool_def":
                module_info["tools"].append(stmt["name"])
                module_info["exports"].append(stmt["name"])

        self.loaded[path] = module_info
        return module_info


# ── cli ──────────────────────────────────────────────────────────────────────

def run(source: str, input_data=None, registry: ToolRegistry | None = None,
        dry_run: bool = False, timeout: int = 120) -> Any:
    """Parse and execute mesh source code."""
    tokens = lex(source)
    parser = Parser(tokens)
    ast = parser.parse()
    executor = Executor(registry=registry, dry_run=dry_run)
    if timeout > 0:
        # set a wall-clock timeout via alarm (unix only)
        def _timeout_handler(signum, frame):
            raise TimeoutError(f"execution timed out after {timeout}s")
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)
    try:
        result = executor.execute(ast, input_data)
    finally:
        if timeout > 0:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    return result

def run_file(path: str, input_data=None, registry: ToolRegistry | None = None,
             dry_run: bool = False, timeout: int = 120) -> Any:
    """Run a .mesh file, returns (result, logs)."""
    with open(path) as f:
        source = f.read()
    tokens = lex(source)
    parser = Parser(tokens)
    ast = parser.parse()
    executor = Executor(registry=registry, dry_run=dry_run)
    if timeout > 0:
        def _timeout_handler(signum, frame):
            raise TimeoutError(f"execution timed out after {timeout}s")
        old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
        signal.alarm(timeout)
    try:
        result = executor.execute(ast, input_data)
    finally:
        if timeout > 0:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old_handler)
    return result, executor.log

def check(source: str) -> list[str]:
    """Check mesh source for errors without executing."""
    errors = []
    try:
        tokens = lex(source)
        parser = Parser(tokens)
        parser.parse()
    except SyntaxError as e:
        errors.append(str(e))
    except Exception as e:
        errors.append(f"parse error: {e}")
    return errors

def repl(registry: ToolRegistry | None = None):
    """Interactive mesh repl."""
    print("mesh repl v0.3 — type 'exit' to quit, 'tools' to list tools, 'trace' for last log")
    executor = Executor(registry=registry)
    while True:
        try:
            line = input("mesh> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line == "exit":
            break
        if line == "tools":
            reg = executor.registry
            for cat, names in sorted(reg.list_by_category().items()):
                print(f"  [{cat}]")
                for name in names:
                    meta = reg.get_meta(name)
                    desc = meta.description if meta else ""
                    print(f"    {name}: {desc}")
            continue
        if line == "trace":
            for entry in executor.log[-10:]:
                print(f"  [{entry['level']}] {entry['message']} ({entry.get('duration_ms', 0):.1f}ms)")
            continue
        try:
            result = run(line, registry=executor.registry)
            if result is not None:
                if isinstance(result, (dict, list)):
                    print(json.dumps(result, indent=2, default=str))
                else:
                    print(result)
        except Exception as e:
            print(f"error: {e}")


if __name__ == "__main__":
    import argparse as ap
    p = ap.ArgumentParser(description="mesh: flow-based language for agents v0.3")
    p.add_argument("file", nargs="?", help=".mesh file to run")
    p.add_argument("--check", action="store_true", help="check syntax only")
    p.add_argument("--repl", action="store_true", help="interactive repl")
    p.add_argument("--tools", action="store_true", help="list available tools")
    p.add_argument("--tools-count", action="store_true", help="print tool count")
    p.add_argument("--dry-run", action="store_true", help="dry run (don't execute tools)")
    p.add_argument("--timeout", type=int, default=120, help="execution timeout in seconds (default 120)")
    p.add_argument("--trace", action="store_true", help="show step-by-step trace")
    p.add_argument("--eval", type=str, help="evaluate inline mesh expression")
    args = p.parse_args()

    reg = ToolRegistry()

    if args.tools_count:
        print(f"{len(reg.list_tools())} tools")
    elif args.tools:
        for cat, names in sorted(reg.list_by_category().items()):
            print(f"[{cat}]")
            for name in names:
                meta = reg.get_meta(name)
                desc = meta.description if meta else ""
                print(f"  {name}: {desc}")
    elif args.eval:
        result = run(args.eval, registry=reg)
        if result is not None:
            print(json.dumps(result, indent=2, default=str) if isinstance(result, (dict, list)) else result)
    elif args.repl:
        repl(reg)
    elif args.file:
        if args.check:
            errs = check(open(args.file).read())
            for e in errs:
                print(f"error: {e}")
            sys.exit(1 if errs else 0)
        else:
            result, logs = run_file(args.file, registry=reg, dry_run=args.dry_run, timeout=args.timeout)
            if result is not None:
                print(json.dumps(result, indent=2, default=str) if isinstance(result, (dict, list)) else result)
            if args.trace:
                print("--- execution trace ---")
                for entry in logs:
                    dur = f" ({entry.get('duration_ms', 0):.1f}ms)" if entry.get('duration_ms') else ""
                    print(f"  [{entry['level']}] {entry['message']}{dur}")
    else:
        repl(reg)
