#!/bin/bash
# usage: get.sh outname url [curl args...]
D=/tmp/claude-0/-home-user-baskonia/e378a948-3c35-5fd4-b5e1-0edff1989e32/scratchpad/research_el
out="$D/data/$1"; shift; url="$1"; shift
sleep 0.6
echo "$url" >> $D/requests.log
curl -sS -m 40 -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36" -H "Accept: application/json, */*" -o "$out" -w "%{http_code} %{size_download} %{content_type}\n" "$@" "$url"
