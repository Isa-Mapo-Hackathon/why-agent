"""Named constants shared across the agent package.

Per CLAUDE.md: backend names, tool names, scenario IDs live here, not as
magic strings scattered through the code.
"""

BACKEND_MINIMAX = "minimax"
BACKEND_VLLM = "vllm"
BACKEND_REPLAY = "replay"

VALID_BACKENDS = frozenset({BACKEND_MINIMAX, BACKEND_VLLM, BACKEND_REPLAY})

MINIMAX_MODEL = "MiniMax-M1"
MINIMAX_BASE_URL = "https://api.minimaxi.chat/v1"

VLLM_MODEL = "meta-llama/Llama-3.3-70B-Instruct"

ENV_MODEL_BACKEND = "MODEL_BACKEND"
ENV_MINIMAX_API_KEY = "MINIMAX_API_KEY"
ENV_VLLM_ENDPOINT = "VLLM_ENDPOINT"
ENV_SCENARIO_ID = "REPLAY_SCENARIO_ID"
