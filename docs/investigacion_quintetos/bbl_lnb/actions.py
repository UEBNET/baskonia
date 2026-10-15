import json,re,sys,collections
h=open(sys.argv[1],encoding='utf-8',errors='replace').read()
m=re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>',h,re.S)
pp=json.loads(m.group(1))['props']['pageProps']
gs=pp['initialGameStats']; A=gs['actions']
print('n actions',len(A))
print(json.dumps(A[0],ensure_ascii=False)[:1500])
c=collections.Counter(a.get('type') for a in A); print(c)
keys=collections.Counter(k for a in A for k in a); print(keys)
for t in list(c)[:40]:
    ex=next(a for a in A if a.get('type')==t)
    print('---',t, json.dumps({k:v for k,v in ex.items()},ensure_ascii=False)[:700])
