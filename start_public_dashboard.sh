#!/usr/bin/env bash
# TTU FactBook & Trends Live Quality Dashboard & Public Tunnel Launcher

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

PORT=5050

# Clean up any existing instances
lsof -ti :$PORT | xargs kill -9 2>/dev/null
pkill -f "localhost.run" 2>/dev/null
pkill -f "localtunnel" 2>/dev/null

echo "========================================================================"
echo " Starting TTU FactBook & Trends Live Dashboard Server..."
echo "========================================================================"

# Start python web server
./venv/bin/python web_server.py > /dev/null 2>&1 &
SERVER_PID=$!
sleep 1.5

# Verify web server
if ! curl -s "http://localhost:$PORT/api/status" > /dev/null; then
    echo "Failed to start local web server on port $PORT"
    exit 1
fi

echo "✓ Local Dashboard is Live at:"
echo "  👉 http://localhost:$PORT"
echo ""

# Start secure public SSH tunnel via localhost.run
echo "Starting secure public HTTPS tunnel..."
TUNNEL_LOG="/tmp/ttu_public_tunnel.log"
rm -f "$TUNNEL_LOG"

ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -R 80:127.0.0.1:$PORT nokey@localhost.run > "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

PUBLIC_URL=""
for i in {1..30}; do
    if grep -q "https://" "$TUNNEL_LOG"; then
        PUBLIC_URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.lhr\.life" "$TUNNEL_LOG" | tail -n 1)
        if [ -n "$PUBLIC_URL" ]; then
            break
        fi
    fi
    sleep 0.5
done

echo "========================================================================"
if [ -n "$PUBLIC_URL" ]; then
    echo "🎉 YOUR PUBLIC REFRESHABLE DASHBOARD LINK IS LIVE:"
    echo ""
    echo "  🌐 $PUBLIC_URL"
    echo ""
    echo "  (Open this link in any browser or on your phone.)"
    echo "  (Whenever you refresh the page or click 'Run Full Test Suite',"
    echo "   it performs live checks and displays any errors immediately!)"
else
    echo "Connecting to tunnel... If URL does not appear, check $TUNNEL_LOG"
fi
echo "========================================================================"
echo "Press Ctrl+C to stop dashboard and public tunnel."

trap 'echo "Stopping server and tunnel..."; kill $SERVER_PID $TUNNEL_PID 2>/dev/null; exit 0' SIGINT SIGTERM

wait
