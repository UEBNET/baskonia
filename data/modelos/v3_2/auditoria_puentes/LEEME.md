# Auditoría de jugadores puente (§13)

Muestra aleatoria (semilla 20261102) de 100 personas que juegan en feb3, feb2, cba, nbl, bnxt, ncaa y en otra liga. Para cada fila, comprueba que todos los registros de `detalle_registros` son la MISMA persona (ficha de la liga, fecha de nacimiento, nacionalidad, trayectoria) y escribe `sí` o `no` en `correcto` (y, si quieres, un comentario). Las filas con `avisos_automaticos` van primero.

Criterio: cota inferior de Clopper-Pearson al 95 % de la precisión ≥ 0,95 (con 100 filas, como mucho 1 error). Después: `python -m bbmodel auditoria-puentes --evaluar`.
