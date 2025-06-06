#!/usr/bin/env python3
"""
Test Claude CLI authentication and diagnose common issues
"""

import subprocess
import os
import sys
import json

def test_claude_auth():
    """Test Claude CLI authentication status"""
    print("=== Testing Claude CLI Authentication ===\n")
    
    # Test 1: Check if Claude CLI is available
    print("1. Checking Claude CLI availability...")
    try:
        result = subprocess.run(['which', 'claude'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✓ Claude CLI found at: {result.stdout.strip()}")
        else:
            print("   ✗ Claude CLI not found in PATH")
            print("   Fix: npm install -g @claude/cli")
            return False
    except Exception as e:
        print(f"   ✗ Error checking Claude CLI: {e}")
        return False
    
    # Test 2: Check Claude version
    print("\n2. Checking Claude CLI version...")
    try:
        result = subprocess.run(['claude', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✓ Version: {result.stdout.strip()}")
        else:
            print(f"   ✗ Failed to get version: {result.stderr}")
    except Exception as e:
        print(f"   ✗ Error: {e}")
    
    # Test 3: Test simple Claude command
    print("\n3. Testing Claude authentication with simple command...")
    test_prompt = "echo 'Authentication test successful'"
    try:
        result = subprocess.run(
            ['claude', '-p', test_prompt], 
            capture_output=True, 
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            print("   ✓ Authentication successful!")
            print(f"   Output length: {len(result.stdout)} chars")
            if "Authentication test successful" in result.stdout:
                print("   ✓ Claude executed the command correctly")
            else:
                print("   ⚠ Claude responded but didn't execute as expected")
        else:
            print(f"   ✗ Authentication failed!")
            print(f"   Exit code: {result.returncode}")
            print(f"   Error: {result.stderr[:500]}")
            
            # Diagnose common issues
            if "please log in" in result.stderr.lower():
                print("\n   DIAGNOSIS: Not authenticated")
                print("   Fix: Run 'claude login' to authenticate")
            elif "rate limit" in result.stderr.lower():
                print("\n   DIAGNOSIS: Rate limit reached")
                print("   Fix: Wait and try again later")
            elif result.stderr.strip() == "":
                print("\n   DIAGNOSIS: Silent failure - likely session expired")
                print("   Fix: Run 'claude login' to re-authenticate")
                
    except subprocess.TimeoutExpired:
        print("   ✗ Command timed out after 30 seconds")
        print("   DIAGNOSIS: Claude might be stuck or network is slow")
    except Exception as e:
        print(f"   ✗ Error testing authentication: {e}")
    
    # Test 4: Check Claude config
    print("\n4. Checking Claude configuration...")
    config_paths = [
        os.path.expanduser("~/.config/claude"),
        os.path.expanduser("~/.claude"),
        os.path.join(os.environ.get('XDG_CONFIG_HOME', '~/.config'), 'claude')
    ]
    
    config_found = False
    for path in config_paths:
        expanded_path = os.path.expanduser(path)
        if os.path.exists(expanded_path):
            print(f"   ✓ Config found at: {expanded_path}")
            config_found = True
            
            # Check for auth files
            auth_files = ['auth.json', 'config.json', 'credentials.json']
            for auth_file in auth_files:
                auth_path = os.path.join(expanded_path, auth_file)
                if os.path.exists(auth_path):
                    stat = os.stat(auth_path)
                    print(f"   ✓ Found {auth_file} (size: {stat.st_size} bytes)")
    
    if not config_found:
        print("   ✗ No Claude config directory found")
        print("   Fix: Run 'claude login' to create config")
    
    # Test 5: Environment check
    print("\n5. Checking environment variables...")
    important_vars = ['HOME', 'USER', 'PATH', 'XDG_CONFIG_HOME']
    for var in important_vars:
        value = os.environ.get(var, 'NOT SET')
        if var == 'PATH' and value != 'NOT SET':
            # Just show if Claude path is included
            if '.npm-global/bin' in value or 'claude' in value:
                print(f"   ✓ {var}: includes Claude path")
            else:
                print(f"   ⚠ {var}: might not include Claude path")
        else:
            print(f"   {var}: {value}")

def suggest_fixes():
    """Suggest fixes for common issues"""
    print("\n\n=== Common Fixes ===")
    print("\n1. If Claude is not authenticated:")
    print("   claude login")
    print("\n2. If Claude CLI is not installed:")
    print("   npm install -g @claude/cli")
    print("\n3. If running from cron, ensure these environment variables:")
    print("   export HOME=/home/ace")
    print("   export USER=ace")
    print("   export XDG_CONFIG_HOME=$HOME/.config")
    print("   export PATH=/home/ace/.npm-global/bin:$PATH")
    print("\n4. If session expired (silent failure):")
    print("   claude logout")
    print("   claude login")
    print("\n5. To test from cron environment:")
    print("   env -i HOME=$HOME USER=$USER XDG_CONFIG_HOME=$HOME/.config PATH=/home/ace/.npm-global/bin:$PATH claude --version")

if __name__ == "__main__":
    test_claude_auth()
    suggest_fixes()