#!/usr/bin/env bash
# Start vLLM server on AMD MI300X using the pre-pulled Docker image.
# The AMD Developer Cloud droplet already has vllm/vllm-openai-rocm:v0.17.1 cached.
# Usage: bash scripts/start_vllm.sh
# Endpoint after start: http://165.245.128.117:8000/v1

set -euo pipefail

DROPLET="root@165.245.128.117"
MODEL="Qwen/Qwen3-30B-A3B"
PORT=8000
CONTAINER="vllm-server"
IMAGE="vllm/vllm-openai-rocm:v0.17.1"
HF_TOKEN="${HF_TOKEN:-}"

echo "==> Connecting to AMD droplet..."

ssh "$DROPLET" bash << EOF
set -euo pipefail

# Stop and remove any existing container
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER}\$"; then
  echo "==> Removing existing container '${CONTAINER}'..."
  docker rm -f "${CONTAINER}" >/dev/null
fi

echo "==> Starting vLLM container..."
echo "    Image : ${IMAGE}"
echo "    Model : ${MODEL}"
echo "    Port  : ${PORT}"

docker run -d \
  --name "${CONTAINER}" \
  --network=host \
  --device=/dev/kfd \
  --device=/dev/dri \
  --group-add=video \
  --cap-add=SYS_PTRACE \
  --security-opt seccomp=unconfined \
  --shm-size=16gb \
  -v /root/.cache/huggingface:/root/.cache/huggingface \
  -e HF_TOKEN="${HF_TOKEN}" \
  -e GLOO_SOCKET_IFNAME=eth0 \
  -e NCCL_SOCKET_IFNAME=eth0 \
  "${IMAGE}" \
  --model "${MODEL}" \
  --port ${PORT} \
  --host 0.0.0.0 \
  --dtype bfloat16 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.90 \
  --trust-remote-code \
  --enable-auto-tool-choice \
  --tool-call-parser hermes

echo "==> Container started. Waiting for server to be ready (model download + load)..."

# Poll /health — up to 10 min for first run (model download)
for i in \$(seq 1 60); do
  if curl -sf http://localhost:${PORT}/health >/dev/null 2>&1; then
    echo "==> Server is UP at http://165.245.128.117:${PORT}/v1"
    echo "    Set: VLLM_ENDPOINT=http://165.245.128.117:${PORT}/v1"
    exit 0
  fi
  echo "    Waiting... (\${i}/60) — check logs: docker logs ${CONTAINER}"
  sleep 10
done

echo "==> Timed out. Last logs:"
docker logs --tail 40 "${CONTAINER}"
exit 1
EOF
