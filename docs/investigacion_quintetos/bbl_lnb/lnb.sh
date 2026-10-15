#!/bin/bash
# usage: lnb.sh PATH OUT [curl args e.g. -X POST -d json]
S=/tmp/claude-0/-home-user-baskonia/e378a948-3c35-5fd4-b5e1-0edff1989e32/scratchpad/research_bbl_lnb
tf=$S/dl/lnb/token.json
if [ ! -f $tf ] || [ $(( $(date +%s) - $(stat -c %Y $tf) )) -gt 700 ]; then $S/scripts/get.sh https://lnb.fr/api/token $tf >/dev/null; fi
tok=$(grep -oE '"token":"[^"]+"' $tf | cut -d'"' -f4)
p="$1"; out="$2"; shift 2
$S/scripts/get.sh "https://api-prod.lnb.fr/$p" "$out" -H "Authorization: Bearer $tok" -H "device_type: web" -H "language_code: fr" -H "Origin: https://lnb.fr" -H "Referer: https://lnb.fr/" -H "Content-Type: application/json" "$@"
