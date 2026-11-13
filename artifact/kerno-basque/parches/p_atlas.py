import sys; sys.path.insert(0, "/home/claude/w/patches")
from util import P
p = P(sys.argv[1])
p.rex(r'const LIGAS_INFO = \{ euroleague:.*?ligau: \["Liga U \(ACB, sub-22\)", "LU"\] \};',
      'const LIGAS_INFO = { esf_1nac: ["Primera Nacional", "1ª NAC"], esf_2nac: ["Segunda Nacional", "2ª NAC"], esf_jun: ["Junior · Liga Vasca", "JUN"], esf_cad: ["Cadete · Liga Vasca", "CAD"] };')
p.rep('let VARA = (() => { try { return localStorage.getItem("mm.vara") || "euroleague"; } catch (e) { return "euroleague"; } })(), VARAJ = null, VARAP = null;',
      'let VARA = (() => { try { const v = localStorage.getItem("kb.vara"); return v && /^esf_/.test(v) ? v : "esf_1nac"; } catch (e) { return "esf_1nac"; } })(), VARAJ = null, VARAP = null;   // Kerno Basque: la vara es siempre una liga vasca')
p.rep('function pintarTodo() { pintarResumen(); pintarEnts(); pintarComparacion(); buscar(); pintarLigas(); pintarTrayectoria(); pintarEstilos(); pintarHallazgos(); pintarModelo(); pintarSim(); pintarMapa(); pintarClavesQuimica(); pintarLectura(); }',
      'function pintarTodo() { [pintarResumen, pintarEnts, pintarComparacion, buscar, pintarLigas, pintarTrayectoria, pintarEstilos, pintarHallazgos, pintarModelo, pintarSim, pintarMapa, pintarClavesQuimica, pintarLectura].forEach((f) => { try { f(); } catch (e) { console.warn("Kerno Basque · sin", f.name, e && e.message); } }); }')
p.rep('''  SIMP = Promise.all(["simulador/meta.json", "simulador/jugadores.json", "simulador/clubes.json"].map((u) => cargarJSON(u))).then(([m, j, c]) => {''',
      '''  SIMP = Promise.reject(new Error("Kerno Basque no incluye el simulador")).then(([m, j, c]) => {''')
p.rep('}).catch((e) => { SIMD = { error: e.message }; console.error(e); if (!$("#p-simulador").hidden) pintarSim(); });', '}).catch((e) => { SIMD = { error: e.message }; if (!$("#p-simulador").hidden) try { pintarSim(); } catch (er) { /* */ } });')
p.rep('<script src="v40.js"></script>\n', '')
p.rep('<script src="v41/ecosistema.js"></script>\n', '')
p.guardar()
