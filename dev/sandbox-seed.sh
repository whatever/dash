#!/bin/sh
set -eu
apk add --no-cache openssh-keygen >/dev/null
[ -f /keys/id_ed25519 ] || ssh-keygen -q -t ed25519 -N '' -C dash-agent -f /keys/id_ed25519
chmod 0644 /keys/id_ed25519 /keys/id_ed25519.pub
