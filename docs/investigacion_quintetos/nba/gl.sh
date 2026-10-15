#!/bin/bash
# usage: gl.sh outfile endpoint querystring
out=$1; ep=$2; q=$3
curl -sS -m 40 -o "$out" -w "%{http_code} %{size_download}\n" \
 -H 'Accept: application/json, text/plain, */*' -H 'Origin: https://gleague.nba.com' -H 'Referer: https://gleague.nba.com/' \
 -A 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36' \
 "https://stats.gleague.nba.com/stats/$ep?$q"
