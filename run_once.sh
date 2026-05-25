#!/bin/zsh
cd /Users/nakanoyuuki/economy-news-line

for i in {1..60}; do
  /usr/bin/curl -fsS --connect-timeout 5 https://news.google.com >/dev/null 2>&1 && break
  echo "$(date '+%Y-%m-%d %H:%M:%S') waiting for network... attempt ${i}/60"
  sleep 10
done

/Users/nakanoyuuki/economy-news-line/.venv/bin/python /Users/nakanoyuuki/economy-news-line/main.py --once
