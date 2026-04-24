#!/usr/bin/env bash
# Download a piper voice (onnx + json) into /app/models/piper/.
# Usage: download_piper_voice.sh <voice_id>  e.g. gosia-medium
set -euo pipefail

VOICE="${1:-gosia-medium}"
DEST="${PIPER_VOICE_DIR:-/app/models/piper}"
mkdir -p "$DEST"

# Rhasspy publishes voices at
# https://huggingface.co/rhasspy/piper-voices/resolve/main/<locale>/<voice>/<name>.onnx(.json)
case "$VOICE" in
  gosia-medium)
    LOCALE="pl/pl_PL"
    BASENAME="pl_PL-gosia-medium"
    ;;
  *)
    echo "unknown voice: $VOICE" >&2
    exit 1
    ;;
esac

BASE="https://huggingface.co/rhasspy/piper-voices/resolve/main/${LOCALE}/${VOICE%-*}/${VOICE##*-}"
curl -fsSL "${BASE}/${BASENAME}.onnx" -o "${DEST}/${BASENAME}.onnx"
curl -fsSL "${BASE}/${BASENAME}.onnx.json" -o "${DEST}/${BASENAME}.onnx.json"
echo "installed: ${DEST}/${BASENAME}.onnx"
