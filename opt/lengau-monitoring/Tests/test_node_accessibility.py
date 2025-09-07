#!/usr/bin/env python3
"""
Test which nodes are accessible via SSH
"""

import subprocess
import concurrent.futures
from pathlib import Path

def test_node_ssh(node_name):
    """Test if a node is accessible via SSH"""
    try:
        # Simple SSH test - just check if we can connect
        result = subprocess.run([
            'ssh', '-o', 'ConnectTimeout=5', 
            '-o', 'BatchMode=yes',
            '-o', 'StrictHostKeyChecking=no',
            node_name, 'echo "OK"'
        ], capture_output=True, text=True, timeout=10)
        
        return {
            'node': node_name,
            'accessible': result.returncode == 0,
            'output': result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
        }
    except Exception as e:
        return {
            'node': node_name,
            'accessible': False,
            'output': str(e)
        }

def test_node_accessibility():
    """Test accessibility of different node types"""
    print("🔌 TESTING NODE ACCESSIBILITY")
    print("=" * 40)
    
    # Load nodes
    nodes_file = Path("compute_nodes.txt")
    if not nodes_file.exists():
        print("❌ compute_nodes.txt not found")
        return
    
    with open(nodes_file, 'r') as f:
        all_nodes = [line.strip() for line in f if line.strip()]
    
    # Test a sample of different node types
    test_nodes = []
    
    # Sample compute nodes
    compute_nodes = [n for n in all_nodes if n.startswith('cnode')]
    test_nodes.extend(compute_nodes[:20])  # First 20 compute nodes
    
    # All special nodes
    special_nodes = [n for n in all_nodes if not n.startswith('cnode')]
    test_nodes.extend(special_nodes)
    
    print(f"🧪 Testing accessibility of {len(test_nodes)} nodes...")
    
    # Test nodes in parallel
    accessible_nodes = []
    inaccessible_nodes = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_node = {executor.submit(test_node_ssh, node): node for node in test_nodes}
        
        for future in concurrent.futures.as_completed(future_to_node):
            result = future.result()
            
            if result['accessible']:
                accessible_nodes.append(result['node'])
                print(f"  ✅ {result['node']}")
            else:
                inaccessible_nodes.append(result['node'])
                print(f"  ❌ {result['node']}: {result['output'][:50]}")
    
    # Summary
    total_tested = len(test_nodes)
    accessible_count = len(accessible_nodes)
    accessibility_rate = (accessible_count / total_tested * 100) if total_tested > 0 else 0
    
    print(f"\n📊 ACCESSIBILITY SUMMARY")
    print("-" * 30)
    print(f"Total tested: {total_tested}")
    print(f"Accessible: {accessible_count}")
    print(f"Inaccessible: {len(inaccessible_nodes)}")
    print(f"Accessibility rate: {accessibility_rate:.1f}%")
    
    if accessible_nodes:
        print(f"\n✅ Sample accessible nodes:")
        for node in accessible_nodes[:10]:
            print(f"  {node}")
    
    if inaccessible_nodes:
        print(f"\n❌ Sample inaccessible nodes:")
        for node in inaccessible_nodes[:10]:
            print(f"  {node}")

if __name__ == "__main__":
    test_node_accessibility()

