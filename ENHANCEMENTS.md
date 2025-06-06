# CronCoder Enhancements

## Claude CLI Cron Compatibility

The Claude CLI works from cron with proper environment setup:

1. **Required Environment Variables**:
   - `HOME=/home/ace` - For config files
   - `USER=ace` - For user context
   - `XDG_CONFIG_HOME=$HOME/.config` - For Claude config
   - `PATH` must include `/home/ace/.npm-global/bin`

2. **Implementation in `run_croncoder.sh`**:
   - Sets all required environment variables
   - Logs startup/completion to `logs/cron.log`
   - Preserves exit codes for debugging

## GitHub Rate Limit Handling

The enhanced version (`croncoder_enhanced.py`) includes:

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

## "Manual Intervention Needed" Diagnosis

The enhanced version provides better error diagnostics:

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

## Usage

1. **For better cron compatibility**, use the updated `run_croncoder.sh`
2. **For rate limit awareness**, use `croncoder_enhanced.py`
3. **To skip an issue**, add the label 'croncoder-skip' on GitHub

## Testing

Run the diagnostic script to verify your setup:
```bash
python3 test_claude_cron.py
```

This will test:
- Claude CLI in cron-like environment
- GitHub API rate limits
- Recent error patterns in logs