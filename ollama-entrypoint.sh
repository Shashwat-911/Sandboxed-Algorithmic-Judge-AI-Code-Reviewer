#!/bin/sh
set -e

MODEL="${OLLAMA_MODEL:-qwen2.5-coder}"

echo "[ollama-entrypoint] Starting Ollama server in background..."
ollama serve &
OLLAMA_PID=$!

echo "[ollama-entrypoint] Waiting for Ollama API to become available..."
# Use built-in ollama command instead of missing curl
until ollama list > /dev/null 2>&1; do
    sleep 2
done

echo "[ollama-entrypoint] Pulling model: ${MODEL}"
ollama pull "${MODEL}"
echo "[ollama-entrypoint] Model ${MODEL} ready. Handing off to Ollama server (PID ${OLLAMA_PID})."

wait $OLLAMA_PID