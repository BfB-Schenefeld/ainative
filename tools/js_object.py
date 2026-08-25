#!/usr/bin/env python3
"""
js_object.py -- parse a JavaScript object/array literal into Python data.

Vite/Rollup bundles hold content as JS object literals, not JSON: keys are usually
unquoted, strings may use single quotes or backticks, and there can be trailing commas.
`json.loads` chokes on all of that. This is a small recursive-descent parser for the
subset that data literals actually use.

Not supported (and not needed for data): expressions, function values, computed keys,
template interpolation, comments inside literals.

Used as a library by extract_upgrade_path.py; also runnable for a quick check:
    python3 tools/js_object.py bundle.js --find QUESTION_BANK
"""
from __future__ import annotations

import json
import re
import sys

WS = " \t\r\n"
ESCAPES = {'"': '"', "'": "'", "`": "`", "\\": "\\", "/": "/",
           "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "\n": ""}
IDENT_START = re.compile(r"[A-Za-z_$]")
IDENT = re.compile(r"[A-Za-z0-9_$]")
NUMBER = re.compile(r"-?(?:0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)")


class JSParseError(ValueError):
    pass


class Parser:
    def __init__(self, text: str, pos: int = 0):
        self.s = text
        self.i = pos

    def error(self, msg: str):
        ctx = self.s[max(0, self.i - 40): self.i + 40].replace("\n", " ")
        raise JSParseError(f"{msg} at {self.i}: …{ctx}…")

    def skip(self):
        while self.i < len(self.s) and self.s[self.i] in WS:
            self.i += 1

    def parse_value(self):
        self.skip()
        if self.i >= len(self.s):
            self.error("unexpected end")
        c = self.s[self.i]
        if c == "{":
            return self.parse_object()
        if c == "[":
            return self.parse_array()
        if c in "\"'`":
            return self.parse_string()
        if self.s.startswith("!0", self.i) and not self.s.startswith("!0x", self.i):
            self.i += 2  # minified `true`
            return True
        if self.s.startswith("!1", self.i):
            self.i += 2  # minified `false`
            return False
        if self.s.startswith("void 0", self.i):
            self.i += 6  # minified `undefined`
            return None
        if self.s.startswith("true", self.i):
            self.i += 4
            return True
        if self.s.startswith("false", self.i):
            self.i += 5
            return False
        if self.s.startswith("null", self.i):
            self.i += 4
            return None
        if self.s.startswith("undefined", self.i):
            self.i += 9
            return None
        m = NUMBER.match(self.s, self.i)
        if m:
            self.i = m.end()
            raw = m.group(0)
            if raw.lower().startswith(("0x", "-0x")):
                return int(raw, 16)
            return float(raw) if any(ch in raw for ch in ".eE") else int(raw)
        # bare identifier: a minified variable reference, not a literal value
        m = re.match(r"[A-Za-z_$][A-Za-z0-9_$.]*", self.s[self.i:])
        if m:
            self.i += m.end()
            return {"__ref__": m.group(0)}
        self.error(f"unexpected character {c!r}")

    def parse_string(self):
        quote = self.s[self.i]
        self.i += 1
        out = []
        while self.i < len(self.s):
            c = self.s[self.i]
            if c == "\\":
                self.i += 1
                e = self.s[self.i]
                if e == "u":
                    if self.s[self.i + 1] == "{":
                        end = self.s.index("}", self.i)
                        out.append(chr(int(self.s[self.i + 2:end], 16)))
                        self.i = end + 1
                    else:
                        out.append(chr(int(self.s[self.i + 1:self.i + 5], 16)))
                        self.i += 5
                    continue
                if e == "x":
                    out.append(chr(int(self.s[self.i + 1:self.i + 3], 16)))
                    self.i += 3
                    continue
                out.append(ESCAPES.get(e, e))
                self.i += 1
                continue
            if c == quote:
                self.i += 1
                return "".join(out)
            if c == "$" and quote == "`" and self.s[self.i + 1:self.i + 2] == "{":
                self.error("template interpolation in string")
            out.append(c)
            self.i += 1
        self.error("unterminated string")

    def parse_key(self):
        self.skip()
        c = self.s[self.i]
        if c in "\"'`":
            return self.parse_string()
        if IDENT_START.match(c):
            j = self.i
            while j < len(self.s) and IDENT.match(self.s[j]):
                j += 1
            key = self.s[self.i:j]
            self.i = j
            return key
        m = NUMBER.match(self.s, self.i)
        if m:
            self.i = m.end()
            return m.group(0)
        self.error("bad object key")

    def parse_object(self):
        self.i += 1  # {
        obj = {}
        while True:
            self.skip()
            if self.i >= len(self.s):
                self.error("unterminated object")
            if self.s[self.i] == "}":
                self.i += 1
                return obj
            if self.s[self.i] == ",":
                self.i += 1
                continue
            if self.s.startswith("...", self.i):
                self.error("spread in object")
            key = self.parse_key()
            self.skip()
            if self.s[self.i] != ":":
                # shorthand property { foo }
                obj[key] = {"__ref__": key}
                continue
            self.i += 1
            obj[key] = self.parse_value()

    def parse_array(self):
        self.i += 1  # [
        arr = []
        while True:
            self.skip()
            if self.i >= len(self.s):
                self.error("unterminated array")
            if self.s[self.i] == "]":
                self.i += 1
                return arr
            if self.s[self.i] == ",":
                self.i += 1
                continue
            arr.append(self.parse_value())


def parse_at(text: str, pos: int):
    """Parse the literal beginning at pos. Returns (value, end_pos)."""
    p = Parser(text, pos)
    val = p.parse_value()
    return val, p.i


def find_binding(text: str, exported_name: str):
    """
    Find a minified binding by its export alias.

    Rollup emits `export{h as QUESTION_BANK, i as QUIZ_SIZE}`. This resolves
    QUESTION_BANK -> h, then finds `const h=[` / `var h=[` / `h=[` and parses it.
    Falls back to treating exported_name as the local name.
    """
    local = exported_name
    m = re.search(rf"([A-Za-z_$][\w$]*)\s+as\s+{re.escape(exported_name)}\b", text)
    if m:
        local = m.group(1)
    m = re.search(rf"(?:const|let|var)\s+{re.escape(local)}\s*=\s*(?=[\[{{])", text)
    if not m:
        m = re.search(rf"[,;\s]{re.escape(local)}\s*=\s*(?=[\[{{])", text)
    if not m:  # scalar binding (number, string, boolean)
        m = re.search(rf"(?:(?:const|let|var)\s+|[,;])\s*{re.escape(local)}\s*=\s*(?![=>])", text)
    if not m:
        raise JSParseError(f"binding for {exported_name!r} (local {local!r}) not found")
    return parse_at(text, m.end())[0]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--find", required=True, help="exported name, e.g. QUESTION_BANK")
    args = ap.parse_args()
    text = open(args.file, encoding="utf-8", errors="replace").read()
    val = find_binding(text, args.find)
    json.dump(val, sys.stdout, indent=2, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
