#!/data/data/com.termux/files/usr/bin/sh
# Package installation only; leave the working SSH boot script untouched.
set -eu
export PREFIX=/data/data/com.termux/files/usr
export PATH="$PREFIX/bin:$PATH"
export DEBIAN_FRONTEND=noninteractive
umask 077
echo RUNTIME_PREFLIGHT
test -f "$HOME/.termux/boot/10-start-ssh"
sha256sum "$HOME/.termux/boot/10-start-ssh"
dpkg-query -W -f='${Package} ${Version} ${Status}\n' openssh
df -h "$HOME"
apt-get update
apt-get install -y python python-pip termux-services
python --version
python -m pip --version
python -c 'import sqlite3; print("SQLITE_VERSION=" + sqlite3.sqlite_version)'
dpkg-query -W -f='${Package} ${Version} ${Status}\n' python python-pip termux-services runit
sha256sum "$HOME/.termux/boot/10-start-ssh"
echo RUNTIME_PACKAGES_INSTALLED
