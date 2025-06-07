#!/usr/bin/env python3
import os, sys, time, subprocess, json, logging, glob
from datetime import datetime, timezone, timedelta

logger = None
lock_file = '/tmp/croncoder.lock'
failed_issues = set()


def run_command(cmd, cwd=None, timeout=None, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=cwd, timeout=timeout)
    if check and result.returncode != 0: raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


class DateRotatingLogger:
    def __init__(self, log_dir='logs', prefix='', days_to_keep=7):
        self.log_dir = log_dir
        self.prefix = prefix
        self.days_to_keep = days_to_keep
        os.makedirs(log_dir, exist_ok=True)
        self._cleanup_old_logs()
    
    
    def _cleanup_old_logs(self):
        cutoff = datetime.now() - timedelta(days=self.days_to_keep)
        pattern = os.path.join(self.log_dir, f"{self.prefix}*.log")
        for file in glob.glob(pattern):
            try:
                date_str = os.path.basename(file).replace(self.prefix, '').replace('.log', '')
                file_date = datetime.strptime(date_str, '%Y-%m-%d')
                if file_date < cutoff: os.remove(file)
            except: pass
    
    
    def get_logger(self, name):
        today = datetime.now().strftime('%Y-%m-%d')
        log_file = os.path.join(self.log_dir, f"{self.prefix}{today}.log")
        
        logger = logging.getLogger(name)
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)
        
        return logger


def setup_logging():
    rotator = DateRotatingLogger(prefix='croncoder-')
    return rotator.get_logger('croncoder')


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
    
    claude_logs_dir = os.path.join(repo_path, 'claude-logs')
    os.makedirs(claude_logs_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime('%Y%m%d-%H%M%S')
    log_file = os.path.join(claude_logs_dir, f'claude-{timestamp}-issue-{issue_number}.log')
    
    cmd = f'echo {repr(prompt)} | claude code --dangerously-skip-permissions'
    start_time = datetime.now()
    
    with open(log_file, 'w') as f:
        f.write(f"=== Claude Code Session Log ===\n")
        f.write(f"Start Time: {start_time}\n")
        f.write(f"Issue: #{issue_number} - {issue_title}\n")
        f.write(f"Repository: {repo_path}\n")
        f.write(f"\n=== PROMPT ===\n{prompt}\n\n=== OUTPUT ===\n")
        f.flush()
        
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                   text=True, bufsize=1, cwd=repo_path)
        
        output = []
        for line in process.stdout:
            f.write(line)
            f.flush()
            output.append(line)
            logger.info(f"Claude: {line.rstrip()}")
        
        try:
            process.wait(timeout=3600)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        
        end_time = datetime.now()
        f.write(f"\n\n=== SESSION END ===\n")
        f.write(f"End Time: {end_time}\n")
        f.write(f"Duration: {end_time - start_time}\n")
        f.write(f"Exit Code: {process.returncode}\n")
    
    output_text = ''.join(output)
    
    if process.returncode != 0:
        error_msg = output_text[:1000] if output_text else "Unknown error"
        if "unauthorized" in error_msg.lower() or "authentication" in error_msg.lower():
            return False, "Check Claude CLI credentials"
        elif "rate limit" in error_msg.lower():
            return False, "Claude rate limit reached"
        elif process.returncode == -9 or "timeout" in error_msg.lower():
            return False, "Issue might be too complex (60-minute timeout reached)"
        return False, f"Claude Code failed: {error_msg}"
    
    return True, output_text


def process_issue(repo_path, issue):
    issue_number = issue['number']
    issue_title = issue['title']
    
    logger.info(f"Processing issue #{issue_number}: {issue_title}")
    
    if issue_number in failed_issues:
        logger.info(f"Skipping previously failed issue #{issue_number}")
        return False
    
    # Post comment on issue before starting work
    comment_result = run_command(
        f'gh issue comment {issue_number} --body "🤖 CronCoder is now working on this issue."',
        cwd=repo_path,
        check=False
    )
    if comment_result.returncode != 0:
        logger.warning(f"Failed to post comment on issue #{issue_number}: {comment_result.stderr}")
    
    logger.info(f"Running Claude Code to handle issue #{issue_number}...")
    success, output = run_claude_code(repo_path, issue_number, issue_title)
    
    if not success:
        failed_issues.add(issue_number)
        logger.error(f"Failed to process issue #{issue_number}: {output}")
        return False
    
    logger.info(f"Successfully processed issue #{issue_number}")
    return True


def main():
    global logger
    logger = setup_logging()
    
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