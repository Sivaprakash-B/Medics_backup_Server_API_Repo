#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  SEF Internal Data API — Quick Update Script
#  Run this on the server after pushing changes to GitHub.
# ══════════════════════════════════════════════════════════════
set -euo pipefail

INSTALL_DIR="/opt/db-api-gateway"
VENV_DIR="${INSTALL_DIR}/venv"

echo "═══════════════════════════════════════════════════"
echo "  SEF API — Pulling Latest & Restarting"
echo "═══════════════════════════════════════════════════"

cd "${INSTALL_DIR}"

# Pull latest code
echo "▶ Pulling latest from GitHub..."
git pull origin main

# Update dependencies (only if requirements.txt changed)
echo "▶ Updating Python dependencies..."
"${VENV_DIR}/bin/pip" install -r requirements.txt --quiet

# Restart service
echo "▶ Restarting sef-api service..."
sudo systemctl restart sef-api

# Show status
echo ""
echo "▶ Service status:"
sudo systemctl status sef-api --no-pager -l

echo ""
echo "✅  Deploy complete!"
echo "   Health check: curl http://localhost:8000/health"
