#!/usr/bin/env python3
"""
Enhanced CronCoder - Automated GitHub issue resolver using Claude Code
with improved error handling and rate limit awareness
"""

import os
import sys
import time
import subprocess
import signal
import atexit
import yaml
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime, timezone
import re


def setup_logging():
    """Setup logging configuration with file and console output"""
    # Create logs directory if it doesn't exist
    log_dir = os.path.join(os.path.dirname(__file__), 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Setup logger
    logger = logging.getLogger('croncoder')
    logger.setLevel(logging.INFO)
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    
    # File handler with rotation (10MB max, keep 5 backups)
    log_file = os.path.join(log_dir, 'croncoder.log')
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10*1024*1024, backupCount=5
    )
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    
    # Add handlers
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger


# Initialize logger
logger = setup_logging()


class LockFile:
    """Manages a PID-based lock file to ensure single instance execution"""
    
    def __init__(self, lock_path="croncoder.lock"):
        self.lock_path = lock_path
        self.locked = False
        
    def acquire(self):
        """Acquire the lock by writing our PID to the lock file"""
        if os.path.exists(self.lock_path):
            # Check if the PID in the lock file is still running
            try:
                with open(self.lock_path, 'r') as f:
                    old_pid = int(f.read().strip())
                
                # Check if process exists
                try:
                    os.kill(old_pid, 0)
                    # Process exists, we cannot acquire lock
                    return False
                except OSError:
                    # Process doesn't exist, we can remove the stale lock
                    os.remove(self.lock_path)
            except (ValueError, IOError):
                # Invalid lock file, remove it
                os.remove(self.lock_path)
        
        # Write our PID
        with open(self.lock_path, 'w') as f:
            f.write(str(os.getpid()))
        
        self.locked = True
        # Register cleanup
        atexit.register(self.release)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)
        
        return True
    
    def release(self):
        """Release the lock by removing the lock file"""
        if self.locked and os.path.exists(self.lock_path):
            try:
                # Verify it's our lock before removing
                with open(self.lock_path, 'r') as f:
                    pid = int(f.read().strip())
                if pid == os.getpid():
                    os.remove(self.lock_path)
                    self.locked = False
            except (ValueError, IOError, OSError):
                pass
    
    def _signal_handler(self, signum, frame):
        """Handle termination signals"""
        self.release()
        sys.exit(0)


def check_github_rate_limit():
    """Check GitHub API rate limits and return wait time if needed"""
    try:
        result = subprocess.run(
            ['gh', 'api', 'rate_limit'],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            # If we can't check rate limits, assume we're rate limited
            if "rate limit" in result.stderr.lower():
                logger.error("Hit rate limit while checking rate limits!")
                return 3600  # Wait 1 hour
            logger.warning(f"Failed to check rate limits: {result.stderr}")
            return 0
        
        data = json.loads(result.stdout)
        
        # Check both core and GraphQL limits
        core = data['resources']['core']
        graphql = data['resources'].get('graphql', core)  # Fallback to core if no graphql
        
        # Use the more restrictive limit
        core_remaining = core['remaining']
        graphql_remaining = graphql['remaining']
        remaining = min(core_remaining, graphql_remaining)
        
        # Use the earliest reset time
        core_reset = core['reset']
        graphql_reset = graphql.get('reset', core_reset)
        reset_timestamp = min(core_reset, graphql_reset)
        
        reset_time = datetime.fromtimestamp(reset_timestamp, tz=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_until_reset = max(0, (reset_time - current_time).total_seconds())
        
        logger.info(f"GitHub API rate limit - Core: {core_remaining}/{core['limit']}, GraphQL: {graphql_remaining}/{graphql.get('limit', 'N/A')} (resets in {time_until_reset/60:.1f} min)")
        
        # If we're low on quota, calculate wait time
        if remaining < 50:
            if remaining == 0:
                # No quota left, must wait until reset
                wait_time = time_until_reset + 60  # Add 1 minute buffer
                logger.warning(f"GitHub API rate limit exhausted! Waiting {wait_time/60:.1f} minutes until reset")
                return wait_time
            else:
                # Calculate wait time to spread remaining requests
                wait_time = time_until_reset / remaining
                if wait_time > 10:  # Only wait if it's more than 10 seconds
                    logger.warning(f"Low GitHub API quota ({remaining} left). Adding {wait_time:.1f}s delay between requests")
                    return wait_time
        
        return 0
        
    except Exception as e:
        logger.error(f"Error checking rate limit: {e}")
        return 0


def setup_claude_environment():
    """Ensure Claude CLI has proper environment variables"""
    # Add Claude CLI to PATH if not present
    claude_path = "/home/ace/.npm-global/bin"
    if claude_path not in os.environ.get('PATH', ''):
        os.environ['PATH'] = f"{claude_path}:{os.environ.get('PATH', '')}"
    
    # Ensure config directory is set
    if 'XDG_CONFIG_HOME' not in os.environ:
        os.environ['XDG_CONFIG_HOME'] = os.path.expanduser('~/.config')
    
    # Test Claude CLI
    try:
        result = subprocess.run(['claude', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            logger.info(f"Claude CLI ready: {result.stdout.strip()}")
            return True
        else:
            logger.error(f"Claude CLI test failed: {result.stderr}")
            return False
    except FileNotFoundError:
        logger.error("Claude CLI not found in PATH")
        return False


def convert_wsl_to_windows_path(path):
    """Convert WSL2 path to Windows path if needed"""
    path_str = str(path)
    if path_str.startswith('/mnt/'):
        # Extract drive letter and rest of path
        parts = path_str.split('/')
        if len(parts) > 2 and len(parts[2]) == 1:
            drive = parts[2].upper()
            rest = '\\'.join(parts[3:])
            return f"{drive}:\\{rest}" if rest else f"{drive}:\\"
    return path_str


def run_command(cmd, cwd=None, capture_output=True, timeout=300):
    """Run a shell command and return the result with timeout"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            check=False,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        logger.error(f"Command timed out after {timeout} seconds: {cmd}")
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def get_open_issues(repo_path):
    """Get list of open issues for a repository"""
    # Check rate limit before API call
    wait_time = check_github_rate_limit()
    if wait_time > 0:
        time.sleep(wait_time)
    
    success, stdout, stderr = run_command("gh issue list --state open --json number,title,labels", cwd=repo_path)
    
    if not success:
        if "rate limit" in stderr.lower() or "api rate limit exceeded" in stderr.lower():
            logger.error("GitHub API rate limit hit while fetching issues")
            # Return None to indicate rate limit error
            return None
        logger.error(f"Failed to get issues: {stderr}")
        return []
    
    try:
        issues = json.loads(stdout)
        # Filter out issues with 'croncoder-skip' label
        filtered_issues = []
        for issue in issues:
            labels = [label.get('name', '') for label in issue.get('labels', [])]
            if 'croncoder-skip' not in labels:
                filtered_issues.append(issue)
            else:
                logger.info(f"Skipping issue #{issue['number']} due to 'croncoder-skip' label")
        return filtered_issues
    except json.JSONDecodeError:
        logger.error(f"Failed to parse issues JSON: {stdout}")
        return []


def get_issue_comments(repo_path, issue_number):
    """Get all comments for a specific issue"""
    success, stdout, stderr = run_command(
        f"gh issue view {issue_number} --json comments --jq '.comments'", 
        cwd=repo_path
    )
    
    if not success:
        logger.error(f"Failed to get issue comments: {stderr}")
        return []
    
    try:
        comments = json.loads(stdout)
        return comments
    except json.JSONDecodeError:
        logger.error(f"Failed to parse comments JSON: {stdout}")
        return []


def get_issue_details(repo_path, issue_number):
    """Get full details of an issue including body"""
    success, stdout, stderr = run_command(
        f"gh issue view {issue_number} --json number,title,body", 
        cwd=repo_path
    )
    
    if not success:
        logger.error(f"Failed to get issue details: {stderr}")
        return None
    
    try:
        issue = json.loads(stdout)
        return issue
    except json.JSONDecodeError:
        logger.error(f"Failed to parse issue JSON: {stdout}")
        return None


def check_recent_attempt(repo_path, issue_number, cooldown_hours=1):
    """Check if CronCoder has attempted this issue recently"""
    comments = get_issue_comments(repo_path, issue_number)
    
    # Look for CronCoder's "working on it" comment
    croncoder_pattern = r"🤖 CronCoder is now working on this issue"
    
    for comment in reversed(comments):  # Check most recent first
        if croncoder_pattern in comment.get('body', ''):
            # Parse the timestamp
            created_at = comment.get('createdAt', '')
            if created_at:
                try:
                    # GitHub timestamps are in ISO format with Z suffix
                    comment_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    current_time = datetime.now(timezone.utc)
                    time_diff = current_time - comment_time
                    
                    if time_diff.total_seconds() < (cooldown_hours * 3600):
                        logger.info(f"Issue #{issue_number} was attempted {time_diff.total_seconds()/60:.1f} minutes ago, skipping")
                        return True
                except Exception as e:
                    logger.error(f"Error parsing timestamp: {e}")
    
    return False


def is_git_repository(path):
    """Check if a directory is a git repository"""
    return os.path.exists(os.path.join(path, '.git'))


def refresh_repository(repo_path):
    """Pull latest changes from main branch"""
    logger.info(f"Refreshing repository: {repo_path}")
    
    # Stash any local changes
    run_command("git stash", cwd=repo_path)
    
    # Checkout main branch (try 'main' first, then 'master')
    success, _, _ = run_command("git checkout main", cwd=repo_path)
    if not success:
        success, _, _ = run_command("git checkout master", cwd=repo_path)
        if not success:
            logger.error("Failed to checkout main/master branch")
            return False
    
    # Pull latest changes
    success, _, stderr = run_command("git pull", cwd=repo_path)
    if not success:
        logger.error(f"Failed to pull latest changes: {stderr}")
        return False
    
    return True


def discover_test_command(repo_path):
    """Discover the appropriate test command for the repository"""
    # Check for common test files and configurations
    checks = [
        ("package.json", "npm test"),
        ("Makefile", "make test"),
        ("setup.py", "python -m pytest"),
        ("pyproject.toml", "pytest"),
        ("Cargo.toml", "cargo test"),
        ("go.mod", "go test ./..."),
    ]
    
    for file, command in checks:
        if os.path.exists(os.path.join(repo_path, file)):
            # For npm, check if test script exists
            if file == "package.json":
                try:
                    with open(os.path.join(repo_path, file), 'r') as f:
                        package = json.load(f)
                        if "scripts" in package and "test" in package["scripts"]:
                            return command
                except:
                    pass
            else:
                return command
    
    # Check for test directories
    if os.path.exists(os.path.join(repo_path, "tests")):
        return "pytest tests/"
    elif os.path.exists(os.path.join(repo_path, "test")):
        return "python -m unittest discover test/"
    
    return None


def run_tests(repo_path):
    """Run tests for the repository"""
    test_command = discover_test_command(repo_path)
    
    if not test_command:
        logger.info("No test command found, skipping tests")
        return True
    
    logger.info(f"Running tests with: {test_command}")
    success, stdout, stderr = run_command(test_command, cwd=repo_path, timeout=600)  # 10 minute timeout
    
    if success:
        logger.info("Tests passed!")
    else:
        logger.error(f"Tests failed:\n{stderr}")
    
    return success


def commit_and_push_fix(repo_path, issue_number):
    """Commit and push the fix for an issue"""
    # Add all changes
    success, _, stderr = run_command("git add -A", cwd=repo_path)
    if not success:
        logger.error(f"Failed to add changes: {stderr}")
        return False
    
    # Create commit message
    commit_message = f"Fix issue #{issue_number} (automated by CronCoder)"
    success, _, stderr = run_command(f'git commit -m "{commit_message}"', cwd=repo_path)
    if not success:
        logger.error(f"Failed to commit: {stderr}")
        return False
    
    # Push changes
    success, _, stderr = run_command("git push", cwd=repo_path)
    if not success:
        logger.error(f"Failed to push: {stderr}")
        return False
    
    logger.info(f"Successfully pushed fix for issue #{issue_number}")
    return True


def post_issue_comment(repo_path, issue_number, comment):
    """Post a comment to a GitHub issue"""
    # Escape quotes in the comment
    escaped_comment = comment.replace('"', '\\"')
    success, _, stderr = run_command(
        f'gh issue comment {issue_number} --body "{escaped_comment}"',
        cwd=repo_path
    )
    
    if success:
        logger.info(f"Posted comment to issue #{issue_number}")
    else:
        logger.error(f"Failed to post comment: {stderr}")
    
    return success


def mark_issue_resolved(repo_path, issue_number):
    """Mark an issue as resolved"""
    success, _, stderr = run_command(
        f'gh issue close {issue_number} --comment "Resolved automatically by CronCoder"',
        cwd=repo_path
    )
    
    if success:
        logger.info(f"Marked issue #{issue_number} as resolved")
    else:
        logger.error(f"Failed to close issue: {stderr}")
    
    return success


def process_issue(repo_path, issue):
    """Process a single issue using Claude Code"""
    issue_number = issue['number']
    issue_title = issue['title']
    
    logger.info(f"Processing issue #{issue_number}: {issue_title}")
    
    # Check if we've attempted this issue recently
    if check_recent_attempt(repo_path, issue_number):
        logger.info(f"Issue #{issue_number} was attempted recently, skipping for now")
        return False
    
    # Get full issue details including body
    issue_details = get_issue_details(repo_path, issue_number)
    if issue_details:
        issue_body = issue_details.get('body', '')
    else:
        issue_body = ''
    
    # Post initial "working on it" comment
    post_issue_comment(repo_path, issue_number, 
        "🤖 CronCoder is now working on this issue. I'll analyze the problem and implement a fix using Claude Code.")
    
    # Refresh repository to latest state
    if not refresh_repository(repo_path):
        logger.error("Failed to refresh repository")
        post_issue_comment(repo_path, issue_number, 
            "❌ Failed to refresh repository to latest state. Please check repository access.")
        return False
    
    # Convert path for Windows if needed
    windows_path = convert_wsl_to_windows_path(repo_path)
    
    # Use Claude Code to fix the issue
    claude_prompt = f"Please fix GitHub issue #{issue_number}: {issue_title}"
    if issue_body:
        claude_prompt += f"\n\nIssue description:\n{issue_body}"
    claude_prompt += "\n\nRun any necessary tests to verify your fix."
    
    # Run Claude Code in the repository directory
    logger.info(f"Running Claude Code to fix issue #{issue_number}...")
    post_issue_comment(repo_path, issue_number, 
        "🔍 Analyzing the issue and generating a fix with Claude Code...")
    
    # Use claude executable with proper error capture
    claude_cmd = f'claude -p "{claude_prompt}"'
    
    # Change to repo directory and run Claude
    original_cwd = os.getcwd()
    try:
        os.chdir(repo_path)
        # Capture output to help diagnose "manual intervention" errors
        success, stdout, stderr = run_command(claude_cmd, capture_output=True, timeout=1800)  # 30 minute timeout
        
        if not success:
            logger.error(f"Claude Code failed to fix issue #{issue_number}")
            logger.error(f"Claude command: {claude_cmd[:100]}...")
            logger.error(f"Exit code: {success}")
            logger.error(f"Claude stdout length: {len(stdout)} chars")
            logger.error(f"Claude stderr: {stderr[:2000]}")  # Log first 2000 chars of error
            
            # Save full output for debugging
            debug_file = os.path.join(os.path.dirname(__file__), 'logs', f'claude_error_{issue_number}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt')
            try:
                with open(debug_file, 'w') as f:
                    f.write(f"Issue: #{issue_number}\n")
                    f.write(f"Command: {claude_cmd}\n")
                    f.write(f"Working Directory: {repo_path}\n")
                    f.write(f"Exit Code: {success}\n")
                    f.write(f"\n--- STDOUT ({len(stdout)} chars) ---\n")
                    f.write(stdout)
                    f.write(f"\n--- STDERR ({len(stderr)} chars) ---\n")
                    f.write(stderr)
                logger.info(f"Full Claude output saved to: {debug_file}")
            except Exception as e:
                logger.error(f"Failed to save debug output: {e}")
            
            # Check for specific error patterns
            error_lower = stderr.lower()
            if "authentication" in error_lower or "unauthorized" in error_lower or "please log in" in error_lower:
                error_msg = "❌ Claude authentication error. Please check Claude CLI credentials."
                logger.error("DIAGNOSIS: Claude CLI needs re-authentication")
            elif "rate limit" in error_lower or "too many requests" in error_lower:
                error_msg = "❌ Claude rate limit reached. Will retry later."
                logger.error("DIAGNOSIS: Claude API rate limit hit")
            elif "timeout" in error_lower or "timed out" in error_lower:
                error_msg = "❌ Claude request timed out. The issue might be too complex."
                logger.error("DIAGNOSIS: Claude request timeout")
            elif "no such file or directory" in error_lower:
                error_msg = "❌ Claude CLI not found. Please check installation."
                logger.error("DIAGNOSIS: Claude CLI binary not found in PATH")
            elif "permission denied" in error_lower:
                error_msg = "❌ Permission denied running Claude CLI."
                logger.error("DIAGNOSIS: Claude CLI permission issue")
            elif stderr.strip() == "" and stdout.strip() == "":
                error_msg = "❌ Claude CLI returned no output. It may need re-authentication or there's a session issue."
                logger.error("DIAGNOSIS: Claude CLI silent failure - likely auth issue")
            else:
                error_msg = f"❌ Claude Code encountered an error. Check logs for details. Error preview: {stderr[:200]}"
                logger.error("DIAGNOSIS: Unknown Claude error - check debug file")
            
            post_issue_comment(repo_path, issue_number, error_msg)
            return False
            
    finally:
        os.chdir(original_cwd)
    
    # Run tests to verify the fix
    post_issue_comment(repo_path, issue_number, 
        "🧪 Running tests to verify the fix...")
    
    if not run_tests(repo_path):
        logger.warning("Tests failed after fix, reverting changes")
        run_command("git checkout .", cwd=repo_path)
        post_issue_comment(repo_path, issue_number, 
            "⚠️ Tests failed after applying the fix. Reverting changes. This issue may require manual review.")
        return False
    
    # Commit and push the fix
    post_issue_comment(repo_path, issue_number, 
        "✅ Tests passed! Committing and pushing the fix...")
    
    if not commit_and_push_fix(repo_path, issue_number):
        print("Failed to commit and push fix")
        post_issue_comment(repo_path, issue_number, 
            "❌ Failed to commit and push the fix. Please check repository permissions.")
        return False
    
    # Post final success message before closing
    post_issue_comment(repo_path, issue_number, 
        "🎉 Successfully fixed and pushed the solution! The fix has been tested and committed. Closing this issue.")
    
    # Mark issue as resolved
    mark_issue_resolved(repo_path, issue_number)
    
    return True


def scan_repositories(repos_dir, failed_issues=None):
    """Scan all repositories and process their issues"""
    issues_found = False
    rate_limit_hit = False
    if failed_issues is None:
        failed_issues = set()
    
    # Track if we found any processable issues (not failed)
    processable_issues_found = False
    
    # Iterate through all subdirectories
    for item in os.listdir(repos_dir):
        repo_path = os.path.join(repos_dir, item)
        
        # Skip if not a directory or not a git repository
        if not os.path.isdir(repo_path) or not is_git_repository(repo_path):
            continue
        
        logger.info(f"Checking repository: {item}")
        
        # Get open issues
        issues = get_open_issues(repo_path)
        
        # Check if we hit rate limit
        if issues is None:
            rate_limit_hit = True
            continue
        
        if not issues:
            logger.info(f"No open issues found in {item}")
            continue
        
        issues_found = True
        logger.info(f"Found {len(issues)} open issues in {item}")
        
        # Process each issue
        for issue in issues:
            issue_key = f"{item}#{issue['number']}"
            
            # Skip if we've already failed this issue in this session
            if issue_key in failed_issues:
                logger.info(f"Skipping previously failed issue #{issue['number']} in this session")
                continue
            
            # Check if we've attempted this issue recently (even in previous sessions)
            if check_recent_attempt(repo_path, issue['number']):
                logger.info(f"Issue #{issue['number']} was attempted recently, skipping")
                continue
            
            # We found at least one issue we can process
            processable_issues_found = True
            
            try:
                success = process_issue(repo_path, issue)
                if not success:
                    failed_issues.add(issue_key)
                    
                # Add delay between issues to avoid rate limits
                time.sleep(30)  # 30 second delay between issues
                
            except Exception as e:
                logger.error(f"Error processing issue #{issue['number']}: {e}")
                failed_issues.add(issue_key)
                continue
    
    return issues_found, failed_issues, processable_issues_found, rate_limit_hit


def main():
    """Main function"""
    # Setup Claude environment first
    if not setup_claude_environment():
        logger.error("Failed to setup Claude CLI environment")
        sys.exit(1)
    
    # Load configuration
    config_file = os.environ.get('CRONCODER_CONFIG', 'config.yaml')
    config_path = os.path.join(os.path.dirname(__file__), config_file)
    
    if not os.path.exists(config_path):
        logger.error(f"Error: {config_file} not found")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    sleep_time = config.get('sleep_time', 30)
    repos_dir = config.get('repos_directory', '.')
    
    # Verify repos directory exists
    if not os.path.exists(repos_dir):
        logger.error(f"Error: Repository directory not found: {repos_dir}")
        sys.exit(1)
    
    # Acquire lock
    lock = LockFile()
    if not lock.acquire():
        logger.info("Another instance of CronCoder is already running")
        sys.exit(0)
    
    logger.info(f"CronCoder started at {datetime.now()}")
    logger.info(f"Monitoring repositories in: {repos_dir}")
    
    try:
        # Track failed issues across loops
        failed_issues = set()
        
        # Main loop
        while True:
            issues_found, failed_issues, processable_issues_found, rate_limit_hit = scan_repositories(repos_dir, failed_issues)
            
            # If we hit GitHub rate limit, wait longer
            if rate_limit_hit:
                logger.warning(f"GitHub API rate limit hit. Sleeping for {sleep_time} minutes...")
                time.sleep(sleep_time * 60)
                break  # Exit after sleep
            
            # If no issues found at all
            if not issues_found:
                logger.info(f"No open issues found. Sleeping for {sleep_time} minutes...")
                time.sleep(sleep_time * 60)
                break  # Exit after sleep
            
            # If we found issues but none are processable (all failed or recently attempted)
            if issues_found and not processable_issues_found:
                logger.info(f"All issues are either failed or recently attempted. Sleeping for {sleep_time} minutes...")
                time.sleep(sleep_time * 60)
                break  # Exit to avoid infinite loop
            
            # If issues were found and processed, loop again immediately
            logger.info("Issues were processed, checking for more...")
    
    except KeyboardInterrupt:
        logger.info("CronCoder interrupted by user")
    except Exception as e:
        logger.error(f"CronCoder error: {e}")
        raise
    finally:
        lock.release()
        logger.info(f"CronCoder finished at {datetime.now()}")


if __name__ == "__main__":
    main()