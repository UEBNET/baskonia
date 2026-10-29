# Arnés de prueba de la lectura de fichaje (informe v3.x del Atlas).
# Sirve una copia local del artifact publicado (carpeta con index.html, atlas/, quintetos/datos/equipos, cerno/fonts),
# genera la lectura de un jugador de 2025-26 hacia Baskonia 2026-27 y comprueba que ninguna hoja A4 se desborda.
# Uso (Python 3.11+ con playwright y Chromium):
#   python3 artifact/herramientas/prueba_informe.py <carpeta_copia> <salida> "jabari+parker+joventut" [1|0] ['{"fuera":[...],"extra":[...]}']
# Salida: margen libre por hoja (negativo = desborde), PDF por la ruta del botón «Descargar PDF», capturas por hoja,
# texto del informe y estado del selector de compañeros. Los argumentos 3-5 son: jugador, con destino (1) o sin él (0)
# y la plantilla elegida (personas a quitar y fichas del simulador a añadir).
import asyncio, sys, subprocess, time, os, json
from playwright.async_api import async_playwright

SITE = os.path.abspath(sys.argv[1])
OUT = sys.argv[2] if len(sys.argv) > 2 else "salida_informe"
JUG = sys.argv[3] if len(sys.argv) > 3 else "jabari+parker+joventut"
SIM = (sys.argv[4] if len(sys.argv) > 4 else "1") == "1"
PLANT = sys.argv[5] if len(sys.argv) > 5 else ''
os.makedirs(OUT, exist_ok=True)

JS_SETUP = """async ([jug, sim, plant]) => {
  const j = JG.filter(x => x.temporada === '2025-26' && jug.toLowerCase().split('+').every(w => (x.nombre + ' ' + x.nombre_club).toLowerCase().includes(w))).sort((a,b)=>b.min-a.min)[0];
  if (!j) return 'sin jugador';
  const c = BY.get(j.clave);
  const al = META.clubes_con_nombre.baskonia, k = al.claves.find(x => x.startsWith('euroleague:'));
  st.inf = { temp: j.temporada, liga: j.liga, club: c.clave_club, jug: jKey(j), sim, dTemp: '2026-27', dLiga: 'euroleague', dClub: k, rol: 'ROTACION' };
  st.inf.rolDe = `${st.inf.jug}→${sim ? k + ':2026-27' : '-'}`;
  if (plant) { await cargarSim(); const P = JSON.parse(plant); st.inf.plant = {}; st.inf.plant[k + ':2026-27'] = P; }
  const nota = 'Proponemos a Jabari Parker para el rol de rotación en el Baskonia, con una adaptación y un Índice Fit elevados en la simulación, en la que se le asignan ~18 minutos por partido. Pesa a su favor una amplia trayectoria al más alto nivel y un recorrido contrastado en la Euroliga. Su aportación concreta es el cuidado del balón, una de las carencias que hoy presenta el equipo.\\n\\nNo mejora las carencias más evidentes del club en defensa ni en rebote, y su nivel actual queda por debajo del habitual en la Euroliga para su puesto.';
  try { const o = {}; o[st.inf.rolDe] = { raw: nota, fin: nota }; localStorage.setItem('cerno.informe.v3', JSON.stringify(o)); } catch(e) {}

  const tb = document.querySelector('#t-informe'); if (tb) tb.click();
  construirInforme(); ifControles(); await pintarInforme();
  return j.nombre + ' · ' + c.nombre_club;
}"""

async def main():
    srv = subprocess.Popen([sys.executable, "-m", "http.server", "8765", "-d", SITE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    try:
        async with async_playwright() as p:
            b = await p.chromium.launch()
            pg = await b.new_page(viewport={"width": 1440, "height": 1000})
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.on("console", lambda m: errs.append("console: " + m.text) if m.type == "error" else None)
            await pg.goto("http://localhost:8765/atlas/index.html", wait_until="load")
            await pg.wait_for_function("typeof META !== 'undefined' && META && typeof JG !== 'undefined' && JG.length > 0", timeout=180000)
            r = await pg.evaluate(JS_SETUP, [JUG, SIM, PLANT])
            print("jugador:", r)
            await pg.wait_for_function("document.querySelectorAll('#ifPages .ifsheet').length > 3 && !document.querySelector('#ifPages').classList.contains('cargando')", timeout=180000)
            await pg.wait_for_timeout(1500)
            info = await pg.evaluate("""() => [...document.querySelectorAll('#ifPages .ifsheet')].map((s, i) => {
              const b = s.querySelector('.ifbody'); const r = b.getBoundingClientRect(); let mx = 0; b.querySelectorAll('*').forEach(e => { const q = e.getBoundingClientRect(); if (q.height > 0) mx = Math.max(mx, q.bottom); }); return { i, libre: Math.round(r.bottom - mx) }; })""")
            print(json.dumps(info))
            html = await pg.evaluate("async () => { await ifFuentes(); return ifHtmlImprimible(); }")
            b64 = await pg.evaluate("async () => { const blob = await ifGenerarPdf(document.querySelector('#ifMsg')); const buf = new Uint8Array(await blob.arrayBuffer()); let s = ''; for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000)); return btoa(s); }")
            import base64; open(f"{OUT}/informe.pdf", "wb").write(base64.b64decode(b64))
            open(f"{SITE}/atlas/_imprimible.html", "w").write(html)
            p2 = await b.new_page(viewport={"width": 900, "height": 1200}, device_scale_factor=1.5)
            await p2.goto("http://localhost:8765/atlas/_imprimible.html", wait_until="load")
            await p2.wait_for_timeout(1500)
            info2 = await p2.evaluate("""() => [...document.querySelectorAll('.ifsheet')].map((s, i) => { const b = s.querySelector('.ifbody'); const r = b.getBoundingClientRect(); let mx = 0; b.querySelectorAll('*').forEach(e => { const q = e.getBoundingClientRect(); if (q.height > 0) mx = Math.max(mx, q.bottom); }); return Math.round(r.bottom - mx); })""")
            print("libre (imprimible):", info2)
            sheets = await p2.query_selector_all(".ifsheet")
            for i, sh in enumerate(sheets):
                await sh.screenshot(path=f"{OUT}/p{i+1:02d}.png")
            txt = await pg.evaluate("() => document.querySelector('#ifPages').innerText")
            open(f"{OUT}/texto.txt", "w").write(txt)
            ui = await pg.evaluate("() => { const b = document.querySelector('#ifPlantBox'); return b && !b.hidden ? b.querySelector('.label').textContent + ' | ' + [...b.querySelectorAll('label.off span, .add span')].map(x => x.textContent).join(' ; ') : 'oculto'; }")
            print("plantilla UI:", ui)
            print("errores:", [e for e in errs if 'plotly' not in e.lower()][:20])
            await b.close()
    finally:
        srv.terminate()

asyncio.run(main())
