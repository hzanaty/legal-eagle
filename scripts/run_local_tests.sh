#!/bin/bash
# Legal Eagle Local Test Runner
# Purpose: Set up environment and run the full pipeline for development/testing
# Usage: bash scripts/run_local_tests.sh (run from project root or scripts/ directory)

# Get absolute path to project root (works regardless of where script is run from)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "📂 Project root: $PROJECT_ROOT"
cd "$PROJECT_ROOT" || {
  echo "❌ Failed to cd to project root"
  exit 1
}

echo "🐍 Setting up Python environment..."
python3 -m pip install --upgrade pip
pip install -r configurations/requirements.txt

echo "🎭 Installing Playwright..."
playwright install chromium

# Set environment variables
export PYTHONPATH="$PROJECT_ROOT"
export OPENAI_API_KEY="${OPENAI_API_KEY:-your_api_key_here}"

echo "🦅 Running Legal Eagle Controller..."
python3 agents/agents_controller.py

echo "✅ Local tests completed."
