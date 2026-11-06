#!/usr/bin/env bash
# Start the virtual display, window manager and Chrome as the unprivileged rec user.
set -u
export DISPLAY=:99
URL="${1:-about:blank}"

pgrep -u rec Xvfb >/dev/null || { nohup Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp >/tmp/xvfb.log 2>&1 & sleep 1; }
pgrep -u rec openbox >/dev/null || { nohup openbox >/tmp/openbox.log 2>&1 & sleep 1; }
pgrep -u rec -f 'remote-debugging-port=9222' >/dev/null || {
  nohup google-chrome \
    --user-data-dir=/home/rec/chrome \
    --remote-debugging-port=9222 \
    --no-first-run --no-default-browser-check \
    --password-store=basic \
    --disable-features=Translate,InterestFeedContentSuggestions,ChromeWhatsNewUI \
    --disable-sync --disable-background-networking \
    --window-position=0,0 --window-size=1920,1080 \
    "$URL" >/tmp/chrome.log 2>&1 &
  sleep 6
}
xdotool search --onlyvisible --class google-chrome getwindowgeometry 2>/dev/null | head -3
curl -s http://127.0.0.1:9222/json/version | head -3
