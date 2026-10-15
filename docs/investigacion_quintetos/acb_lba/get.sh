#!/bin/bash
# usage: get.sh OUTFILE URL [extra curl args]; logs and sleeps
out=$1; shift; url=$1; shift
echo "$(date +%s) $url" >> /tmp/claude-0/-home-user-baskonia/e378a948-3c35-5fd4-b5e1-0edff1989e32/scratchpad/research_acb_lba/requests.log
curl -sS -L --max-time 40 -A "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36" -o "$out" -w "%{http_code} %{size_download} %{content_type}\n" "$url" "$@"
sleep 0.7
