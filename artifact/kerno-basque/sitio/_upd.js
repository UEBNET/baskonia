/* Botón «Ejecutar»: la página no ejecuta Python. Con la capacidad `mcp` (conector «Claude Code Remote») lanza la tarea
   «EJECUTAR Kerno Basque Analytics» (fire_trigger) y sigue su última ejecución (get_trigger). La tarea abre una sesión
   de Claude Code que actualiza la temporada pedida en la rama FTAB y vuelve a publicar esta página (Federación Vasca y Kerno Basque Analytics). */
(function () {
  "use strict";
  const TRIGGER = "trig_01Tmstsk4KswuUPmpBjhHgKf", SERVER = "Claude Code Remote", MAX_MS = 3 * 3600e3, CADA_MS = 60e3;
  const el = (i) => document.getElementById(i);
  const btn = el("updBtn"), pop = el("updPop"), est = el("updEst"), go = el("updGo"), no = el("updNo"), ult = el("updUlt"), dat = el("updDatos"), sel = el("updTemp");
  const mem = { get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* */ } } };
  const escU = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fecha = (t) => { const d = new Date(t); return isNaN(d) ? "" : d.toLocaleString("es-ES", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); };
  let mcp = null, timer = 0;
  const abierto = () => !pop.hidden;
  function abrir(on) { pop.hidden = !on; btn.setAttribute("aria-expanded", String(on)); if (on) leerEstado(); }
  btn.addEventListener("click", (e) => { e.stopPropagation(); abrir(!abierto()); });
  no.addEventListener("click", () => { abrir(false); btn.focus(); });
  document.addEventListener("click", (e) => { if (abierto() && !pop.contains(e.target) && !btn.contains(e.target)) abrir(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && abierto()) { abrir(false); btn.focus(); } });
  ["2026-27", "2025-26", "2024-25", "2023-24", "2022-23"].forEach((t) => { const o = document.createElement("option"); o.value = o.textContent = t; sel.appendChild(o); });
  const ETQ = { run: "En marcha", err: "Con error" };
  function pinta(st, txt) { if (st === "run" || st === "err") btn.dataset.st = st; else delete btn.dataset.st; est.textContent = ETQ[st] || "Ejecutar"; ult.innerHTML = txt || ""; }
  fetch("quintetos/datos/indice.json").then((r) => r.json()).then((d) => { dat.innerHTML = `Datos publicados el <b>${escU(fecha(d.generado))}</b>.`; }).catch(() => { dat.textContent = ""; });
  const errorTxt = (e) => ({
    server_not_connected: "Falta el conector «Claude Code Remote» en tu cuenta: claude.ai, Ajustes, Conectores.",
    needs_reauth: "Hay que volver a conectar «Claude Code Remote» en claude.ai, Ajustes, Conectores.",
    not_in_manifest: "No has permitido a esta página usar «Claude Code Remote». Puedes cambiarlo en los permisos del artifact.",
    approval_required: "La acción necesita tu aprobación: pulsa de nuevo y acepta el aviso de claude.ai.",
    blocked_by_policy: "La política de tu organización no permite lanzar la actualización desde aquí.",
    tool_error: "No se pudo lanzar o consultar la actualización con tu cuenta: solo la cuenta propietaria puede lanzarla.",
  }[e && e.code] || `No se pudo contactar con Claude Code Remote (${escU((e && e.code) || "error")}).`);
  function ejecucion(lr) {
    if (!lr) return ["", "Todavía no se ha lanzado ninguna ejecución con el botón."];
    const s = String(lr.status || "");
    if (/RUNNING|PENDING|QUEUED|STARTED/.test(s) || (!lr.finished_at && lr.fired_at)) return ["run", `Ejecución en marcha desde ${escU(fecha(lr.fired_at))}. La página se publicará sola al terminar.`];
    if (/SUCCEEDED/.test(s)) return ["ok", `Última ejecución: terminó el ${escU(fecha(lr.finished_at || lr.fired_at))}.`];
    if (/FAILED|ERROR|CANCEL/.test(s)) return ["err", `La última ejecución (${escU(fecha(lr.fired_at))}) terminó con error; los datos publicados son los anteriores.`];
    return ["", `Última ejecución: ${escU(fecha(lr.fired_at))}.`];
  }
  async function leerEstado() {
    if (!mcp || TRIGGER.startsWith("@@")) return null;
    try { const r = await mcp.callTool(SERVER, "get_trigger", { trigger_id: TRIGGER }, { cache: false }); const t = (r && r.payload && (r.payload.trigger || r.payload)) || {};
      const [st, txt] = ejecucion(t.last_run); pinta(st, txt); go.disabled = st === "run"; return t.last_run || null; }
    catch (e) { pinta("", escU(errorTxt(e))); return null; }
  }
  function seguir() {
    clearTimeout(timer); const t0 = Number(mem.get("kerno.basque.lanzado") || 0); if (!t0 || Date.now() - t0 > MAX_MS) return;
    timer = setTimeout(async () => { const lr = await leerEstado(); if (lr && lr.finished_at && new Date(lr.finished_at) >= new Date(t0 - 120e3)) { mem.set("kerno.basque.lanzado", ""); } else seguir(); }, CADA_MS);
  }
  go.addEventListener("click", async () => {
    if (!mcp) return; go.disabled = true; pinta("run", "Lanzando la ejecución…");
    try { await mcp.callTool(SERVER, "fire_trigger", { trigger_id: TRIGGER, text: `temporada=${sel.value} origen=boton-kerno-basque` }, { cache: false });
      mem.set("kerno.basque.lanzado", String(Date.now())); pinta("run", "Ejecución lanzada. Tarda entre 10 y 40 minutos; puedes cerrar la página."); seguir(); }
    catch (e) { go.disabled = false; const dud = e && (e.code === "server_unavailable" || e.code === "upstream_error"); pinta(dud ? "" : "err", dud ? "No hubo respuesta: puede que se haya lanzado igualmente. Comprueba el estado en unos minutos antes de volver a pulsar." : escU(errorTxt(e))); }
  });
  const sinMcp = () => { go.disabled = true; pinta("", "Para ejecutar la extracción, abre esta página en claude.ai con la cuenta propietaria."); };
  if (TRIGGER.startsWith("@@")) { sinMcp(); return; }
  (window.claude && window.claude.use ? window.claude.use("mcp") : Promise.resolve(null)).then((m) => { mcp = m; if (!m) { sinMcp(); return; } leerEstado().then(seguir); }).catch(sinMcp);
})();
