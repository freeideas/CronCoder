# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CronCoder is an automated GitHub issue resolver that monitors repositories for open issues and uses Claude Code to implement fixes. The main components are:

- `croncoder.py` - Main script that orchestrates the issue resolution process
- `config.yaml` - Configuration file specifying sleep time and repositories directory

## Key Commands

Since the implementation files don't exist yet, here are the expected commands based on the project description:

```bash
# Run the main script
python croncoder.py

# Install dependencies
pip install pyyaml
```

## Architecture

The system follows this workflow:

1. **Lock Management**: Uses PID-based lock files to ensure single instance execution
2. **Repository Scanning**: Iterates through all repositories in the configured directory
3. **Issue Processing**: For each open issue:
   - Refreshes repository to latest main branch
   - Invokes Claude Code to analyze and fix the issue
   - Discovers and runs tests
   - Commits and pushes successful fixes
   - Marks issues as resolved
4. **Loop Control**: Continues processing until no issues remain, then sleeps

## Implementation Notes

When implementing `croncoder.py`, ensure:

- Lock file cleanup in case of errors (use try/finally blocks)
- Proper error handling for git operations
- Safe execution of Claude Code commands
- Test discovery should be flexible to handle different test frameworks
- Commit messages should reference the issue being fixed
- WSL2 path conversion: Automatically convert `/mnt/c/` paths to `C:\` when running Windows commands (e.g., when invoking Claude Code on Windows)

## Dependencies

- Python 3.x with PyYAML
- `gh` CLI (GitHub CLI) - must be authenticated
- Claude Code CLI - must be authenticated
- Git with push permissions to target repositories