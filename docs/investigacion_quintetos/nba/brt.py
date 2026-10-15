import re,sys
from html.parser import HTMLParser
class P(HTMLParser):
    def __init__(s): super().__init__(); s.t={}; s.cur=None; s.row=None; s.cell=None
    def handle_starttag(s,tag,a):
        a=dict(a)
        if tag=="table": s.cur=a.get("id"); s.t[s.cur]=[]
        elif tag=="tr" and s.cur: s.row={}; s.cell=None
        elif tag in("td","th") and s.row is not None: s.cell=a.get("data-stat"); s.row.setdefault(s.cell,"")
    def handle_endtag(s,tag):
        if tag=="tr" and s.row: s.t[s.cur].append(s.row); s.row=None
        elif tag=="table": s.cur=None
    def handle_data(s,d):
        if s.row is not None and s.cell: s.row[s.cell]=s.row.get(s.cell,"")+d
show=sys.argv[1].split(",")
for f in sys.argv[2:]:
    p=P(); p.feed(re.sub(r"<!--|-->","",open(f,encoding="utf-8",errors="replace").read()))
    for k,v in p.t.items():
        rows=[r for r in v if len(r)>5]
        print(f,k,len(rows))
        if rows and k in show:
            print("  keys:",list(rows[0].keys())); 
            for r in rows[:3]: print("  ex:",r)
