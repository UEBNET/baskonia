#!/bin/bash
# usage: get.sh URL OUTFILE [extra curl args...]
S=/tmp/claude-0/-home-user-baskonia/e378a948-3c35-5fd4-b5e1-0edff1989e32/scratchpad/research_bbl_lnb
url="$1"; out="$2"; shift 2
host=$(echo "$url" | awk -F/ '{print $3}')
lock="$S/scripts/.last_$host"
if [ -f "$lock" ]; then
  last=$(cat "$lock"); now=$(date +%s.%N)
  d=$(echo "0.6 - ($now - $last)" | bc -l)
  if (( $(echo "$d > 0" | bc -l) )); then sleep_cmd=$(printf "%.2f" $d); python3 -c "import time;time.sleep($sleep_cmd)"; fi
fi
date +%s.%N > "$lock"
echo "$url" >> "$S/scripts/requests.log"
curl -sS -L --compressed -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36" -o "$out" -w "%{http_code} %{size_download} %{content_type}\n" "$@" "$url"
