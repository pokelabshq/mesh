"""mesh: a flow-based programming language for agents.

reference implementation — python 3.12, stdlib only.
"""

from __future__ import annotations

import json
import re
import shlex
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError


# ── AST nodes ────────────────────────────────────────────────────────────────

@dataclass
class Value:
    """A literal value in the mesh AST."""
    value: Any
    pos: int = 0  # line position for error reporting

@dataclass
class Ref:
    """A reference to the current pipeline data (the implicit input)."""
    path: str = ""  # e.g. ".items", ".items[:5]"
    pos: int = 0

@dataclass
class ToolCall:
    """A tool invocation."""
    name: str
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)
    flags: list = field(default_factory=list)
    pos: int = 0

@dataclass
class Pipe:
    """A pipe: step → step."""
    left: Any  # ToolCall, Value, Ref, Pipe, Parallel, Conditional, etc.
    right: Any
    pos: int = 0

@dataclass
class Parallel:
    """Parallel execution block."""
    branches: dict[str, list]  # name → list of steps
    pos: int = 0

@dataclass
class Conditional:
    """If/then conditional."""
    condition: Any  # expression to evaluate
    then_steps: list
    else_steps: list = field(default_factory=list)
    pos: int = 0

@dataclass
class ForEach:
    """For each item in collection."""
    var: str
    collection: Any
    steps: list
    pos: int = 0

@dataclass
class TryBlock:
    """Retry/error handling block."""
    steps: list
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
        return {"ok": False, "error": self.message, "step": self.step, "pos": self.pos}

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

# token types
#   WORD     — tool name, argument, keyword
#   STRING   — "quoted string"
#   NUMBER   — 42, 3.14
#   PIPE     — →
#   DOT      — .
#   LBRACKET — [
#   RBRACKET — ]
#   LPAREN   — (
#   RPAREN   — )
#   COMMA    — ,
#   COLON    — :
#   EQUALS   — =
#   BANG     — !
#   GT       — >
#   LT       — -
#   NEWLINE  — line break
#   INDENT   — increase in indentation
#   DEDENT   — decrease in indentation
#   EOF      — end of file

KEYWORDS = {"if", "then", "else", "for", "each", "in", "parallel", "branch",
            "retry", "backoff", "on_error", "import", "tool", "description",
            "input", "output", "steps", "loop", "every", "otherwise", "skip",
            "return", "merge", "as", "by", "with", "true", "false", "null"}

def lex(source: str) -> list[Token]:
    """Tokenize mesh source code."""
    tokens = []
    lines = source.split("\n")
    indent_stack = [0]
    pos = 0

    for line_num, line in enumerate(lines):
        # skip empty lines and comments
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("//"):
            pos += len(line) + 1
            continue

        # compute indent
        indent = len(line) - len(line.lstrip())
        if indent > indent_stack[-1]:
            tokens.append(Token("INDENT", "", pos))
            indent_stack.append(indent)
        while indent < indent_stack[-1]:
            tokens.append(Token("DEDENT", "", pos))
            indent_stack.pop()
        if indent != indent_stack[-1]:
            # inconsistent dedent — reset
            while len(indent_stack) > 1 and indent < indent_stack[-1]:
                tokens.append(Token("DEDENT", "", pos))
                indent_stack.pop()
            if indent > indent_stack[-1]:
                tokens.append(Token("INDENT", "", pos))
                indent_stack.append(indent)

        i = 0
        while i < len(stripped):
            c = stripped[i]

            # skip whitespace
            if c in " \t":
                i += 1
                continue

            # pipe
            if c == "→" or (c == "-" and i + 1 < len(stripped) and stripped[i + 1] == ">"):
                tokens.append(Token("PIPE", "→", pos + i))
                i += 1 if c == "→" else 2
                continue

            # string
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

            # number
            if c.isdigit() or (c == "-" and i + 1 < len(stripped) and stripped[i + 1].isdigit()):
                j = i + 1
                while j < len(stripped) and (stripped[j].isdigit() or stripped[j] == "."):
                    j += 1
                tokens.append(Token("NUMBER", stripped[i:j], pos + i))
                i = j
                continue

            # bracket access [n:m]
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

            # symbols
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

            # word (tool name, keyword, or argument)
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

            # skip unknown chars
            i += 1

        pos += len(line) + 1

    # close remaining indents
    while len(indent_stack) > 1:
        tokens.append(Token("DEDENT", "", pos))
        indent_stack.pop()

    tokens.append(Token("EOF", "", pos))
    return tokens


# ── parser ───────────────────────────────────────────────────────────────────

class Parser:
    """Recursive descent parser for mesh."""

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
        """Parse the full source into a list of top-level statements."""
        statements = []
        while self.peek().type != "EOF":
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        return statements

    def parse_statement(self):
        """Parse a single top-level statement."""
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

        # default: parse a pipeline
        return self.parse_pipeline()

    def parse_import(self):
        self.advance()  # consume 'import'
        path = self.expect("STRING")
        return {"type": "import", "path": path.value}

    def parse_tool_def(self):
        self.advance()  # consume 'tool'
        name = self.expect("WORD").value
        self.expect("COLON")
        # skip tool body for now (simplified)
        self._skip_block()
        return {"type": "tool_def", "name": name}

    def parse_parallel(self):
        tok = self.advance()  # consume 'parallel'
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
        tok = self.advance()  # consume 'for'
        self.expect("KEYWORD")  # 'each'
        var = self.expect("WORD").value
        # collection is the rest of the line
        collection_parts = []
        while self.peek().type not in ("COLON", "NEWLINE", "EOF"):
            collection_parts.append(self.advance().value)
        collection = " ".join(collection_parts)
        self.match("COLON")
        self.match("NEWLINE", "INDENT")
        steps = self._parse_block()
        return ForEach(var=var, collection=collection, steps=steps, pos=tok.pos)

    def parse_retry(self):
        tok = self.advance()  # consume 'retry'
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
        tok = self.advance()  # consume 'loop'
        self.expect("KEYWORD")  # 'every'
        interval = self.expect("NUMBER").value
        self.expect("COLON")
        self.match("NEWLINE", "INDENT")
        steps = self._parse_block()
        return {"type": "loop", "interval": int(interval), "steps": steps, "pos": tok.pos}

    def parse_conditional(self):
        tok = self.advance()  # consume 'if'
        # parse condition
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
        """Parse a pipeline: step → step → step."""
        left = self.parse_step()
        while self.match("PIPE"):
            right = self.parse_step()
            left = Pipe(left=left, right=right, pos=0)
        return left

    def parse_step(self):
        """Parse a single pipeline step (tool call, value, or ref)."""
        tok = self.peek()

        # reference to pipeline data
        if tok.type == "DOT":
            return self.parse_ref()

        # literal value
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

        # tool call
        if tok.type == "WORD":
            return self.parse_tool_call()

        # skip unknown
        self.advance()
        return None

    def parse_ref(self):
        """Parse a data reference: .field, .items[:5], etc."""
        self.expect("DOT")
        path = "."
        if self.peek().type == "WORD":
            path += self.advance().value
        if self.peek().type == "ACCESS":
            path += self.advance().value
        return Ref(path=path, pos=0)

    def parse_tool_call(self):
        """Parse a tool call: tool_name arg1 arg2 key=value."""
        name = self.expect("WORD").value
        args = []
        kwargs = {}
        flags = []

        while self.peek().type in ("WORD", "STRING", "NUMBER", "DOT"):
            tok = self.peek()
            if tok.type == "WORD" and self.pos + 1 < len(self.tokens) and self.tokens[self.pos + 1].type == "ASSIGN":
                key = self.advance().value
                self.advance()  # consume =
                val = self.advance()
                kwargs[key] = self._coerce_value(val)
            elif tok.type == "WORD" and tok.value.startswith("--"):
                flags.append(self.advance().value)
            else:
                args.append(self._coerce_value(self.advance()))

        return ToolCall(name=name, args=args, kwargs=kwargs, flags=flags, pos=0)

    def _parse_block(self) -> list:
        """Parse an indented block of statements."""
        statements = []
        while self.peek().type not in ("DEDENT", "EOF"):
            stmt = self.parse_statement()
            if stmt:
                statements.append(stmt)
        self.match("DEDENT")
        return statements

    def _skip_block(self):
        """Skip an indented block (for tool defs we don't parse yet)."""
        self.match("NEWLINE", "INDENT")
        depth = 1
        while depth > 0 and self.peek().type != "EOF":
            if self.peek().type == "INDENT":
                depth += 1
            elif self.peek().type == "DEDENT":
                depth -= 1
            self.advance()

    def _coerce_value(self, tok: Token) -> Any:
        """Convert a token to a python value."""
        if tok.type == "STRING":
            return tok.value
        if tok.type == "NUMBER":
            return float(tok.value) if "." in tok.value else int(tok.value)
        if tok.type == "KEYWORD":
            if tok.value == "true": return True
            if tok.value == "false": return False
            if tok.value == "null": return None
        return tok.value


# ── runtime: built-in tools ──────────────────────────────────────────────────

class ToolRegistry:
    """Registry of available tools."""

    def __init__(self):
        self.tools: dict[str, Callable] = {}
        self._register_builtins()

    def register(self, name: str, fn: Callable):
        self.tools[name] = fn

    def get(self, name: str) -> Optional[Callable]:
        return self.tools.get(name)

    def list_tools(self) -> list[str]:
        return sorted(self.tools.keys())

    def _register_builtins(self):
        self.register("print", self._print)
        self.register("json.parse", self._json_parse)
        self.register("json.stringify", self._json_stringify)
        self.register("http.get", self._http_get)
        self.register("http.post", self._http_post)
        self.register("filter", self._filter)
        self.register("map", self._map)
        self.register("count", self._count)
        self.register("first", self._first)
        self.register("last", self._last)
        self.register("take", self._take)
        self.register("skip", self._skip)
        self.register("sort", self._sort)
        self.register("unique", self._unique)
        self.register("flatten", self._flatten)
        self.register("format", self._format)
        self.register("log", self._log)
        self.register("return", self._return)
        self.register("wait", self._wait)
        self.register("now", self._now)
        self.register("uuid", self._uuid)
        self.register("env", self._env)
        self.register("shell", self._shell)
        self.register("merge", self._merge)
        self.register("length", self._length)
        self.register("keys", self._keys)
        self.register("values", self._values)
        self.register("type", self._type)
        self.register("string", self._string)
        self.register("number", self._number)
        self.register("save", self._save)
        self.register("load", self._load)

    # ── data tools ──

    @staticmethod
    def _json_parse(data, **kw):
        if isinstance(data, str):
            return json.loads(data)
        return data

    @staticmethod
    def _json_stringify(data, **kw):
        return json.dumps(data, indent=2, default=str)

    @staticmethod
    def _length(data, **kw):
        if hasattr(data, "__len__"):
            return len(data)
        return 0

    @staticmethod
    def _keys(data, **kw):
        if isinstance(data, dict):
            return list(data.keys())
        return []

    @staticmethod
    def _values(data, **kw):
        if isinstance(data, dict):
            return list(data.values())
        return []

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

    # ── http tools ──

    @staticmethod
    def _http_get(data=None, *args, **kw):
        url = args[0] if args else data
        if not url:
            return err("http.get requires a url")
        try:
            req = Request(str(url), headers={"User-Agent": "mesh/0.1"})
            with urlopen(req, timeout=kw.get("timeout", 30)) as resp:
                body = resp.read().decode("utf-8")
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": body,
                    "json": lambda: json.loads(body),
                }
        except HTTPError as e:
            return {"status": e.code, "error": str(e), "body": ""}
        except URLError as e:
            return err(f"http error: {e.reason}", retryable=True)

    @staticmethod
    def _http_post(data=None, *args, **kw):
        url = args[0] if args else data
        body = kw.get("body", {})
        if isinstance(body, dict):
            body = json.dumps(body).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        try:
            req = Request(
                str(url),
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "mesh/0.1"},
                method="POST",
            )
            with urlopen(req, timeout=kw.get("timeout", 30)) as resp:
                return {
                    "status": resp.status,
                    "body": resp.read().decode("utf-8"),
                }
        except HTTPError as e:
            return {"status": e.code, "error": str(e)}

    # ── collection tools ──

    @staticmethod
    def _filter(data, *args, **kw):
        if not isinstance(data, (list, tuple)):
            return data
        # simplified: filter by truthiness or by expression
        condition = args[0] if args else kw.get("where", "true")
        if condition == "true":
            return [x for x in data if x]
        return data

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
        key = kw.get("by", "")
        seen = set()
        result = []
        for item in data:
            k = item.get(key) if key and isinstance(item, dict) else str(item)
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
    def _merge(data, *args, **kw):
        """merge multiple parallel branch results."""
        if isinstance(data, dict):
            # merge all list values
            result = []
            for v in data.values():
                if isinstance(v, list):
                    result.extend(v)
                else:
                    result.append(v)
            return result
        return data

    # ── output tools ──

    @staticmethod
    def _print(data, **kw):
        if isinstance(data, (dict, list)):
            print(json.dumps(data, indent=2, default=str))
        else:
            print(data)
        return data

    @staticmethod
    def _format(data, *args, **kw):
        template = args[0] if args else kw.get("as", "{{.}}")
        if isinstance(data, dict):
            try:
                # support both {{.name}} and {name} styles
                result = template
                for key, val in data.items():
                    result = result.replace("{{." + key + "}}", str(val))
                    result = result.replace("{" + key + "}", str(val))
                return result
            except (KeyError, IndexError):
                return template
        return str(data)

    @staticmethod
    def _log(data, *args, **kw):
        level = args[0] if args else kw.get("level", "info")
        msg = args[1] if len(args) > 1 else str(data)
        print(f"[{level}] {msg}")
        return data

    @staticmethod
    def _return(data, **kw):
        return data

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

    # ── utility tools ──

    @staticmethod
    def _wait(data, *args, **kw):
        seconds = float(args[0]) if args else kw.get("seconds", 1)
        time.sleep(seconds)
        return data

    @staticmethod
    def _now(data=None, **kw):
        import datetime
        return datetime.datetime.now().isoformat()

    @staticmethod
    def _uuid(data=None, **kw):
        import uuid
        return str(uuid.uuid4())

    @staticmethod
    def _env(data=None, *args, **kw):
        name = args[0] if args else data
        return os.environ.get(str(name), "")

    @staticmethod
    def _shell(data=None, *args, **kw):
        import subprocess
        cmd = args[0] if args else data
        result = subprocess.run(str(cmd), shell=True, capture_output=True, text=True)
        return {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}


import os  # needed for _env and _save/_load


# ── executor ─────────────────────────────────────────────────────────────────

class Executor:
    """Execute a mesh AST."""

    def __init__(self, registry: ToolRegistry | None = None):
        self.registry = registry or ToolRegistry()
        self.log: list[dict] = []

    def execute(self, statements: list, input_data=None) -> Any:
        """Execute a list of top-level statements."""
        data = input_data
        for stmt in statements:
            data = self._exec_node(stmt, data)
        return data

    def _exec_node(self, node, data):
        """Execute a single AST node."""
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
        """Resolve a data reference like .items[:5]."""
        if not ref.path or ref.path == ".":
            return data

        path = ref.path.lstrip(".")
        # handle slice notation
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
            # apply slice
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
        """Execute a tool call."""
        fn = self.registry.get(call.name)
        if fn is None:
            self._log("error", f"unknown tool: {call.name}", call.pos)
            return err(f"unknown tool: {call.name}", step=call.name, pos=call.pos)

        try:
            # first positional arg is pipeline data if the tool expects it
            result = fn(data, *call.args, **call.kwargs)
            self._log("ok", f"{call.name}", call.pos)
            return result
        except Exception as e:
            self._log("error", f"{call.name}: {e}", call.pos)
            return err(str(e), step=call.name, pos=call.pos, retryable=True)

    def _exec_parallel(self, node: Parallel, data):
        """Execute parallel branches (sequential for now — threading later)."""
        results = {}
        for name, steps in node.branches.items():
            branch_data = data
            for step in steps:
                branch_data = self._exec_node(step, branch_data)
            results[name] = branch_data
        return results

    def _exec_conditional(self, node: Conditional, data):
        """Execute if/then/else."""
        # simplified: evaluate condition as string match
        # in a full impl, this would parse the condition expression
        condition_result = self._eval_condition(node.condition, data)
        if condition_result:
            for step in node.then_steps:
                data = self._exec_node(step, data)
        elif node.else_steps:
            for step in node.else_steps:
                data = self._exec_node(step, data)
        return data

    def _eval_condition(self, condition: str, data) -> bool:
        """Evaluate a simple condition string."""
        # very simplified: check for != and ==
        condition = condition.strip()
        if "==" in condition:
            left, right = condition.split("==", 1)
            return self._eval_expr(left.strip(), data) == self._eval_expr(right.strip(), data)
        if "!=" in condition:
            left, right = condition.split("!=", 1)
            return self._eval_expr(left.strip(), data) != self._eval_expr(right.strip(), data)
        return bool(condition)

    def _eval_expr(self, expr: str, data):
        """Evaluate a simple expression against data."""
        expr = expr.strip()
        if expr.startswith("."):
            return self._resolve_ref(Ref(path=expr), data)
        # literal
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
        """Execute for each item."""
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
        """Execute with retry."""
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
        """Execute a dict node (import, tool_def, etc.)."""
        if node.get("type") == "import":
            # simplified: just log
            self._log("info", f"import: {node['path']}")
        elif node.get("type") == "loop":
            for step in node.get("steps", []):
                data = self._exec_node(step, data)
        return data

    def _log(self, level: str, message: str, pos: int = 0):
        entry = {"level": level, "message": message, "pos": pos, "time": time.time()}
        self.log.append(entry)


# ── cli ──────────────────────────────────────────────────────────────────────

def run(source: str, input_data=None, registry: ToolRegistry | None = None) -> Any:
    """Parse and execute mesh source code."""
    tokens = lex(source)
    parser = Parser(tokens)
    ast = parser.parse()
    executor = Executor(registry=registry)
    return executor.execute(ast, input_data)

def run_file(path: str, input_data=None, registry: ToolRegistry | None = None) -> Any:
    """Run a .mesh file."""
    with open(path) as f:
        return run(f.read(), input_data, registry)

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
    print("mesh repl — type 'exit' to quit, 'tools' to list tools")
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
            for name in executor.registry.list_tools():
                print(f"  {name}")
            continue
        try:
            result = run(line, registry=registry)
            if result is not None:
                if isinstance(result, (dict, list)):
                    print(json.dumps(result, indent=2, default=str))
                else:
                    print(result)
        except Exception as e:
            print(f"error: {e}")


if __name__ == "__main__":
    import argparse as ap
    p = ap.ArgumentParser(description="mesh: flow-based language for agents")
    p.add_argument("file", nargs="?", help=".mesh file to run")
    p.add_argument("--check", action="store_true", help="check syntax only")
    p.add_argument("--repl", action="store_true", help="interactive repl")
    p.add_argument("--tools", action="store_true", help="list available tools")
    args = p.parse_args()

    reg = ToolRegistry()

    if args.tools:
        for name in reg.list_tools():
            print(name)
    elif args.repl:
        repl(reg)
    elif args.file:
        if args.check:
            errs = check(open(args.file).read())
            for e in errs:
                print(f"error: {e}")
            sys.exit(1 if errs else 0)
        else:
            result = run_file(args.file, registry=reg)
            if result is not None:
                print(json.dumps(result, indent=2, default=str) if isinstance(result, (dict, list)) else result)
    else:
        repl(reg)
