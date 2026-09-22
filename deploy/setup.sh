#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  SEF Internal Data API — One-Time Server Setup Script
#  Target: Ubuntu/Debian Linux
#  Repo:   https://github.com/Sivaprakash-B/Medics_backup_Server_API_Repo.git
# ══════════════════════════════════════════════════════════════
set -euo pipefail

REPO_URL="https://github.com/Sivaprakash-B/Medics_backup_Server_API_Repo.git"
INSTALL_DIR="/opt/db-api-gateway"
SERVICE_USER="sef-api"
VENV_DIR="${INSTALL_DIR}/venv"
LOG_DIR="/var/log/sef-api"

echo "═══════════════════════════════════════════════════"
echo "  SEF API — Server Setup"
echo "═══════════════════════════════════════════════════"

# ── 1. Install system dependencies ──────────────────────────
echo ""
echo "▶ Step 1: Installing system packages..."
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git nginx

# ── 2. Create service user (no login shell) ─────────────────
echo ""
echo "▶ Step 2: Creating service user '${SERVICE_USER}'..."
if id "${SERVICE_USER}" &>/dev/null; then
    echo "  User '${SERVICE_USER}' already exists, skipping."
else
    sudo useradd --system --shell /usr/sbin/nologin --home "${INSTALL_DIR}" "${SERVICE_USER}"
    echo "  Created user '${SERVICE_USER}'."
fi

# ── 3. Clone the repo ───────────────────────────────────────
echo ""
echo "▶ Step 3: Cloning repository..."
if [ -d "${INSTALL_DIR}/.git" ]; then
    echo "  Repo already cloned. Pulling latest..."
    cd "${INSTALL_DIR}"
    sudo -u "${SERVICE_USER}" git pull origin main || git pull origin main
else
    sudo git clone "${REPO_URL}" "${INSTALL_DIR}"
    sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
fi
cd "${INSTALL_DIR}"

# ── 4. Create Python venv & install deps ────────────────────
echo ""
echo "▶ Step 4: Setting up Python virtual environment..."
if [ ! -d "${VENV_DIR}" ]; then
    sudo -u "${SERVICE_USER}" python3 -m venv "${VENV_DIR}" || python3 -m venv "${VENV_DIR}"
fi
sudo "${VENV_DIR}/bin/pip" install --upgrade pip
sudo "${VENV_DIR}/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

# ── 5. Create .env from template ────────────────────────────
echo ""
echo "▶ Step 5: Setting up environment file..."
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    sudo cp "${INSTALL_DIR}/env.example" "${INSTALL_DIR}/.env"
    sudo chown "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}/.env"
    sudo chmod 600 "${INSTALL_DIR}/.env"
    echo ""
    echo "  ⚠  IMPORTANT: Edit ${INSTALL_DIR}/.env with your real credentials:"
    echo "     sudo nano ${INSTALL_DIR}/.env"
    echo ""
else
    echo "  .env already exists, skipping."
fi

# ── 6. Create log directory ─────────────────────────────────
echo ""
echo "▶ Step 6: Creating log directory..."
sudo mkdir -p "${LOG_DIR}"
sudo chown "${SERVICE_USER}:${SERVICE_USER}" "${LOG_DIR}"

# ── 7. Install systemd service ──────────────────────────────
echo ""
echo "▶ Step 7: Installing systemd service..."
sudo cp "${INSTALL_DIR}/deploy/sef-api.service" /etc/systemd/system/sef-api.service
sudo systemctl daemon-reload
sudo systemctl enable sef-api
echo "  Service installed and enabled."

# ── 8. Install Nginx config ────────────────────────────────
echo ""
echo "▶ Step 8: Installing Nginx config..."
sudo cp "${INSTALL_DIR}/deploy/nginx-sef-api.conf" /etc/nginx/sites-available/sef-api
if [ ! -L /etc/nginx/sites-enabled/sef-api ]; then
    sudo ln -s /etc/nginx/sites-available/sef-api /etc/nginx/sites-enabled/sef-api
fi
echo "  ⚠  Edit /etc/nginx/sites-available/sef-api to set your server_name and SSL cert paths."

# ── 9. Set permissions ──────────────────────────────────────
echo ""
echo "▶ Step 9: Setting permissions..."
sudo chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"
sudo chmod 600 "${INSTALL_DIR}/.env"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  ✅  Setup Complete!"
echo "═══════════════════════════════════════════════════"
echo ""
echo "  Next steps:"
echo "  ─────────────────────────────────────────────────"
echo "  1. Edit .env with real credentials:"
echo "       sudo nano ${INSTALL_DIR}/.env"
echo ""
echo "  2. Edit Nginx config (server_name, SSL certs):"
echo "       sudo nano /etc/nginx/sites-available/sef-api"
echo ""
echo "  3. Test Nginx config:"
echo "       sudo nginx -t"
echo ""
echo "  4. Start the services:"
echo "       sudo systemctl start sef-api"
echo "       sudo systemctl restart nginx"
echo ""
echo "  5. Check status:"
echo "       sudo systemctl status sef-api"
echo "       curl http://localhost:8000/health"
echo ""
