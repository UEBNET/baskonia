import sys; sys.path.insert(0, "/home/claude/w/patches")
from util import P
p = P(sys.argv[1])
# --- ligas vascas (nombres, abreviaturas, orden)
p.rex(r'const LIGAS_INFO = \{ euroleague:.*?ligau: \["Liga U \(ACB, sub-22\)", "LU"\] \};',
      'const LIGAS_INFO = { esf_1nac: ["Primera Nacional", "1ª NAC"], esf_2nac: ["Segunda Nacional", "2ª NAC"], esf_jun: ["Junior · Liga Vasca", "JUN"], esf_cad: ["Cadete · Liga Vasca", "CAD"] };')
p.rep('referencia: "euroleague", factor: 2, familias: {', 'referencia: "su liga", factor: 2, familias: {')
p.rep('unidad: "pts/100 (vara Euroliga)", dt: 1.2426', 'unidad: "pts/100 en su liga", dt: 1.2426')
p.rep('unidad: "pts/100 (vara Euroliga)", dt: 0.8334', 'unidad: "pts/100 en su liga", dt: 0.8334')
p.rep('unidad: "pts/100 (vara Euroliga)", dt: 0.6745', 'unidad: "pts/100 en su liga", dt: 0.6745')
p.rep('lab = hk ? HR.lab() : "Euroliga", donde = hk ? HR.donde() : "en la Euroliga";', 'lab = hk ? HR.lab() : "media de su liga", donde = hk ? HR.donde() : "en las ligas vascas";')
p.rep('if (!c || c.tipo === "euroleague") return "Euroliga";', 'if (!c || c.tipo === "euroleague") return "media de su liga";')
p.rep('return !c || c.tipo === "euroleague" ? "la Euroliga" : "la " + ESC.ligaNom(c.liga);', 'return !c || c.tipo === "euroleague" ? "las ligas vascas" : "la " + ESC.ligaNom(c.liga);')
# --- los seis estilos (taxonomía unificada) también donde la página mostraba los perfiles del mapa
p.rex(r'const ESTILOS = \{\n  E01:.*?\n\};', '''const ESTILOS = { // Kerno Basque: los seis estilos del sitio general (taxonomía unificada), en el orden de EU_IDS
  E01: ["Pistons", "Intensidad física: robos, faltas, ataque al aro y rebote ofensivo, con triple de esquina; poco balón en las manos."],
  E02: ["Isolation", "Muchas canastas sin asistencia y mucho balón en las manos; más pérdidas, poco rebote ofensivo."],
  E03: ["Old-School", "Juego interior clásico: rebote ofensivo, tiros cerca del aro y tapones; poco triple y poco pase."],
  E04: ["Spacing", "Tiro exterior: mucho triple, sobre todo de esquina, casi siempre tras pase; poco aro y pocos tiros libres."],
  E05: ["Circulación", "Juego de pase lejos del aro: triple y asistencias; poco rebote ofensivo, pocos tapones y pocos tiros en el aro."],
  E06: ["Pintura", "Juego en la pintura: casi ningún triple, muchos tiros en el aro y tiros libres, rebote ofensivo, tapones y faltas."],
};''')
# --- liga por defecto y equipos
p.rep('const S = { tab: "equipo", t: null, l: "euroleague", f: "regular"', 'const S = { tab: "equipo", t: null, l: "esf_1nac", f: "regular"')
p.rep('const l = S.l || "euroleague";', 'const l = S.l || "esf_1nac";')
p.rep('if (!LIGAS.includes(S.l) && !(IDX.temporadas[S.t] || {})[S.l]) S.l = "euroleague";', 'if (!LIGAS.includes(S.l) && !(IDX.temporadas[S.t] || {})[S.l]) S.l = "esf_1nac";')
p.rep('return x && x.cobertura && x.cobertura.partidos >= 150; }) || ts[0];', 'return x && x.cobertura && x.cobertura.partidos >= 100; }) || ts[0];')
p.rep('Object.values(IDX.temporadas[t]).every((x) => !x.cobertura || x.cobertura.partidos < 150)', 'Object.values(IDX.temporadas[t]).every((x) => !x.cobertura || x.cobertura.partidos < 100)')
# --- sin modelos multiliga (v4.0, v4.2): la página no los pide
p.rep('if (!V4QP) V4QP = Promise.all([bajarJSON("../atlas/v40/jugadores_v40.json.gz.txt"), bajarJSON("../atlas/v40/mapa_personas.json.gz.txt")]).catch((e) => { console.error("v4.0:", e); return null; });',
      'if (!V4QP) V4QP = Promise.resolve(null);   // Kerno Basque: sin modelo multiliga v4.0')
p.rep('if (!V42IP) V42IP = bajarJSON("datos_v42/indice.json").catch(() => null);', 'if (!V42IP) V42IP = Promise.resolve(null);   // Kerno Basque: sin estimación v4.2')
p.rep('EVP = Promise.all([bajarJSON("datos/equipos.gz.txt"), cargarEUC(), bajarJSON("../atlas/v40/clubes_v40.json.gz.txt").catch(() => null)]).then(([raw, , v4]) => {',
      'EVP = Promise.all([bajarJSON("datos/equipos.gz.txt"), cargarEUC(), Promise.resolve(null)]).then(([raw, , v4]) => {')
# --- textos de cabecera y escala
p.rep('(50 = la media; los cambios, en puntos de esa escala con signo; la vara es la Euroliga)', '(50 = la media de su liga; los cambios, en puntos de esa escala con signo; la vara es la dispersión en las ligas vascas)')
p.rep('o unidad media (net, sinergia), con la dispersión de la Euroliga como vara.', 'o unidad media (net, sinergia), con la dispersión en las ligas vascas como vara.')
p.rep('(50 = equipo medio; la vara es la dispersión de los equipos de la Euroliga)', '(50 = equipo medio de su liga; la vara es la dispersión de los equipos de las ligas vascas)')
p.rep('["L", "Nivel", "Nivel del jugador (índice L en la vara EuroLeague), escala 0–100: 50 = jugador medio de su liga en la temporada", 2],',
      '["L", "Nivel Kerno", "Nivel Kerno del jugador (producción e impacto en su liga), escala 0–100: 50 = jugador medio de su liga en la temporada", 2],')
p.rep('[["rapm_el", "RAPM proyectado", "RAPM proyectado: RAPM multiliga con prior del perfil; 50 = jugador medio de la EuroLeague", "rapm"], ["orapm_el", "ORAPM proyectado", "Parte ofensiva del RAPM proyectado (reparto del RAPM anterior)", "orapm"], ["drapm_el", "DRAPM proyectado", "Parte defensiva del RAPM proyectado (más de 50 = mejor)", "drapm"]]',
      '[["rapm_el", "RAPM", "RAPM del jugada a jugada en su liga; 50 = jugador medio de su liga", "rapm"], ["orapm_el", "ORAPM", "Parte ofensiva del RAPM", "orapm"], ["drapm_el", "DRAPM", "Parte defensiva del RAPM (más de 50 = mejor)", "drapm"]]')
p.rep('El <b>nivel</b> (L) resume la calidad del jugador en la vara de la EuroLeague;', 'El <b>Nivel Kerno</b> resume la producción y el impacto del jugador frente a su liga;')
p.rep('El RAPM está en <b>unidades de su liga</b>: +3 en la ACB no equivale a +3 en la NBA (para comparar entre ligas usa el «RAPM proyectado» de la pestaña Jugadores, traducido a la Euroliga). La escala 0–100 (50 = jugador medio) usa como vara la dispersión del RAPM en la Euroliga;',
      'El RAPM está en <b>unidades de su liga</b>: +3 en Primera Nacional no equivale a +3 en Cadete (no hay puente de normalización entre ligas vascas). La escala 0–100 (50 = jugador medio de su liga) usa como vara la dispersión del RAPM en las ligas vascas;')
p.rep('50 es la media; la vara es la dispersión de esa cifra en la Euroliga, así que 73 es una desviación típica por encima (27, una por debajo) y 88, dos.',
      '50 es la media de su liga; la vara es la dispersión de esa cifra en las ligas vascas, así que 73 es una desviación típica por encima (27, una por debajo) y 88, dos.')
p.rep('El nivel (L) usa la Euroliga de esa temporada como 50, de modo que las medias de las ligas se leen directamente.', 'El Nivel Kerno se mide dentro de cada liga vasca y temporada: 50 = jugador medio de su liga.')
p.rep('Junto a cada cifra, su percentil en la Euroliga.', 'Junto a cada cifra, su percentil en su liga.')
# --- Evaluación: KPIs, lectura y nivel sin Euroliga ni v4.0
p.rep('''    kp("Net v4.0 de su liga", v4Html(v4Liga(l, t)), ok(v4Liga(l, t)) ? `pts/100 frente a la Euroliga ${esc(t)}` : "sin dato",
      `<b>Net v4.0 de la liga</b>: media del valor de sus plantillas (Σ minutos × RAPM proyectado de cada jugador) frente a la de la Euroliga ${esc(t)}, en puntos por 100 posesiones.`) +
    kp("Net v4.0 de la plantilla", v4Html(r.v4 && r.v4[1]), r.v4 ? `pts/100 · ${ord(r.v4[2])} de ${r.v4[3]} en su liga` : "sin dato",
      `<b>Net v4.0 de la plantilla</b>: Σ minutos × RAPM proyectado (RAPM multiliga con prior del perfil) de sus jugadores, frente al club medio de ${esc(LNOM[l] || l)} ${esc(t)}, en puntos por 100 posesiones (modelo v4.0, capa aditiva).`) +''',
'''    kp("Nivel Kerno de la plantilla", evNiv(L), rkPl ? `${ord(rkPl)} de ${nPl} plantillas de su liga` : "sin dato",
      `<b>Nivel Kerno de la plantilla</b>: media del Nivel Kerno de sus jugadores (100+ minutos), ponderada por minutos, frente al club medio de ${esc(LNOM[l] || l)} ${esc(t)} (= 50). El Nivel Kerno de cada jugador combina producción (PER, Win Shares, Game Score y PIE por 40 minutos) e impacto (RAPM y on/off ajustado) frente a su liga.`) +
    kp("División", esc((club && club.division) || "–"), (club && club.club_nombre) ? esc(club.club_nombre) : "", "<b>División</b> en la que ha jugado la mayor parte de sus partidos (Junior y Cadete: A1 o A2; senior: única). La evaluación compara con todos los equipos de su liga.") +''')
p.rep('''${l !== "euroleague" && rkEL ? ` y, por nivel, sería la ${ord(rkEL)} de ${el_.length + 1} plantillas de la Euroliga` : ""}.`); }''', '''.`); }''')
p.rep('${aprende("Todas las cifras de nivel están en la escala 0–100 con la <b>Euroliga como 50</b>: el nivel de la liga dice cuánto vale competir allí y el de la plantilla, cuánto valen sus jugadores, en la misma vara. Las cifras de rendimiento (Net, factores) se miden <b>dentro de su liga</b>; para compararlas entre ligas, léelas junto al nivel de la liga. Pasa el ratón por cualquier cifra para ver su valor original.", "escalas")}',
      '${aprende("Todas las cifras están en la escala 0–100 con la <b>media de su liga como 50</b>: el Nivel Kerno de la plantilla dice cuánto valen sus jugadores frente a los de su liga, y las cifras de rendimiento (Net, factores) se miden también <b>dentro de su liga</b>. Entre ligas vascas no hay puente de normalización: un 60 en Cadete no es un 60 en Primera Nacional. Pasa el ratón por cualquier cifra para ver su valor original.", "escalas")}')
p.rep('<h2>Nivel: la liga y la plantilla, con la Euroliga como 50</h2>', '<h2>Nivel Kerno: las plantillas de su liga, con el club medio como 50</h2>')
p.rep('${aprende("Arriba, la media de cada liga; en el centro, las plantillas de los equipos de su liga; abajo, las de la Euroliga como referencia. El equipo elegido va con su punto en latón. Un equipo de una liga más floja puede tener plantilla de Euroliga: es lo que hay que mirar al fichar o al comparar rivales.")}',
      '${aprende("Cada punto es la plantilla de un equipo de su liga (Nivel Kerno medio de sus jugadores, ponderado por minutos); debajo, los jugadores de la plantilla elegida. El equipo elegido va en latón.")}')
p.rep('[["liga", `Su liga`], ["el", "Su liga + Euroliga"], ["todas", "Todas las ligas"]]', '[["liga", `Su liga`], ["todas", "Todas las ligas vascas"]]')
p.rep('<span class="note">temporada regular · 100+ minutos · nivel L en la escala 0–100 (50 = jugador medio de su liga)</span>', '<span class="note">toda la temporada · 100+ minutos · Nivel Kerno en la escala 0–100 (50 = jugador medio de su liga)</span>')
p.rep('${aprende("El gráfico cruza lo que vale la plantilla (horizontal, comparable entre ligas) con lo que gana (vertical, dentro de su liga). Por encima de la nube de su liga: equipos que rinden más de lo que sus jugadores prometen. Clic en un equipo para evaluarlo.")}',
      '${aprende("El gráfico cruza lo que vale la plantilla (horizontal: Nivel Kerno de la plantilla frente al club medio de su liga) con lo que gana (vertical). Por encima de la nube: equipos que rinden más de lo que sus jugadores prometen. Clic en un equipo para evaluarlo.")}')
# tira de nivel: plantillas de su liga y jugadores de la plantilla elegida
p.func("evPintarStrip", r'''
function evPintarStrip(t, l, id, r, lg) {
  const box = $("#evStrip"); if (!box) return;
  const W = ancho(box), m = { l: 150, r: 20 }, pw = W - m.l - m.r, XU = (u) => m.l + (clamp(u, 0, 100) / 100) * pw, X = (s) => XU(ESC.U(s));   // eje en la escala 0–100
  const pl = EV.P[r.k];
  const filas = [[`Plantillas ${ESC.ligaCorto(l)} (club medio = 50)`, lg.filter((x) => ok(x.L)).map((x) => ({ s: nS("nivel", x.L), col: ESC.ligaCol(l), me: x.id === id, act: `${x.liga}|${x.id}`, tip: `<b>${esc(x.eq)}</b><br>Nivel Kerno de la plantilla: ${ESC.txt(nS("nivel", x.L))} · ${evWL(x)}` }))]];
  if (pl && pl.j && pl.j.length) filas.push([`Jugadores (jugador medio = 50)`, pl.j.filter((j) => ok(j[4])).map((j) => ({ s: enJugEV(l, t, () => nS("nivel", j[4])), col: "var(--e4)", lab: nombreBonito(j[0]).sur, tip: `<b>${esc(nombreBonito(j[0]).full)}</b><br>Nivel Kerno: ${enJugEV(l, t, () => ESC.txt(nS("nivel", j[4])))} · ${fi(j[3])} min` }))]);
  const rh = 56, H = filas.length * rh + 30;
  let g = "";
  [0, 25, 50, 75, 100].forEach((v) => { g += `<line class="grid" x1="${XU(v)}" y1="8" x2="${XU(v)}" y2="${H - 22}" ${v === 50 ? 'stroke="var(--faint)" stroke-width="1.5"' : ""}/><text class="ax" x="${XU(v)}" y="${H - 6}" text-anchor="${v === 0 ? "start" : v === 100 ? "end" : "middle"}">${v === 50 ? "50 = media de la fila" : v}</text>`; });
  filas.forEach(([lab, pts], i) => {
    const y = 24 + i * rh;
    g += `<text class="lab" x="${m.l - 10}" y="${y + 4}" text-anchor="end" font-size="11.5" fill="var(--muted)">${esc(lab)}</text><line x1="${m.l}" x2="${m.l + pw}" y1="${y}" y2="${y}" stroke="var(--line)" stroke-dasharray="2 3"/>`;
    const conLab = pts.filter((p) => p.lab).sort((a, b) => X(a.s) - X(b.s));
    const pos = new Map(); const ocup = [[], []];
    conLab.forEach((p) => { const cx = X(p.s), w = p.lab.length * 6.2 + 6; for (const c of [0, 1]) { if (!ocup[c].some(([a, b]) => cx - w / 2 < b && cx + w / 2 > a)) { ocup[c].push([cx - w / 2, cx + w / 2]); pos.set(p, c); break; } } });
    pts.slice().sort((a, b) => (a.me || 0) - (b.me || 0)).forEach((p) => {
      const cx = X(p.s), c = pos.get(p);
      g += `<g ${p.act ? `class="hit" data-a="ev" data-v="${esc(p.act)}" role="button" tabindex="0"` : ""} ${tipA(p.tip)}><circle cx="${cx}" cy="${y}" r="${p.me ? 8 : 5}" fill="${p.me ? "var(--sim)" : p.col}" fill-opacity="${p.me ? 1 : 0.7}" stroke="${p.me ? "var(--ink)" : "var(--surface)"}" stroke-width="1.5"/>${p.lab && c != null ? `<text class="lab" x="${cx}" y="${c === 0 ? y - 11 : y + 19}" text-anchor="middle" font-size="10" fill="var(--muted)">${esc(p.lab)}</text>` : ""}</g>`;
    });
  });
  box.innerHTML = `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Nivel Kerno de las plantillas de su liga (club medio = 50) y de los jugadores de la plantilla, escala 0–100">${g}</svg>`;
}
''')
p.rep('box.innerHTML = `<div class="kv"><div><span>Net v4.0 de la plantilla</span><b>${v4Html(v4Net(k))}</b></div><div ${tipA("Los cinco jugadores con más minutos · nivel de caja")}><span>Nivel caja · 5 que más juegan</span><b>${evNiv(nivDe(top5))}</b></div><div><span>Nivel caja · resto</span><b>${evNiv(nivDe(banq))}</b></div>',
      'box.innerHTML = `<div class="kv"><div><span>Nivel Kerno de la plantilla</span><b>${enClubEV(S.l, S.t, () => evNiv(pl.L))}</b></div><div ${tipA("Los cinco jugadores con más minutos")}><span>Nivel Kerno · 5 que más juegan</span><b>${enJugEV(S.l, S.t, () => evNiv(nivDe(top5)))}</b></div><div><span>Nivel Kerno · resto</span><b>${enJugEV(S.l, S.t, () => evNiv(nivDe(banq)))}</b></div>')
p.rep('<div><span>Jugadores (100\'+)</span><b>${fi(pl.n)}</b></div><div ${tipA("Media ponderada por minutos")}><span>Edad media</span><b>${f(pl.edad, 1)}</b></div>',
      '<div><span>Jugadores (100\'+)</span><b>${fi(pl.n)}</b></div>')
p.rep('<th ${tipA("Nivel de caja (L) del jugador en la escala 0–100 (50 = jugador medio de su liga). No es el Nivel Kerno de la v4.0.")}>Nivel caja</th>', '<th ${tipA("Nivel Kerno del jugador en la escala 0–100 (50 = jugador medio de su liga): producción e impacto frente a su liga.")}>Nivel Kerno</th>')
p.rep('<thead><tr><th class="txt sticky">Jugador</th><th class="txt">Pos.</th><th>Edad</th><th>Min</th>', '<thead><tr><th class="txt sticky">Jugador</th><th class="txt" ${tipA("Posición estimada con su perfil estadístico (la Federación no la publica)")}>Pos.</th><th>Min</th>')
p.rep('<td class="txt">${esc(POSN[j[1]] || "–")}</td><td>${ok(j[2]) ? fi(j[2]) : "–"}</td><td>${fi(j[3])}</td>', '<td class="txt">${esc(POSN[j[1]] || "–")}</td><td>${fi(j[3])}</td>')
# todos los equipos: Nivel Kerno de la plantilla en lugar del Net v4.0
p.rep('let rows = EV.F.filter((x) => x.t === t && x.f === fz && (amb === "todas" || x.liga === l || (amb === "el" && x.liga === "euroleague")));', 'let rows = EV.F.filter((x) => x.t === t && x.f === fz && (amb === "todas" || x.liga === l));')
p.rep('const pts = rows.filter((x) => x.v4 && ok(x.wp));', 'const nsxK = (x) => enClubEV(x.liga, x.t, () => ESC.U(nS("nivel", x.L))), pts = rows.filter((x) => ok(x.L) && ok(x.wp));')
p.rep('const nsx = (x) => x.v4[1], sx = pts.map(nsx); let x0 = Math.min(...sx, -2), x1 = Math.max(...sx, 2);', 'const nsx = nsxK, sx = pts.map(nsx); let x0 = Math.min(...sx, 45), x1 = Math.max(...sx, 55);')
p.rep('text-anchor="middle">${v === 0 ? "EL = 0" : (v > 0 ? "+" : "−") + Math.abs(v)}</text>`;', 'text-anchor="middle">${v === 50 ? "50" : v}</text>`;')
p.rep('${v === 0 ? \'stroke="var(--faint)" stroke-width="1.5"\' : ""}/><text class="ax" x="${X(v)}" y="${H - 22}"', '${v === 50 ? \'stroke="var(--faint)" stroke-width="1.5"\' : ""}/><text class="ax" x="${X(v)}" y="${H - 22}"')
p.rep('text-anchor="end">Net v4.0 de la plantilla, pts/100 (club medio de su liga = 0)</text>', 'text-anchor="end">Nivel Kerno de la plantilla (club medio de su liga = 50)</text>')
p.rep('<br>Net v4.0 ${fs(nsx(x), 1)} · ${evWL(x)}', '<br>Nivel Kerno de la plantilla ${f(nsx(x), 0)} · ${evWL(x)}')
p.rep('aria-label="Net v4.0 de la plantilla frente a % de victorias"', 'aria-label="Nivel Kerno de la plantilla frente a % de victorias"')
p.rep('''    { k: "Lliga", l: "Net liga", get: (x) => v4Liga(x.liga, t), fmt: (v) => v4Html(v), tip: "Net v4.0 de la liga: pts/100 frente a la Euroliga de esa temporada" },
    { k: "SL", l: "Net v4.0", get: (x) => (x.v4 ? x.v4[1] : null), fmt: (v, x) => (ok(v) ? `${v4Html(v)} <span class="muted">${x.v4[2]}.º</span>` : "–"), tip: "Net v4.0 de la plantilla: pts/100 frente al club medio de su liga (Σ minutos × RAPM proyectado)." },''',
'''    { k: "div", l: "Div.", txt: true, get: (x) => ((EV.C[x.k] || {}).division || ""), fmt: (v) => esc(v || "–"), tip: "División (Junior y Cadete: A1 o A2)" },
    { k: "SL", l: "Nivel Kerno", get: (x) => (ok(x.L) ? nsxK(x) : null), fmt: (v) => (ok(v) ? `<b>${f(v, 0)}</b>` : "–"), tip: "Nivel Kerno de la plantilla: 50 = club medio de su liga (media del Nivel Kerno de sus jugadores, ponderada por minutos)." },''')
p.rep('(rows.some((x) => x.wl === "entrenadores_con_playoffs") ? `<p class="note">* Euroliga y EuroCup: la fuente oficial no publica el balance por fases; se suma el de sus entrenadores, que incluye los playoffs.</p>` : "");', '"";')
p.func("evPintarHist", r'''
function evPintarHist(club, r) {
  const box = $("#evHist"); if (!box) return;
  const cc = club && club.club;
  if (!cc) { box.innerHTML = `<p class="note">Sin historial.</p>`; return; }
  const filas = EV.F.filter((x) => x.f === "regular" && EV.C[x.k] && EV.C[x.k].club === cc).sort((a, b) => a.t.localeCompare(b.t));
  if (filas.length < 2) { box.innerHTML = `<p class="note">Solo hay una temporada de este equipo con jugada a jugada (desde 2022-23).</p>`; return; }
  box.innerHTML = `<div class="tablebox flat"><table aria-label="Evolución del club"><thead><tr><th class="txt sticky">Temporada</th><th ${tipA("Nivel Kerno de la plantilla frente al club medio de su liga esa temporada (= 50)")}>Nivel Kerno</th><th>Div.</th><th>Balance</th><th>Net</th><th class="txt">Entrenador</th><th class="txt">Estilo</th></tr></thead><tbody>` +
    filas.map((x) => { const c = EV.C[x.k];
      return `<tr class="${x.t === r.t ? "sel" : ""}"><td class="txt name sticky">${esc(x.t)}${c.prov ? " <small class=\"muted\">(en curso)</small>" : ""}</td><td>${ok(x.L) ? enClubEV(x.liga, x.t, () => evNiv(x.L)) : "–"}</td><td>${esc(c.division || "–")}</td><td>${evWL(x)}${ok(x.wp) ? ` <span class="muted">${f(x.wp, 0)} %</span>` : ""}</td><td>${fs(x.net)}</td><td class="txt">${esc((c.ent || []).map((e) => e.n).join(" → ") || "–")}</td><td class="txt">${euSpan(evU(x.k), true)}</td></tr>`; }).join("") +
    `</tbody></table></div><p class="note">Toda la temporada de ${esc(LNOM[r.liga])}. El Nivel Kerno de la plantilla se mide cada temporada frente al club medio de su liga ese año.</p>`;
}
''')
p.guardar()
p = P(sys.argv[1])
p.rep('<th ${tipA("Net v4.0 de la plantilla de la temporada (pts/100 frente al club medio de su liga): Σ minutos × RAPM proyectado. Es de la temporada entera, igual para todas las etapas.")}>Net v4.0</th>',
      '<th ${tipA("Nivel Kerno de la plantilla de la temporada (50 = club medio de su liga). Es de la temporada entera.")}>Nivel Kerno</th>')
p.rep('<td>${v4Html(v4Net(r.k))}</td><td class="txt">${euSpan(evUent(r.k, e.id), true)}</td>', '<td>${ok(r.L) ? evNiv(r.L) : "–"}</td><td class="txt">${euSpan(evUent(r.k, e.id), true)}</td>')
p.rep('<div ${tipA("Proporción de remuestreos de los minutos de la plantilla en la que el club conserva su perfil del mapa: alta = no depende de quién juegue cada noche. Se calcula sobre los perfiles del mapa, no sobre los estilos nuevos.")}><span>Robustez</span><b>${club && ok(club.rob) ? f(100 * club.rob, 0) + " %" : "–"}</b></div></div>',
      '<div ${tipA("Rasgos medidos frente a su liga vasca")}><span>Vara</span><b>${esc(LNOM[r.liga] || r.liga)}</b></div></div>')
p.rep('La robustez se estimó sobre los perfiles del mapa (A–F), no sobre los estilos nuevos. El detalle, en «Atlas de Estilos».', 'Los doce rasgos (ritmo, triple, esquina, aro, tiros libres, creación propia, pase, rebote ofensivo, pérdidas, robos, tapones y faltas) se miden frente a su liga y se asignan con la misma mezcla de seis estilos del sitio general. El detalle, en «Mapa de estilos».')
p.rep('const estNombre = (id) => (ESTILOS[id] && ESTILOS[id][0]) || "–"; // perfiles del mapa: siempre el rótulo neutro A–F', 'const estNombre = (id) => (ESTILOS[id] && ESTILOS[id][0]) || "–"; // Kerno Basque: los seis estilos unificados')
p.guardar()
