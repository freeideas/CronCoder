#!/bin/bash
# CronCoder wrapper script for cron execution

# Set HOME explicitly to ensure auth files are found
export HOME=/home/ace

# Source user's bashrc to get proper PATH and environment
if [ -f "$HOME/.bashrc" ]; then
    source "$HOME/.bashrc"
fi

# Change to the script directory
cd /home/ace/prjx/github/croncoder

# Activate virtual environment if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Run the Python script
python croncoder.py

# Exit with the same code as the Python script
exit $?