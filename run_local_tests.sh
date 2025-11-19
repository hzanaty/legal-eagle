#!/bin/bash
echo "Setting up Python environment..."
python3 -m pip install --upgrade pip
pip install -r configurations/requirements.txt

echo "Installing Playwright..."
playwright install chromium

export PYTHONPATH="/Users/i077750/Documents/GitHub/legal-eagle"
export OPENAI_API_KEY="your_api_key_here"
echo "Running Legal Eagle Controller..."
python3 agents/agents_controller.py

echo "Local tests completed."
