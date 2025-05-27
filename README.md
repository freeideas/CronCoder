# CronCoder

An automated GitHub issue resolver that continuously monitors repositories for open issues and uses Claude Code to implement fixes.

## Overview

CronCoder is a Python script designed to run as a scheduled task (e.g., via cron) that:
- Monitors multiple GitHub repositories for open issues
- Automatically attempts to resolve issues using Claude Code
- Runs tests to verify fixes
- Commits and pushes successful fixes
- Marks resolved issues as complete

The script ensures only one instance runs at a time using a PID-based lock file mechanism.

## Features

- **Single Instance Enforcement**: Uses a lock file to prevent multiple concurrent executions
- **Multi-Repository Support**: Monitors all repositories in a configured directory
- **Automated Issue Resolution**: Leverages Claude Code in full agentic mode to analyze and fix issues
- **Test Verification**: Automatically discovers and runs project tests before committing
- **Continuous Processing**: Loops until no open issues remain, then sleeps

## Prerequisites

- Python 3.x
- `gh` CLI tool (authenticated with appropriate permissions)
- Claude Code CLI (authenticated and configured)
- Git configured with push permissions
- PyYAML package (`pip install pyyaml`)

## Configuration

Create a `config.yaml` file in the same directory as the script:

```yaml
sleep_time: 30  # Minutes to sleep when no issues found
repos_directory: /path/to/repos  # Directory containing GitHub repositories
```

**Note for WSL2/Windows users**: The script automatically converts WSL2 paths to Windows paths when needed. For example, `/mnt/c/repos` will be converted to `C:\repos` when running Windows commands.

## Directory Structure

```
.
├── croncoder.py      # Main script
├── config.yaml       # Configuration file
└── README.md         # This file
```

The `repos_directory` should contain subdirectories, each being a cloned GitHub repository. Note that not every subdirectory needs to be a GitHub repository - directories without a `.git` folder will be automatically ignored:

```
/path/to/repos/
├── repo1/          # GitHub repository
├── repo2/          # GitHub repository
├── other-files/    # Non-repository directory (ignored)
└── repo3/          # GitHub repository
```

## Usage

Run the script directly:

```bash
python croncoder.py
```

Or set up as a cron job to run periodically:

```bash
# Run every hour
0 * * * * /usr/bin/python /path/to/croncoder.py
```

## How It Works

1. **Lock Check**: Verifies no other instance is running
2. **Repository Scan**: Checks each repository for open GitHub issues
3. **Issue Processing**: For each open issue:
   - Refreshes repository to latest main branch
   - Uses Claude Code to analyze and implement a fix
   - Discovers and runs appropriate tests
   - If tests pass, commits and pushes the fix
   - Marks the issue as resolved
4. **Loop or Sleep**: If issues were found, loops back to check for more. Otherwise, sleeps for configured duration and exits

## Security Considerations

- Ensure `gh` and Git credentials are properly secured
- Run with appropriate file system permissions
- Consider the security implications of automated code changes
- Review Claude Code's changes before deploying to production

## Error Handling

The script includes cleanup mechanisms to remove lock files even if errors occur, preventing deadlocks in subsequent runs.

## License

[Specify your license here]