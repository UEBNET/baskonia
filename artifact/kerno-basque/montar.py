"""Monta el sitio publicable de Kerno Basque Analytics en publicacion/kerno-basque/ y escribe la lista de ficheros.

    python -m bbstats.esf artifact && python -m bbstats.esf kerno && python artifact/kerno-basque/montar.py

Código (versionado): artifact/kerno-basque/sitio/{index.html, federacion.html, quintetos/, atlas/, kerno/}
  - index.html se ensambla con sitio/_build.py (_cabeza + _estilo.css + _markup + _app.js + _upd.js).
  - quintetos/ y atlas/ son las páginas del sitio general «Kerno Analytics · Equipos» con los parches de parches/.
Datos (no versionados): data/basko/artifact/datos (vista Federación Vasca) y data/basko/artifact/sitio (kerno.py).
Salida: publicacion/kerno-basque/ + publicacion/kerno-basque.json = [{"as": ruta servida, "path": fichero local}].
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
SITIO = RAIZ / "artifact" / "kerno-basque" / "sitio"
OUT = RAIZ / "publicacion" / "kerno-basque"

subprocess.run([sys.executable, str(SITIO / "_build.py")], check=True)
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
for n in ("index.html", "federacion.html"):
    shutil.copy2(SITIO / n, OUT / n)
for d in ("quintetos", "atlas", "kerno"):
    shutil.copytree(SITIO / d, OUT / d, dirs_exist_ok=True)
shutil.copytree(RAIZ / "data" / "basko" / "artifact" / "datos", OUT / "datos", dirs_exist_ok=True)
shutil.copytree(RAIZ / "data" / "basko" / "artifact" / "sitio", OUT, dirs_exist_ok=True)
fs = sorted((p for p in OUT.rglob("*") if p.is_file()), key=lambda p: (p.name != "index.html" or p.parent != OUT, str(p)))
lista = [{"as": p.relative_to(OUT).as_posix(), "path": str(p)} for p in fs]
(OUT.parent / "kerno-basque.json").write_text(json.dumps(lista, ensure_ascii=False, indent=0))
print(f"{len(lista)} ficheros en {OUT} ({sum(p.stat().st_size for p in fs) / 2**20:.1f} MiB)")
