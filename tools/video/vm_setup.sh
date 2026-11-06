#!/usr/bin/env bash
# Recording stack for the demo video: a virtual 1080p display with a real Chrome
# window and a real terminal, captured with ffmpeg. Run once as root on the VM.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
apt-get -o DPkg::Lock::Timeout=300 update -qq
apt-get -o DPkg::Lock::Timeout=300 install -y -qq --no-install-recommends \
  xvfb openbox xterm xdotool x11-utils ffmpeg python3-venv \
  fonts-liberation fonts-dejavu-core fonts-noto-color-emoji >/dev/null

if ! command -v google-chrome >/dev/null; then
  curl -fsSL -o /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
  apt-get -o DPkg::Lock::Timeout=300 install -y -qq /tmp/chrome.deb >/dev/null
  rm -f /tmp/chrome.deb
fi

id rec >/dev/null 2>&1 || useradd -m -s /bin/bash rec
usermod -aG docker rec
mkdir -p /home/rec/.config/openbox
cat > /home/rec/.config/openbox/rc.xml <<'XML'
<?xml version="1.0"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <applications>
    <application class="*"><decor>no</decor></application>
    <application class="Google-chrome"><decor>no</decor><maximized>yes</maximized></application>
  </applications>
</openbox_config>
XML
chown -R rec:rec /home/rec

# the verifier runs from the repo in a host-side venv, outside any container
if [ ! -x /opt/cage/.venv/bin/python ]; then
  python3 -m venv /opt/cage/.venv
  /opt/cage/.venv/bin/pip install -q -r /opt/cage/requirements.txt
fi
google-chrome --version
ffmpeg -version | head -1
