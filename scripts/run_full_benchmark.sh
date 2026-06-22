#!/bin/bash
# Run full benchmark across all patients with multiple models.
#
# Prerequisites:
#   - LM Studio running on localhost:1234 with model loaded
#   - OR Ollama running on localhost:11434
#   - ANTHROPIC_API_KEY / OPENAI_API_KEY set in .env
#
# Usage:
#   bash scripts/run_full_benchmark.sh
#   bash scripts/run_full_benchmark.sh "anthropic:claude-haiku-4-5-20251001 lmstudio:qwen2.5-7b-instruct"

set -euo pipefail

MODELS="${1:-anthropic:claude-haiku-4-5-20251001 lmstudio:qwen2.5-7b-instruct}"

echo "========================================"
echo "  Medical Record Summarization Benchmark"
echo "========================================"
echo "Models: $MODELS"
echo ""

python -m scripts.benchmark_models \
    --all-patients \
    --models $MODELS

echo ""
echo "Done! Results in data/benchmark/"
