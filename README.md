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
- **Comprehensive Logging**: Logs all activities to both console and rotating log files
- **GitHub Rate Limit Handling**: Monitors API rate limits and intelligently waits when necessary
- **Enhanced Error Diagnostics**: Provides detailed error messages for Claude CLI failures
- **Skip Functionality**: Can skip issues labeled with 'croncoder-skip'

## Prerequisites

- Python 3.9+
- `gh` CLI tool (authenticated with appropriate permissions)
- Claude Code CLI (authenticated and configured)
- Git configured with push permissions

## Configuration

Create a `config.json` file in the same directory as the script:

```json
{
  "sleep_time": 30,
  "repos_directory": "/path/to/repos",
  "_comment": "sleep_time is in minutes; repos_directory should contain GitHub repositories"
}
```


## Directory Structure

```
.
├── croncoder.py      # Main script
├── config.json       # Configuration file
├── logs/             # Log files (created automatically)
│   └── croncoder.log # Main log file (rotates at 10MB)
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

Or run via the shell script (recommended):

```bash
./run_croncoder.sh
```

Set up as a cron job to run periodically:

```bash
# Run every 30 minutes
*/30 * * * * /path/to/run_croncoder.sh
```

**Note**: Use the shell script (`run_croncoder.sh`) in cron jobs as it properly sets up the environment before running the Python script.

### Claude CLI Cron Compatibility

The Claude CLI requires specific environment variables when running from cron:

1. **Required Environment Variables**:
   - `HOME=/home/ace` - For config files
   - `USER=ace` - For user context
   - `XDG_CONFIG_HOME=$HOME/.config` - For Claude config
   - `PATH` must include `/home/ace/.npm-global/bin`

2. **Implementation in `run_croncoder.sh`**:
   - Sets all required environment variables
   - Logs startup/completion to `logs/cron.log`
   - Preserves exit codes for debugging

### Testing Your Setup

Run the diagnostic script to verify your setup:
```bash
python3 test_claude_cron.py
```

This will test:
- Claude CLI in cron-like environment
- GitHub API rate limits
- Recent error patterns in logs

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

### GitHub Rate Limit Handling

CronCoder includes intelligent rate limit management:

1. **Rate Limit Checking**:
   - Checks rate limits before API calls
   - Calculates wait times when quota is low
   - Implements exponential backoff
   - Logs rate limit status

2. **Smart Waiting**:
   - If rate limit exhausted: waits until reset + 1 minute
   - If < 50 requests remaining: spreads requests evenly
   - Adds 30-second delay between issues

3. **Error Detection**:
   - Detects rate limit errors in API responses
   - Forces 5-minute wait on rate limit errors

### Issue Skip Functionality

To skip an issue from CronCoder processing, add the label 'croncoder-skip' on GitHub.

## Security Considerations

- Ensure `gh` and Git credentials are properly secured
- Run with appropriate file system permissions
- Consider the security implications of automated code changes
- Review Claude Code's changes before deploying to production

## Logging

CronCoder maintains comprehensive logs of all activities:

- **Console Output**: All log messages are displayed in the terminal when running interactively
- **Log Files**: Stored in the `logs/` directory with automatic rotation
  - Main log file: `logs/croncoder.log`
  - Rotates at 10MB, keeping 5 backup files
  - Includes timestamps, log levels, and detailed messages

Example log entries:
```
2025-05-27 22:30:15,123 - INFO - CronCoder started at 2025-05-27 22:30:15.123456
2025-05-27 22:30:15,234 - INFO - Monitoring repositories in: /mnt/c/repos
2025-05-27 22:30:15,345 - INFO - Checking repository: myproject
2025-05-27 22:30:16,456 - INFO - Found 2 open issues in myproject
2025-05-27 22:30:16,567 - INFO - Processing issue #42: Fix memory leak
```

## Error Handling

The script includes cleanup mechanisms to remove lock files even if errors occur, preventing deadlocks in subsequent runs.

### Enhanced Error Diagnostics

CronCoder provides detailed error diagnostics for Claude CLI failures:

1. **Claude Error Categories**:
   - Authentication errors → "Check Claude CLI credentials"
   - Rate limit errors → "Claude rate limit reached"
   - Timeout errors → "Issue might be too complex"
   - Other errors → Shows first 1000 chars of stderr

2. **Improved Error Handling**:
   - Captures Claude stdout/stderr for debugging
   - 30-minute timeout for complex issues
   - Specific error messages for each failure type
   - Logs detailed errors to help diagnose issues

3. **Additional Features**:
   - Skip issues with 'croncoder-skip' label
   - Test command timeout (10 minutes)
   - Better process management with timeouts

## License

[Specify your license here]