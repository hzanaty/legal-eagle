#!/bin/zsh
# Legal Eagle scheduler entrypoint wrapper
# Purpose: Provide a stable command for OS schedulers (launchd/systemd/cron)
# to invoke the Python scheduler with correct working directory and PATH.
#
# Usage:
#   scripts/scheduler_entry.sh            # run all active profiles scheduled for today
#   scripts/scheduler_entry.sh --profile-id 1   # run a single profile
#   scripts/scheduler_entry.sh --ignore-schedule # run all active profiles ignoring schedule_day
#
# Optional environment variables:
#   DISABLE_TWEETS=1   # disable tweet collection during scheduled runs

# Absolute project root (tailored to current environment)
PROJECT_ROOT="/Users/i077750/Documents/GitHub/legal-eagle"

# Change to project root
cd "$PROJECT_ROOT" || {
  echo "❌ Failed to cd to $PROJECT_ROOT"
  exit 1
}

# If a virtualenv is desired, source it here.
# Uncomment and set VENV_PATH accordingly:
# VENV_PATH="$PROJECT_ROOT/.venv"
# if [ -d "$VENV_PATH" ]; then
#   source "$VENV_PATH/bin/activate"
# fi

# Ensure Python can import project modules
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Run the scheduler
python3 scripts/schedule_runner.py "$@"
