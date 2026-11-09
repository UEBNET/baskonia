// Regla de oro (F4 v4.1): inventario de controles por página (botones, enlaces, selects con sus opciones, entradas, pestañas)
// node inventario_controles.js <url_base> <salida.json>  — requiere playwright (preinstalado en el entorno)
const { chromium } = require("playwright");
const [base, salida] = process.argv.slice(2);
const PAGINAS = ["index.html", "atlas/index.html", "v40/index.html", "quintetos/index.html", "clasico.html"];
(async () => {
  const br = await chromium.launch();
  const out = {};
  for (const p of PAGINAS) {
    const pg = await br.newPage({ viewport: { width: 1440, height: 900 } });
    const errores = [];
    pg.on("pageerror", (e) => errores.push(String(e)));
    pg.on("console", (m) => { if (m.type() === "error") errores.push(m.text()); });
    try { await pg.goto(base + p, { waitUntil: "load", timeout: 120000 }); } catch (e) { errores.push("goto: " + e); }
    await pg.waitForTimeout(8000);
    const inv = await pg.evaluate(() => {
      const vis = (el) => { const r = el.getBoundingClientRect(); return !!(r.width || r.height || el.getClientRects().length); };
      const txt = (el) => (el.getAttribute("aria-label") || el.textContent || el.value || "").replace(/\s+/g, " ").trim().slice(0, 80);
      const q = (s) => Array.from(document.querySelectorAll(s));
      return {
        botones: q("button").map((b) => ({ id: b.id || null, t: txt(b), vis: vis(b) })),
        enlaces: q("a[href]").map((a) => ({ id: a.id || null, t: txt(a), href: a.getAttribute("href"), vis: vis(a) })),
        selects: q("select").map((s) => ({ id: s.id || null, n: s.options.length, opciones: Array.from(s.options).slice(0, 12).map((o) => o.textContent.trim().slice(0, 40)), vis: vis(s) })),
        entradas: q("input, textarea").map((i) => ({ id: i.id || null, tipo: i.type, vis: vis(i) })),
        pestanas: q("[role=tab], .tab, [data-tab], [data-vista]").map((t) => ({ id: t.id || null, t: txt(t) })),
        titulo: document.title,
      };
    });
    out[p] = { ...inv, errores: errores.slice(0, 20) };
    await pg.close();
  }
  await br.close();
  require("fs").writeFileSync(salida, JSON.stringify(out, null, 1));
  for (const [p, v] of Object.entries(out)) console.log(p, "botones", v.botones.length, "enlaces", v.enlaces.length, "selects", v.selects.length, "entradas", v.entradas.length, "errores", v.errores.length);
})();
