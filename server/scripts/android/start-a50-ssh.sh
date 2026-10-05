#!/data/data/com.termux/files/usr/bin/sh
# Deploy to ~/.termux/boot/10-start-ssh after installing and opening Termux:Boot.
set -eu
export PREFIX=/data/data/com.termux/files/usr
export PATH="$PREFIX/bin:$PATH"
umask 077
state_dir="$HOME/.local/state/a50-server"
mkdir -p "$state_dir"
log_file="$state_dir/bootstrap.log"
if [ -f "$log_file" ]; then
    tail -n 100 "$log_file" > "$log_file.tmp"
    mv "$log_file.tmp" "$log_file"
fi
exec >> "$log_file" 2>&1
date -u '+BOOT_START=%Y-%m-%dT%H:%M:%SZ'
termux-wake-lock
sshd -t -p 8022 -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no
if pgrep -x sshd > /dev/null; then
    echo 'SSH_ALREADY_RUNNING'
else
    sshd -p 8022 -o PasswordAuthentication=no -o KbdInteractiveAuthentication=no
    echo 'SSH_START_COMMAND_COMPLETED'
fi
