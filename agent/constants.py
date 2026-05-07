"""Named constants shared across the agent package.

Per CLAUDE.md: backend names, tool names, scenario IDs live here, not as
magic strings scattered through the code.
"""

ENV_PARQUET_DIR = "PARQUET_DIR"
ENV_SEMANTIC_LAYER_PATH = "SEMANTIC_LAYER_PATH"

DEFAULT_PARQUET_DIR = "data/parquet"
DEFAULT_SEMANTIC_LAYER_PATH = "data/semantic_layer.yml"

BACKEND_MINIMAX = "minimax"
BACKEND_VLLM = "vllm"
BACKEND_REPLAY = "replay"

VALID_BACKENDS = frozenset({BACKEND_MINIMAX, BACKEND_VLLM, BACKEND_REPLAY})

MINIMAX_MODEL = "MiniMax-M2.7"
MINIMAX_BASE_URL = "https://api.minimaxi.chat/v1"

VLLM_MODEL = "meta-llama/Llama-3.3-70B-Instruct"

ENV_MODEL_BACKEND = "MODEL_BACKEND"
ENV_MINIMAX_API_KEY = "MINIMAX_API_KEY"
ENV_VLLM_ENDPOINT = "VLLM_ENDPOINT"
ENV_SCENARIO_ID = "REPLAY_SCENARIO_ID"

DEMO_QUESTIONS = [
    "Why did campaign 230 underperform campaign 150? They're both bulk sale-out emails sent within a week of each other, similar volume, similar audience profile. Open rate gap: 27% vs 8%.",
    "Why did message open rate drop in the most recent campaign?",
    "Why does campaign 361 convert 60x better than campaign 296?",
    "Why is weekend engagement consistently lower than weekday?",
]
