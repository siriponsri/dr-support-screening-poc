#!/bin/sh
# FOR THE dr-train ADMINISTRATOR ONLY (run with sudo). Not run by the app or by Claude Code.
# Creates one restricted account that can do nothing except forward a local port to the regular gateway
# (127.0.0.1:7860). No shell, no other forwarding, no agent or X11 forwarding, no terminal.
# Usage: sudo sh create-restricted-user.sh <account-name> <path-to-the-person's-public-key.pub>
set -eu
name=${1:?usage: create-restricted-user.sh <account-name> <public-key-file>}
key_file=${2:?usage: create-restricted-user.sh <account-name> <public-key-file>}
case "$name" in drgw-[a-z0-9]*) ;; *) echo "Account names start with drgw- (for example drgw-ann)"; exit 2 ;; esac
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 2; }
key=$(head -n 1 "$key_file")
case "$key" in ssh-ed25519\ *|ecdsa-sha2-*\ *|ssh-rsa\ *) ;; *) echo "Not a public key file."; exit 2 ;; esac
id "$name" >/dev/null 2>&1 || useradd --create-home --shell /usr/sbin/nologin "$name"
home=$(getent passwd "$name" | cut -d: -f6)
install -d -m 700 -o "$name" -g "$name" "$home/.ssh"
printf 'restrict,port-forwarding,permitopen="127.0.0.1:7860",command="/bin/false" %s\n' "$key" > "$home/.ssh/authorized_keys"
chown "$name:$name" "$home/.ssh/authorized_keys"
chmod 600 "$home/.ssh/authorized_keys"
echo "Ready: $name can only forward to 127.0.0.1:7860."
echo "Remove later with: sudo userdel --remove $name"
