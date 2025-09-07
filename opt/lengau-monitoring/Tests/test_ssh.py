#!/usr/bin/env python3
"""
Test SSH connectivity to different node types
"""

import subprocess
import sys

def test_ssh_connection(node, user='root'):
    """Test SSH connection to a node"""
    try:
        cmd = f"ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o PasswordAuthentication=no {user}@{node} 'hostname && uptime'"
        print(f"🔍 Testing: {user}@{node}")
        
        result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, universal_newlines=True, timeout=10)
        
        if result.returncode == 0:
            print(f"  ✅ Success: {result.stdout.strip()}")
            return True
        else:
            print(f"  ❌ Failed: {result.stderr.strip()}")
            return False
            
    except Exception as e:
        print(f"  💥 Exception: {e}")
        return False

def main():
    # Test different node types
    test_cases = [
        ('login3', 'root'),
        ('cnode0003', 'root'),
        ('cnode0056', 'root'),
        ('oss01', 'embele'),
        ('oss01', 'root'),  # Try root as backup
    ]
    
    print("🧪 Testing SSH connectivity...")
    
    for node, user in test_cases:
        test_ssh_connection(node, user)
        print()

if __name__ == "__main__":
    main()

