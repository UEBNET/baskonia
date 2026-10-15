import json,re,sys
h=open(sys.argv[1],encoding='utf-8',errors='replace').read()
m=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S)
d=json.loads(m.group(1))
print('buildId',d.get('buildId'),'page',d.get('page'),'query',d.get('query'))
pp=d['props']['pageProps']
def sk(x,p='',depth=0,maxd=3):
    if depth>maxd: return
    if isinstance(x,dict):
        for k,v in x.items():
            t=type(v).__name__; ln=len(v) if isinstance(v,(list,dict,str)) else ''
            print('  '*depth+f'{k}: {t} {ln}' + (f' = {v!r}'[:80] if not isinstance(v,(list,dict)) else ''))
            sk(v,p+k+'.',depth+1,maxd)
    elif isinstance(x,list) and x:
        sk(x[0],p,depth,maxd)
sk(pp,maxd=int(sys.argv[2]) if len(sys.argv)>2 else 1)
