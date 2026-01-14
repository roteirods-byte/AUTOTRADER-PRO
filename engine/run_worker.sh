#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export DATA_DIR="${DATA_DIR:-$(pwd)/data}"
python3 -m engine.worker_pro
