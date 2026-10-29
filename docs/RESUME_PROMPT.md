# Prompt para reanudar el proyecto

Pega este texto al abrir una sesión nueva de Claude Code y completa la última línea:

```text
Lee CLAUDE.md. Consulta en docs/PROJECT_STATE.md solo las secciones que afecten a la tarea (usa su índice;
no leas el documento entero). La rama viva es claude/basketball-stats-extractor-jpas93 (main está desfasado):
parte de ella salvo que te indique otra.
Respeta las reglas no negociables de CLAUDE.md: capas raw → clean → features → models → simulation → outputs,
sin fuga temporal, incertidumbre siempre explícita, umbrales sólo en configs/*.yaml, no citar la fuente
conceptual externa del reemplazo de rol, no inventar resultados (sólo cifras de data/modelos/** o
docs/checkpoints/**).
Antes de cambiar un modelo, lee su informe docs/checkpoints/F<n>.md y ejecuta sus tests.
Al terminar, actualiza docs/PROJECT_STATE.md (historial, estado ✅/🟡/❌, deuda, discrepancias) y CLAUDE.md
sólo si cambia algo estructural (máx. ~150 líneas).
Tarea: …
```
