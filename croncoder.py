#!/usr/bin/env python3
"""
CronCoder - Automated GitHub issue resolver using Claude Code
"""

import os
import sys
import time
import subprocess
import signal
import atexit
import yaml
import json
from pathlib import Path
from datetime import datetime


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


def run_command(cmd, cwd=None, capture_output=True):
    """Run a shell command and return the result"""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            check=False
        )
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)


def get_open_issues(repo_path):
    """Get list of open issues for a repository"""
    success, stdout, stderr = run_command("gh issue list --state open --json number,title", cwd=repo_path)
    
    if not success:
        print(f"Failed to get issues: {stderr}")
        return []
    
    try:
        issues = json.loads(stdout)
        return issues
    except json.JSONDecodeError:
        print(f"Failed to parse issues JSON: {stdout}")
        return []


def is_git_repository(path):
    """Check if a directory is a git repository"""
    return os.path.exists(os.path.join(path, '.git'))


def refresh_repository(repo_path):
    """Pull latest changes from main branch"""
    print(f"Refreshing repository: {repo_path}")
    
    # Stash any local changes
    run_command("git stash", cwd=repo_path)
    
    # Checkout main branch (try 'main' first, then 'master')
    success, _, _ = run_command("git checkout main", cwd=repo_path)
    if not success:
        success, _, _ = run_command("git checkout master", cwd=repo_path)
        if not success:
            print("Failed to checkout main/master branch")
            return False
    
    # Pull latest changes
    success, _, stderr = run_command("git pull", cwd=repo_path)
    if not success:
        print(f"Failed to pull latest changes: {stderr}")
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
        print("No test command found, skipping tests")
        return True
    
    print(f"Running tests with: {test_command}")
    success, stdout, stderr = run_command(test_command, cwd=repo_path)
    
    if success:
        print("Tests passed!")
    else:
        print(f"Tests failed:\n{stderr}")
    
    return success


def commit_and_push_fix(repo_path, issue_number):
    """Commit and push the fix for an issue"""
    # Add all changes
    success, _, stderr = run_command("git add -A", cwd=repo_path)
    if not success:
        print(f"Failed to add changes: {stderr}")
        return False
    
    # Create commit message
    commit_message = f"Fix issue #{issue_number} (automated by CronCoder)"
    success, _, stderr = run_command(f'git commit -m "{commit_message}"', cwd=repo_path)
    if not success:
        print(f"Failed to commit: {stderr}")
        return False
    
    # Push changes
    success, _, stderr = run_command("git push", cwd=repo_path)
    if not success:
        print(f"Failed to push: {stderr}")
        return False
    
    print(f"Successfully pushed fix for issue #{issue_number}")
    return True


def mark_issue_resolved(repo_path, issue_number):
    """Mark an issue as resolved"""
    success, _, stderr = run_command(
        f'gh issue close {issue_number} --comment "Resolved automatically by CronCoder"',
        cwd=repo_path
    )
    
    if success:
        print(f"Marked issue #{issue_number} as resolved")
    else:
        print(f"Failed to close issue: {stderr}")
    
    return success


def process_issue(repo_path, issue):
    """Process a single issue using Claude Code"""
    issue_number = issue['number']
    issue_title = issue['title']
    
    print(f"\nProcessing issue #{issue_number}: {issue_title}")
    
    # Refresh repository to latest state
    if not refresh_repository(repo_path):
        print("Failed to refresh repository")
        return False
    
    # Convert path for Windows if needed
    windows_path = convert_wsl_to_windows_path(repo_path)
    
    # Use Claude Code to fix the issue
    claude_prompt = f"Please fix GitHub issue #{issue_number}: {issue_title}. Run any necessary tests to verify your fix."
    
    # Run Claude Code in the repository directory
    print(f"Running Claude Code to fix issue #{issue_number}...")
    
    # Use full path to claude executable with non-interactive mode
    claude_path = "/home/human/.claude/local/claude"
    if os.path.exists(claude_path):
        claude_cmd = f'{claude_path} --dangerously-skip-permissions -p "{claude_prompt}"'
    else:
        claude_cmd = f'claude --dangerously-skip-permissions -p "{claude_prompt}"'
    
    # Change to repo directory and run Claude
    original_cwd = os.getcwd()
    try:
        os.chdir(repo_path)
        success, stdout, stderr = run_command(claude_cmd, capture_output=False)
    finally:
        os.chdir(original_cwd)
    
    if not success:
        print(f"Claude Code failed to fix issue: {stderr}")
        return False
    
    # Run tests to verify the fix
    if not run_tests(repo_path):
        print("Tests failed after fix, reverting changes")
        run_command("git checkout .", cwd=repo_path)
        return False
    
    # Commit and push the fix
    if not commit_and_push_fix(repo_path, issue_number):
        print("Failed to commit and push fix")
        return False
    
    # Mark issue as resolved
    mark_issue_resolved(repo_path, issue_number)
    
    return True


def scan_repositories(repos_dir, failed_issues=None):
    """Scan all repositories and process their issues"""
    issues_found = False
    if failed_issues is None:
        failed_issues = set()
    
    # Iterate through all subdirectories
    for item in os.listdir(repos_dir):
        repo_path = os.path.join(repos_dir, item)
        
        # Skip if not a directory or not a git repository
        if not os.path.isdir(repo_path) or not is_git_repository(repo_path):
            continue
        
        print(f"\nChecking repository: {item}")
        
        # Get open issues
        issues = get_open_issues(repo_path)
        
        if not issues:
            print(f"No open issues found in {item}")
            continue
        
        issues_found = True
        print(f"Found {len(issues)} open issues in {item}")
        
        # Process each issue
        for issue in issues:
            issue_key = f"{item}#{issue['number']}"
            
            # Skip if we've already failed this issue
            if issue_key in failed_issues:
                print(f"Skipping previously failed issue #{issue['number']}")
                continue
            
            try:
                success = process_issue(repo_path, issue)
                if not success:
                    failed_issues.add(issue_key)
            except Exception as e:
                print(f"Error processing issue #{issue['number']}: {e}")
                failed_issues.add(issue_key)
                continue
    
    return issues_found, failed_issues


def main():
    """Main function"""
    # Load configuration
    config_file = os.environ.get('CRONCODER_CONFIG', 'config.yaml')
    config_path = os.path.join(os.path.dirname(__file__), config_file)
    
    if not os.path.exists(config_path):
        print("Error: config.yaml not found")
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    sleep_time = config.get('sleep_time', 30)
    repos_dir = config.get('repos_directory', '.')
    
    # Verify repos directory exists
    if not os.path.exists(repos_dir):
        print(f"Error: Repository directory not found: {repos_dir}")
        sys.exit(1)
    
    # Acquire lock
    lock = LockFile()
    if not lock.acquire():
        print("Another instance of CronCoder is already running")
        sys.exit(0)
    
    print(f"CronCoder started at {datetime.now()}")
    print(f"Monitoring repositories in: {repos_dir}")
    
    try:
        # Track failed issues across loops
        failed_issues = set()
        
        # Main loop
        while True:
            issues_found, failed_issues = scan_repositories(repos_dir, failed_issues)
            
            if not issues_found:
                print(f"\nNo open issues found. Sleeping for {sleep_time} minutes...")
                time.sleep(sleep_time * 60)
                break  # Exit after sleep
            
            # Check if all issues have failed
            if failed_issues and not any(issue for issue in issues_found):
                print(f"\nAll remaining issues have failed. Sleeping for {sleep_time} minutes...")
                time.sleep(sleep_time * 60)
                break
            
            # If issues were found and processed, loop again immediately
            print("\nIssues were processed, checking for more...")
    
    except KeyboardInterrupt:
        print("\nCronCoder interrupted by user")
    except Exception as e:
        print(f"\nCronCoder error: {e}")
        raise
    finally:
        lock.release()
        print(f"\nCronCoder finished at {datetime.now()}")


if __name__ == "__main__":
    main()