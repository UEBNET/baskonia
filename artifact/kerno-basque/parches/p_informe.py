import sys; sys.path.insert(0, "/home/claude/w/patches")
from util import P
p = P(sys.argv[1])
p.rep('const FASES = [["regular", "Liga regular"], ["playoffs", "Playoffs"], ["total", "Toda la temporada"]];',
      'const FASES = [["regular", "Toda la temporada"]];   // Federación Vasca: la temporada entera (todas las fases y divisiones) va como «regular»')
p.rep('const FNOM = { regular: "liga regular", playoffs: "playoffs", total: "toda la temporada" };',
      'const FNOM = { regular: "toda la temporada", playoffs: "playoffs", total: "toda la temporada" };')
p.rep('Medias por partido de ${E(t)} (liga regular).', 'Medias por partido de ${E(t)} (toda la temporada).')
p.rep('["Net proyectado · Nivel Kerno · Impacto", "v4.0: puntos por 100 posesiones que proyecta la plantilla frente a su liga; y por jugador, de 0 a 100, su producción esperada entre los de su puesto y lo que pierde el equipo sin él (50 = nada)."]',
      '["Nivel Kerno · Impacto", "Por jugador, de 0 a 100 frente a los jugadores de su liga vasca (50 = jugador medio): Nivel Kerno = 0,6 · producción (PER, Win Shares, Game Score y PIE por minuto) + 0,4 · impacto (RAPM y on/off ajustado), con su rango del 80 %. Sin proyección entre ligas."]')
p.rep("informe/<temporada> (medias por partido) y rol del simulador.", "informe/<temporada> (medias por partido; opcional).")
p.guardar()
