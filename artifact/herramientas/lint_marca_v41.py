"""Verificación de marca Kerno de lo que añade la F4 de la v4.1 (bloqueantes automatizables de la skill cerno-brand §10).

El brand_lint.py oficial (Anexo D de los recursos de marca) no está en este entorno: este script reproduce los bloqueantes
que se pueden comprobar sobre texto en las líneas AÑADIDAS frente a la base publicada (commit de artifact/kerno/README.md):
  1 colores fuera de la paleta Kerno (o restos de Cerno: #12161B, #F3F0E8, #F2CC2F, #2A6FA8);
  4 glifos que las fuentes de marca no tienen (→ ← ▲ ■ ● ≥ ≤ № y emojis) en texto visible;
  6 expresiones vetadas (EN/ES), «Kerno AI», «Cerno» en texto nuevo.
Uso: python3 artifact/herramientas/lint_marca_v41.py [commit_base]
"""
from __future__ import annotations

import re
import subprocess
import sys

PALETA = {c.lower() for c in """#0F2E25 #F3F4F0 #0C1210 #B8975C #8A6B35 #D9C49B #FFFFFF #1D2723 #2B3631 #3F4B45 #56625C #707B75
#8F9993 #B2BAB5 #CFD5D0 #E3E7E2 #163B30 #1F4A3D #2C5C4C #7FA597 #DCE7E2 #2F7D3A #A86A12 #B3392E #2B6FBF #D35C2A #12997A
#6550CC #CC6390 #7F8418 #3A82D6 #D9662F #17A07D #7C6BDD #D46A99 #958C22 #E8EFEB #C9DBD2 #A3C2B5 #79A594 #4F8773 #2C6855
#1A4B3C #B04A20 #D9805A #EBC0A9 #B4C9E6 #6F9AD3""".split()}
CERNO = {"#12161b", "#f3f0e8", "#f2cc2f", "#2a6fa8"}
GLIFOS = re.compile("[→←▲■●≥≤№\U0001F300-\U0001FAFF☀-➿]")
VETADAS = re.compile(r"\b(revolutioni[sz]e|unlock|game-changing|cutting-edge|next-gen|predict the future|guaranteed|secret sauce|"
                     r"moneyball|superhuman|the best|magic|disrupt|revolucionar\w*|desbloquear|disruptiv\w*|de última generación|"
                     r"garantizad\w*|infalible|mágic\w*|sobrehuman\w*|predecir el futuro|salsa secreta)\b", re.I)


def lineas_anadidas(base: str) -> list[tuple[str, str]]:
    d = subprocess.run(["git", "diff", "-U0", base, "--", "artifact/kerno"], capture_output=True, text=True, check=True).stdout
    nuevas = subprocess.run(["git", "ls-files", "--others", "--exclude-standard", "artifact/kerno"], capture_output=True, text=True).stdout.split()
    out, f = [], None
    for ln in d.splitlines():
        if ln.startswith("+++ "):
            f = ln[6:]
        elif ln.startswith("+") and not ln.startswith("+++"):
            out.append((f, ln[1:]))
    for f in nuevas:
        out += [(f, x) for x in open(f, encoding="utf-8").read().splitlines()]
    return out


def main(base: str) -> int:
    errores = []
    for f, ln in lineas_anadidas(base):
        t = ln.strip()
        if t.startswith(("//", "/*", "*", "#")):
            continue                                         # comentarios: no se pintan
        for c in re.findall(r"#[0-9A-Fa-f]{6}\b", ln):
            if c.lower() in CERNO or c.lower() not in PALETA:
                errores.append((f, "color fuera de paleta", c, t[:100]))
        if GLIFOS.search(ln):
            errores.append((f, "glifo sin soporte en las fuentes de marca", GLIFOS.search(ln).group(), t[:100]))
        m = VETADAS.search(ln)
        if m:
            errores.append((f, "expresión vetada", m.group(), t[:100]))
        if re.search(r"Kerno ?AI", ln) or re.search(r"\bCerno\b(?!V40)", ln):
            errores.append((f, "nombre de marca", "Cerno/Kerno AI", t[:100]))
    for e in errores:
        print(" · ".join(e))
    print(f"bloqueantes: {len(errores)}")
    return 1 if errores else 0


if __name__ == "__main__":
    base = sys.argv[1] if len(sys.argv) > 1 else subprocess.run(["git", "log", "--format=%H", "-1", "--", "artifact/kerno/README.md"],
                                                                 capture_output=True, text=True).stdout.strip()
    sys.exit(main(base))
