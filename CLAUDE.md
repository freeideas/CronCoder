# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CronCoder is an automated GitHub issue resolver that monitors repositories for open issues and uses Claude Code to implement fixes. The main components are:

- `croncoder.py` - Main script that orchestrates the issue resolution process
- `config.json` - Configuration file specifying sleep time and repositories directory

## Key Commands

Since the implementation files don't exist yet, here are the expected commands based on the project description:

```bash
# Run the main script
python croncoder.py

# No dependencies to install - uses only Python standard library
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

## Code Style Guidelines

**IMPORTANT**: This project follows the coding philosophy outlined in `CODE_GUIDELINES.md`. Key principles:

- **Brevity above all**: Fewer lines of code is always better
- **Early returns**: Use early returns and breaks to flatten code structure
- **Minimal exception handling**: Let exceptions bubble up naturally
- **No unnecessary comments**: Code should be self-explanatory
- **3 blank lines between functions**: As specified in the formatting guidelines

Please read `CODE_GUIDELINES.md` before making any changes to ensure consistency.

## Implementation Notes

When implementing `croncoder.py`, ensure:

- Lock file cleanup in case of errors (use try/finally blocks)
- Proper error handling for git operations
- Safe execution of Claude Code commands
- Test discovery should be flexible to handle different test frameworks
- Commit messages should reference the issue being fixed

## Dependencies

- Python 3.9+ (no external dependencies)
- `gh` CLI (GitHub CLI) - must be authenticated
- Claude Code CLI - must be authenticated
- Git with push permissions to target repositories