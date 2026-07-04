#!/bin/bash
# family-finance-backend 自動啟動腳本
# 啟動後端 + cloudflare tunnel，網址變了自動更新 GitHub

set -e

cd /home/clement/HermesProjects/FinancialAutomation

# 1. 啟動後端 (如果還沒跑)
if ! curl -sf http://localhost:8800/health > /dev/null 2>&1; then
    echo "[$(date)] 啟動後端..."
    source /home/clement/.hermes/hermes-agent/venv/bin/activate
    CRED_PATH=/home/clement/HermesProjects/google_creds.json \
    SHEET_KEY=10257dP7ZcVqT5gIp8OPf-t78rJK8XyouXpxzjZY7AHQ \
    nohup uvicorn backend.main:app --host 0.0.0.0 --port 8800 --workers 2 > /tmp/family-backend.log 2>&1 &
    sleep 3
fi

# 2. 啟動 cloudflare tunnel
echo "[$(date)] 啟動 Cloudflare Tunnel..."
TUNNEL_OUT=$(/tmp/cloudflared tunnel --url http://localhost:8800 2>&1)
TUNNEL_URL=$(echo "$TUNNEL_OUT" | grep -oP 'https://[a-z-]+\.trycloudflare\.com' | head -1)

if [ -z "$TUNNEL_URL" ]; then
    echo "[$(date)] ERROR: 無法取得 tunnel URL"
    exit 1
fi

echo "[$(date)] Tunnel URL: $TUNNEL_URL"

# 3. 檢查 URL 是否跟目前 git 的一致
CURRENT_URL=$(grep "API_BASE" index.html | grep -oP 'https://[^"]+')

if [ "$TUNNEL_URL" != "$CURRENT_URL" ]; then
    echo "[$(date)] 網址變更！更新前端程式碼..."
    sed -i "s|const API_BASE = localStorage.getItem('famt_api_base') || '[^']*'|const API_BASE = localStorage.getItem('famt_api_base') || '$TUNNEL_URL'|" index.html
    git add -A
    git commit -m "auto: update API base to $TUNNEL_URL"
    git push
    echo "[$(date)] ✅ 已更新前端 API 網址為 $TUNNEL_URL"
else
    echo "[$(date)] 網址未變，跳過更新"
fi
