#!/usr/bin/env bash
# Bootstrap xiaohongshu-mcp for local publishing
#
# Prerequisites:
#   - Go 1.21+ installed (or download the binary release)
#   - A Xiaohongshu account for QR code login
#
# Usage:
#   bash scripts/bootstrap_mcp.sh

set -euo pipefail

MCP_REPO="ptonlix/xiaohongshu-mcp"
MCP_DIR="$HOME/.xiaohongshu-mcp"

echo "=== xiaohongshu-mcp Bootstrap ==="
echo ""

# Check if already installed
if [ -d "$MCP_DIR" ]; then
    echo "Found existing installation at $MCP_DIR"
    echo "To reinstall, remove it first: rm -rf $MCP_DIR"
else
    echo "Cloning xiaohongshu-mcp..."
    git clone "https://github.com/$MCP_REPO.git" "$MCP_DIR"
fi

cd "$MCP_DIR"

echo ""
echo "Building..."
if command -v go &> /dev/null; then
    go build -o xiaohongshu-mcp .
    echo "Built successfully: $MCP_DIR/xiaohongshu-mcp"
else
    echo "Go not found. Please either:"
    echo "  1. Install Go: https://go.dev/dl/"
    echo "  2. Download a pre-built release from: https://github.com/$MCP_REPO/releases"
    exit 1
fi

echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Start the MCP server:"
echo "   cd $MCP_DIR && ./xiaohongshu-mcp"
echo ""
echo "2. Scan the QR code with your Xiaohongshu app to log in"
echo ""
echo "3. The server will listen on http://localhost:18060"
echo ""
echo "4. Test with:"
echo "   curl http://localhost:18060/health"
echo ""
echo "5. Configure in your .env:"
echo "   XHS_MCP_URL=http://localhost:18060"
