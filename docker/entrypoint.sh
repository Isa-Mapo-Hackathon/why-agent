#!/usr/bin/env bash
set -euo pipefail

# Pull parquet data from HF Dataset at boot if the directory is empty
if [ -n "${HF_DATASET_ID:-}" ] && [ -z "$(ls -A /app/data/parquet 2>/dev/null)" ]; then
    echo "Fetching parquet from HF Dataset: $HF_DATASET_ID"
    if timeout 120 /app/.venv/bin/huggingface-cli download \
        --repo-type dataset \
        "${HF_DATASET_ID}" \
        --local-dir /app/data/parquet \
        --quiet; then
        echo "Parquet data ready."
    else
        echo "WARNING: parquet download failed or timed out. Falling back to MODEL_BACKEND=replay."
        export MODEL_BACKEND=replay
    fi
fi

exec supervisord -c /etc/supervisord.conf
