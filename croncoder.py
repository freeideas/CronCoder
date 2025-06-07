#!/usr/bin/env python3
import os, sys, time, subprocess, json, logging
from datetime import datetime, timezone

logger = logging.getLogger('croncoder')
lock_file = '/tmp/croncoder.lock'
failed_issues = set()


def run_command(cmd, cwd=None, timeout=None, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    if check and result.returncode != 0: raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def setup_logging():
    os.makedirs('logs', exist_ok=True)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s',
                       handlers=[logging.StreamHandler(), logging.FileHandler('logs/croncoder.log')])


def acquire_lock():
    if os.path.exists(lock_file):
        with open(lock_file) as f: pid = int(f.read().strip())
        try:
            os.kill(pid, 0)
            logger.error(f"Another instance (PID {pid}) is already running")
            sys.exit(1)
        except ProcessLookupError:
            logger.info("Removing stale lock file")
            os.remove(lock_file)
    
    with open(lock_file, 'w') as f: f.write(str(os.getpid()))


def release_lock():
    if os.path.exists(lock_file): os.remove(lock_file)


def check_rate_limit():
    result = run_command("gh api rate_limit", check=False)
    if result.returncode != 0: return True
    
    data = json.loads(result.stdout)
    core = data['resources']['core']
    graphql = data['resources']['graphql']
    
    core_remaining = core['remaining']
    graphql_remaining = graphql['remaining']
    core_reset = datetime.fromtimestamp(core['reset'], tz=timezone.utc)
    graphql_reset = datetime.fromtimestamp(graphql['reset'], tz=timezone.utc)
    
    now = datetime.now(timezone.utc)
    core_minutes = (core_reset - now).total_seconds() / 60
    graphql_minutes = (graphql_reset - now).total_seconds() / 60
    
    logger.info(
        f"GitHub API rate limit - Core: {core_remaining}/{core['limit']}, "
        f"GraphQL: {graphql_remaining}/{graphql['limit']} (resets in {min(core_minutes, graphql_minutes):.1f} min)"
    )
    
    if core_remaining == 0 or graphql_remaining == 0:
        wait_time = max(core_minutes, graphql_minutes) + 1
        logger.warning(f"Rate limit exhausted. Waiting {wait_time:.1f} minutes...")
        time.sleep(wait_time * 60)
        return False
    
    if core_remaining < 50 or graphql_remaining < 50:
        wait_per_request = min(
            core_minutes * 60 / core_remaining, graphql_minutes * 60 / graphql_remaining
        ) if core_remaining > 0 and graphql_remaining > 0 else 60
        logger.info(f"Low rate limit. Waiting {wait_per_request:.1f} seconds between requests")
        time.sleep(wait_per_request)
    
    return True


def get_open_issues(repo_path):
    result = run_command("gh issue list --state open --json number,title,labels", cwd=repo_path, check=False)
    
    if result.returncode != 0:
        if "rate limit" in result.stderr.lower():
            logger.error("GitHub API rate limit hit")
            time.sleep(300)
        return []
    
    issues = json.loads(result.stdout) if result.stdout else []
    return [issue for issue in issues if issue['number'] not in failed_issues and 
            not any(label['name'] == 'croncoder-skip' for label in issue.get('labels', []))]


def run_claude_code(repo_path, issue_number, issue_title):
    prompt = f"""Please help resolve GitHub issue #{issue_number}: {issue_title}

Before starting:
1. Ensure the repository is up to date with the remote (fetch, pull/merge as needed)
2. Make sure you're on the default branch

Then:
1. Analyze and fix the issue
2. Run any relevant tests (check README.md, package.json, Makefile, etc. for test commands)
3. If tests pass and the fix works:
   - Commit your changes with a clear message referencing issue #{issue_number}
   - Push the changes
   - Post a comment on the issue explaining what was fixed
   - Close the issue
4. If you encounter problems:
   - If you see GitHub API rate limit errors:
     * Check rate limit status with: gh api rate_limit | jq '.resources.core'
     * Calculate seconds until reset: echo $(($(gh api rate_limit | jq '.resources.core.reset') - $(date +%s)))
     * Sleep for that duration plus 60 seconds buffer
     * If the calculation fails, default to 'sleep 300' (5 minutes)
   - For other errors, post a comment on the issue explaining what went wrong
   - Do not commit/push incomplete changes

Please handle the complete workflow from start to finish."""
    
    cmd = f'claude code "{repo_path}" "{prompt}"'
    result = run_command(cmd, cwd=repo_path, timeout=1800, check=False)
    
    if result.returncode != 0:
        error_msg = result.stderr[:1000] if result.stderr else "Unknown error"
        if "unauthorized" in error_msg.lower() or "authentication" in error_msg.lower():
            return False, "Check Claude CLI credentials"
        elif "rate limit" in error_msg.lower():
            return False, "Claude rate limit reached"
        elif result.returncode == -9 or "timeout" in error_msg.lower():
            return False, "Issue might be too complex (30-minute timeout reached)"
        return False, f"Claude Code failed: {error_msg}"
    
    return True, result.stdout


def process_issue(repo_path, issue):
    issue_number = issue['number']
    issue_title = issue['title']
    
    logger.info(f"Processing issue #{issue_number}: {issue_title}")
    
    if issue_number in failed_issues:
        logger.info(f"Skipping previously failed issue #{issue_number}")
        return False
    
    logger.info(f"Running Claude Code to handle issue #{issue_number}...")
    success, output = run_claude_code(repo_path, issue_number, issue_title)
    
    if not success:
        failed_issues.add(issue_number)
        logger.error(f"Failed to process issue #{issue_number}: {output}")
        return False
    
    logger.info(f"Successfully processed issue #{issue_number}")
    return True


def main():
    setup_logging()
    
    result = run_command("claude --version", check=False)
    if result.returncode == 0:
        logger.info(f"Claude CLI ready: {result.stdout.strip()}")
    else:
        logger.error("Claude CLI not found or not authenticated")
        sys.exit(1)
    
    logger.info(f"CronCoder started at {datetime.now()}")
    
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if not os.path.exists(config_path):
        logger.error("config.json not found")
        sys.exit(1)
    
    with open(config_path) as f: config = json.load(f)
    sleep_time = config.get('sleep_time', 30)
    repos_dir = config.get('repos_directory', '.')
    
    if not os.path.isdir(repos_dir):
        logger.error(f"Repos directory not found: {repos_dir}")
        sys.exit(1)
    
    logger.info(f"Monitoring repositories in: {repos_dir}")
    
    acquire_lock()
    try:
        while True:
            issues_found = False
            
            for item in os.listdir(repos_dir):
                repo_path = os.path.join(repos_dir, item)
                if not os.path.isdir(repo_path) or not os.path.exists(os.path.join(repo_path, '.git')): continue
                
                logger.info(f"Checking repository: {item}")
                
                if not check_rate_limit(): continue
                
                issues = get_open_issues(repo_path)
                if not issues: continue
                
                issues_found = True
                logger.info(f"Found {len(issues)} open issues in {item}")
                
                for issue in issues:
                    if not check_rate_limit(): break
                    if process_issue(repo_path, issue): time.sleep(30)
            
            if not issues_found:
                logger.info(f"No open issues found. Sleeping for {sleep_time} minutes...")
                time.sleep(sleep_time * 60)
                break
    finally:
        release_lock()
        logger.info("CronCoder finished")

if __name__ == "__main__":
    import atexit
    atexit.register(release_lock)
    main()