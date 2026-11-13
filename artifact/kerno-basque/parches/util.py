import re, sys
class P:
    def __init__(self, path):
        self.path = path; self.s = open(path, encoding="utf-8").read(); self.n = 0
    def rep(self, old, new, count=1):
        c = self.s.count(old)
        if count is not None and c != count:
            raise SystemExit(f"[{self.path}] esperado {count}, hay {c}: {old[:120]!r}")
        if c == 0: raise SystemExit(f"[{self.path}] no está: {old[:120]!r}")
        self.s = self.s.replace(old, new); self.n += 1
    def rex(self, pat, new, count=1, flags=re.S):
        m = list(re.finditer(pat, self.s, flags))
        if count is not None and len(m) != count: raise SystemExit(f"[{self.path}] regex {len(m)} != {count}: {pat[:100]}")
        self.s = re.sub(pat, new, self.s, flags=flags); self.n += 1
    def func(self, name, code, prefix="function "):
        i = self.s.find(f"\n{prefix}{name}(")
        if i < 0: raise SystemExit(f"no hay función {name}")
        j = self.s.find("\n}\n", i + 1)
        self.s = self.s[:i + 1] + code.strip("\n") + self.s[j + 2:]; self.n += 1
    def guardar(self):
        open(self.path, "w", encoding="utf-8").write(self.s); print(self.path, self.n, "cambios")
