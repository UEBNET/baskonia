"""Ensambla index.html de Kerno Basque Analytics: _cabeza + _estilo.css + _markup + _app.js."""
from pathlib import Path
d = Path(__file__).parent
html = (d / "_cabeza.html").read_text() + "\n<style>\n" + (d / "_estilo.css").read_text() + "\n</style>\n" \
     + (d / "_markup.html").read_text() + "\n<script>\n" + (d / "_app.js").read_text() + "\n</script>\n<script id=\"kerno-upd-js\">\n" + (d / "_upd.js").read_text() + "</script>\n</body></html>\n"
(d / "index.html").write_text(html)
print(f"index.html {len(html) / 1024:.0f} KB")
