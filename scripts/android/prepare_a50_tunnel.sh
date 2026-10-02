#!/data/data/com.termux/files/usr/bin/sh
set -eu
umask 077
printf 'ARCHITECTURE='
uname -m
apt-get -s install cloudflared
apt-get install --no-upgrade -y cloudflared
cloudflared --version
test -f "$PREFIX/var/service/cloudflared/down"
printf 'VENDOR_TUNNEL_SERVICE_DISABLED=PASS\n'
curl --fail --silent http://127.0.0.1:8001/health/ready
printf '\nCENTRAL_LOOPBACK_READY=PASS\n'
