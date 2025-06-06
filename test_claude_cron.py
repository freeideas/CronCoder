#!/usr/bin/env python3
"""
Test script to diagnose Claude CLI behavior in cron-like environments
and GitHub rate limit handling
"""

import os
import subprocess
import json
import time
from datetime import datetime, timezone

def test_claude_cli():
    """Test Claude CLI in various environments"""
    print("=== Testing Claude CLI ===")
    
    # Test 1: Normal environment
    print("\n1. Testing with normal environment:")
    result = subprocess.run(['claude', '--version'], capture_output=True, text=True)
    print(f"   Exit code: {result.returncode}")
    print(f"   Output: {result.stdout.strip()}")
    print(f"   Error: {result.stderr.strip()}")
    
    # Test 2: Minimal environment (cron-like)
    print("\n2. Testing with minimal environment (cron-like):")
    minimal_env = {
        'HOME': os.environ.get('HOME'),
        'USER': os.environ.get('USER'),
        'PATH': f"/home/ace/.npm-global/bin:{os.environ.get('PATH')}"
    }
    result = subprocess.run(['claude', '--version'], env=minimal_env, capture_output=True, text=True)
    print(f"   Exit code: {result.returncode}")
    print(f"   Output: {result.stdout.strip()}")
    print(f"   Error: {result.stderr.strip()}")
    
    # Test 3: Check if Claude needs additional env vars
    print("\n3. Checking Claude's environment dependencies:")
    # Add config directory
    minimal_env['XDG_CONFIG_HOME'] = os.path.expanduser('~/.config')
    result = subprocess.run(['claude', '--version'], env=minimal_env, capture_output=True, text=True)
    print(f"   With XDG_CONFIG_HOME:")
    print(f"   Exit code: {result.returncode}")
    print(f"   Output: {result.stdout.strip()}")
    
    # Test 4: Test actual command execution
    print("\n4. Testing Claude command execution:")
    test_prompt = "echo 'Hello from Claude CLI'"
    result = subprocess.run(['claude', '-p', test_prompt], env=minimal_env, capture_output=True, text=True)
    print(f"   Exit code: {result.returncode}")
    print(f"   Output length: {len(result.stdout)} chars")
    if result.returncode != 0:
        print(f"   Error: {result.stderr[:200]}...")

def check_github_rate_limits():
    """Check GitHub API rate limits and calculate wait times"""
    print("\n=== GitHub API Rate Limits ===")
    
    result = subprocess.run(['gh', 'api', 'rate_limit'], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error checking rate limits: {result.stderr}")
        return
    
    try:
        data = json.loads(result.stdout)
        core = data['resources']['core']
        
        print(f"\nCore API:")
        print(f"  Limit: {core['limit']}")
        print(f"  Used: {core['used']}")
        print(f"  Remaining: {core['remaining']}")
        
        # Calculate reset time
        reset_timestamp = core['reset']
        reset_time = datetime.fromtimestamp(reset_timestamp, tz=timezone.utc)
        current_time = datetime.now(timezone.utc)
        time_until_reset = reset_time - current_time
        
        print(f"  Reset at: {reset_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        print(f"  Time until reset: {time_until_reset.total_seconds() / 60:.1f} minutes")
        
        # Calculate recommended wait time if low on quota
        if core['remaining'] < 100:
            print(f"\n⚠️  WARNING: Low API quota remaining!")
            print(f"  Recommended wait between requests: {time_until_reset.total_seconds() / core['remaining']:.1f} seconds")
        
        # Check other relevant limits
        print(f"\nOther limits:")
        print(f"  Search API: {data['resources']['search']['remaining']}/{data['resources']['search']['limit']}")
        print(f"  GraphQL: {data['resources']['graphql']['remaining']}/{data['resources']['graphql']['limit']}")
        
    except Exception as e:
        print(f"Error parsing rate limit data: {e}")

def analyze_croncoder_logs():
    """Analyze recent CronCoder logs for common issues"""
    print("\n=== Analyzing CronCoder Logs ===")
    
    log_file = "/home/ace/prjx/croncoder/logs/croncoder.log"
    if not os.path.exists(log_file):
        print("Log file not found")
        return
    
    # Get last 100 lines
    result = subprocess.run(['tail', '-100', log_file], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error reading log file: {result.stderr}")
        return
    
    lines = result.stdout.strip().split('\n')
    
    # Count error types
    error_patterns = {
        "Claude Code failed": 0,
        "Failed to refresh repository": 0,
        "Failed to commit": 0,
        "Failed to push": 0,
        "Tests failed": 0,
        "Permission denied": 0,
        "rate limit": 0
    }
    
    for line in lines:
        for pattern in error_patterns:
            if pattern.lower() in line.lower():
                error_patterns[pattern] += 1
    
    print("\nError summary from last 100 log lines:")
    for pattern, count in error_patterns.items():
        if count > 0:
            print(f"  {pattern}: {count} occurrences")
    
    # Look for specific Claude errors
    print("\nLast few Claude-related errors:")
    claude_errors = [line for line in lines if "claude" in line.lower() and "error" in line.lower()]
    for error in claude_errors[-5:]:
        print(f"  {error[:150]}...")

def suggest_improvements():
    """Suggest improvements based on findings"""
    print("\n=== Recommendations ===")
    
    print("\n1. For Cron Compatibility:")
    print("   - Ensure Claude CLI path is included: /home/ace/.npm-global/bin")
    print("   - Set minimal environment variables:")
    print("     export HOME=/home/ace")
    print("     export USER=ace")
    print("     export XDG_CONFIG_HOME=$HOME/.config")
    print("     export PATH=/home/ace/.npm-global/bin:/usr/local/bin:/usr/bin:/bin")
    
    print("\n2. For Rate Limiting:")
    print("   - Add rate limit checking before API calls")
    print("   - Implement exponential backoff when approaching limits")
    print("   - Consider caching issue data to reduce API calls")
    
    print("\n3. For 'Manual Intervention' errors:")
    print("   - Add better error logging from Claude CLI stderr")
    print("   - Consider capturing Claude's full output for debugging")
    print("   - Add retry logic with different prompts")
    print("   - Check if Claude session has expired")

if __name__ == "__main__":
    test_claude_cli()
    check_github_rate_limits()
    analyze_croncoder_logs()
    suggest_improvements()