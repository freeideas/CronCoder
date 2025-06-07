#!/bin/bash
# CronCoder wrapper script for cron execution

# Set HOME explicitly to ensure auth files are found
export HOME=/home/ace
export USER=ace

# Set minimal environment for Claude CLI
export XDG_CONFIG_HOME=$HOME/.config
export PATH="/home/ace/.npm-global/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Source user's bashrc to get additional environment if needed
if [ -f "$HOME/.bashrc" ]; then
    source "$HOME/.bashrc"
fi

# Change to the script directory
cd /home/ace/prjx/croncoder

# No virtual environment needed - using only Python standard library

# Log startup
echo "$(date): CronCoder starting from cron" >> logs/cron.log

# Run the Python script
python croncoder.py

# Capture exit code
EXIT_CODE=$?

# Log completion
echo "$(date): CronCoder finished with exit code $EXIT_CODE" >> logs/cron.log

# Exit with the same code as the Python script
exit $EXIT_CODE