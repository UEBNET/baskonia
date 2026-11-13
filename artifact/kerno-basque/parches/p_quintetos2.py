import sys; sys.path.insert(0, "/home/claude/w/patches")
from util import P
p = P(sys.argv[1])
p.rep('const FASES = [["regular", "Regular"], ["playoffs", "Playoffs"], ["total", "Total"]];',
      'const FASES = [["regular", "Toda la temporada"]];   // Federación Vasca: todas las fases y divisiones juntas')
p.guardar()
