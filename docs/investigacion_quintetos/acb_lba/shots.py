import json, sys
def walk(o,p="",out=None,depth=0):
    if isinstance(o,dict):
        for k,v in o.items(): walk(v,p+"."+k,out,depth+1)
    elif isinstance(o,list):
        out.add(p+"[] len"+str(len(o)) if depth<3 else p+"[]")
        if o: walk(o[0],p+"[]",out,depth+1)
    else: out.add(p)
    return out
for f in sys.argv[1:]:
    d=json.load(open(f)); keys=sorted(walk(d,"",set()))
    print("==",f); print([k for k in keys if not any(s in k for s in ("Team.","logo","Color"))][:80])
