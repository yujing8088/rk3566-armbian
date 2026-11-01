#!/usr/bin/env python3
"""极简 C 预处理器：只为编译 DTS 服务 (去注释 / #include / #define / 条件编译)"""
import os, re, sys

def strip_comments(txt):
    out = []
    i, n = 0, len(txt)
    while i < n:
        c = txt[i]
        if c == '"':
            j = i + 1
            while j < n:
                if txt[j] == '\\':
                    j += 2; continue
                if txt[j] == '"':
                    j += 1; break
                j += 1
            out.append(txt[i:j]); i = j; continue
        if txt.startswith('/*', i):
            j = txt.find('*/', i + 2)
            j = n if j < 0 else j + 2
            out.append("\n" * txt.count("\n", i, j))
            i = j; continue
        if txt.startswith('//', i):
            j = txt.find('\n', i)
            j = n if j < 0 else j
            out.append(" "); i = j; continue
        out.append(c); i += 1
    return "".join(out)

class PP:
    def __init__(self, incdirs):
        self.incdirs = incdirs
        self.macros = {}
        self.done = set()

    def find(self, name, curdir):
        cands = [os.path.join(curdir, name)] + [os.path.join(d, name) for d in self.incdirs]
        for c in cands:
            if os.path.isfile(c):
                return c
        return None

    def expand(self, line):
        if not self.macros:
            return line
        def rep(m):
            return self.macros.get(m.group(0), m.group(0))
        parts = re.split(r'("(?:[^"\\]|\\.)*")', line)
        for k in range(0, len(parts), 2):
            parts[k] = re.sub(r'[A-Za-z_][A-Za-z0-9_]*', rep, parts[k])
        return "".join(parts)

    def process(self, path):
        path = os.path.abspath(path)
        curdir = os.path.dirname(path)
        txt = strip_comments(open(path, encoding="utf-8", errors="replace").read())
        res = []
        for line in txt.split("\n"):
            m = re.match(r'\s*#\s*(\w+)\s*(.*)$', line)
            if m and m.group(1) in ("include", "define", "undef", "if", "ifdef",
                                    "ifndef", "elif", "else", "endif", "pragma",
                                    "error", "warning", "line"):
                d, rest = m.group(1), m.group(2).strip()
                if d == "include":
                    mm = re.match(r'[<"]([^">]+)[">]', rest)
                    if mm:
                        name = mm.group(1)
                        p = self.find(name, curdir)
                        if p and p not in self.done:
                            self.done.add(p)
                            res.append(self.process(p))
                        elif not p:
                            res.append("\n")
                    continue
                if d == "define":
                    mm = re.match(r'([A-Za-z_][A-Za-z0-9_]*)(\([^)]*\))?\s*(.*)$', rest)
                    if mm:
                        self.macros[mm.group(1)] = mm.group(3).strip()
                    continue
                if d == "undef":
                    for w in rest.split():
                        self.macros.pop(w, None)
                    continue
                continue  # ifdef/ifndef/endif/pragma/pass-through
            res.append(self.expand(line))
        return "\n".join(res)

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    incdirs = []
    for i, a in enumerate(sys.argv):
        if a == "-I" and i + 1 < len(sys.argv):
            incdirs.append(sys.argv[i + 1])
    pp = PP(incdirs)
    txt = pp.process(src)
    open(dst, "w", encoding="utf-8").write(txt)
    print(f"preprocessed -> {os.path.basename(dst)} ({len(txt.splitlines())} lines, {len(pp.macros)} macros)")
