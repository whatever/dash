#!/bin/sh
set -eu
apk add --no-cache openssh-keygen >/dev/null
umask 077
[ -f /opt/data/.ssh/id_ed25519 ] || ssh-keygen -q -t ed25519 -N '' -C hermes-agent -f /opt/data/.ssh/id_ed25519
: > /opt/data/.ssh/known_hosts
cat > /opt/data/.ssh/config <<'CFG'
Host sandbox
  HostName sandbox
  User agent
  Port 2222
  IdentityFile /opt/data/.ssh/id_ed25519
  IdentitiesOnly yes
  StrictHostKeyChecking accept-new
  UserKnownHostsFile /opt/data/.ssh/known_hosts
CFG
chmod 0700 /opt/data/.ssh
chmod 0644 /opt/data/.ssh/id_ed25519.pub
sed "s|\${OPENAI_API_KEY}|${OPENAI_API_KEY}|" /etc/hermes/config.yaml > /opt/data/config.yaml
mkdir -p /opt/data/cache/vision-tmp
chown -R 10000:10000 /opt/data /opt/data/.ssh
