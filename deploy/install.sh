#!/usr/bin/env bash
set -euo pipefail

# Run as root on the Vultr server after rsync'ing the repo to /opt/belowiceberg
REPO=/opt/belowiceberg

apt-get update -qq
apt-get install -y -qq python3.11 python3.11-venv

# Create data dirs
mkdir -p /var/www/belowiceberg-data/notes
chown -R www-data:www-data /var/www/belowiceberg-data
mkdir -p /etc/belowiceberg
chmod 750 /etc/belowiceberg

# Venv
if [ ! -d "$REPO/server/.venv" ]; then
  python3.11 -m venv "$REPO/server/.venv"
fi
"$REPO/server/.venv/bin/pip" install -q -e "$REPO/server"

# systemd unit
cp "$REPO/deploy/belowiceberg-api.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable belowiceberg-api.service
systemctl restart belowiceberg-api.service

# nginx
cp "$REPO/deploy/nginx-belowiceberg.conf" /etc/nginx/sites-available/belowiceberg
ln -sf /etc/nginx/sites-available/belowiceberg /etc/nginx/sites-enabled/belowiceberg
nginx -t
systemctl reload nginx

echo
echo "── Almost done. Now create /etc/belowiceberg/admin.env with:"
echo "ADMIN_PASSWORD_HASH=<bcrypt hash>"
echo "SESSION_SECRET=<random 32+ chars>"
echo "DEEPSEEK_API_KEY=<your key>"
echo "── Then: systemctl restart belowiceberg-api.service"
