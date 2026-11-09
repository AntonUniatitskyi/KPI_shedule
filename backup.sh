#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

KEEP=14                      # скільки останніх копій зберігати
STAMP=$(date +%Y%m%d-%H%M)

docker compose exec -T kpi-schedule-bot python - "$STAMP" <<'PY'
import os, sqlite3, sys

stamp = sys.argv[1]
os.makedirs("data/backups", exist_ok=True)
src = sqlite3.connect("data/bot_data.db")
dst = sqlite3.connect(f"data/backups/bot_{stamp}.db")
with dst:
    src.backup(dst)          # офіційний API копіювання, безпечний при паралельних записах
dst.close()
src.close()
print(f"bot_{stamp}.db")
PY

# ротація: лишаємо KEEP найновіших
ls -1t data/backups/bot_*.db 2>/dev/null | tail -n +$((KEEP + 1)) | xargs -r rm --
echo "OK: bot_${STAMP}.db (усього копій: $(ls -1 data/backups/bot_*.db | wc -l))"