#!/usr/bin/env python3
"""
Simple test of data collection pipeline
"""

import subprocess
import sys

def test_collection_pipeline():
    """Test the complete data collection pipeline"""
    print("🧪 TESTING DATA COLLECTION PIPELINE")
    print("=" * 40)
    
    # Step 1: Fix database schema
    print("🔧 Step 1: Fixing database schema...")
    try:
        result = subprocess.run([sys.executable, "scripts/fix_database_schema.py"], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("✅ Database schema fixed")
        else:
            print(f"❌ Schema fix failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Schema fix error: {e}")
        return False
    
    # Step 2: Test simple collection
    print("\n📊 Step 2: Testing simple collection...")
    try:
        result = subprocess.run([sys.executable, "scripts/lengau_collector_simple.py", "login3,cnode0056"], 
                              capture_output=True, text=True, timeout=60)
        if result.returncode == 0:
            print("✅ Simple collection works")
        else:
            print(f"❌ Simple collection failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Simple collection error: {e}")
        return False
    
    # Step 3: Test production collector (small batch)
    print("\n🏭 Step 3: Testing production collector...")
    try:
        result = subprocess.run([sys.executable, "scripts/lengau_production_collector.py", 
                               "--node-limit", "5", "--max-workers", "2"], 
                              capture_output=True, text=True, timeout=120)
        if result.returncode == 0:
            print("✅ Production collector works")
            # Extract success rate from output
            lines = result.stdout.split('\n')
            for line in lines:
                if "Success rate:" in line:
                    print(f"📈 {line.strip()}")
        else:
            print(f"❌ Production collector failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Production collector error: {e}")
        return False
    
    # Step 4: Test dashboard
    print("\n📋 Step 4: Testing dashboard...")
    try:
        result = subprocess.run([sys.executable, "scripts/lengau_enhanced_dashboard_fixed.py", "--once"], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("✅ Dashboard works")
        else:
            print(f"❌ Dashboard failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Dashboard error: {e}")
        return False
    
    # Step 5: Test system status
    print("\n🏥 Step 5: Testing system status...")
    try:
        result = subprocess.run([sys.executable, "scripts/lengau_system_status.py"], 
                              capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            print("✅ System status works")
            # Show key metrics
            lines = result.stdout.split('\n')
            for line in lines:
                if "Active nodes:" in line or "Alert nodes:" in line:
                    print(f"📊 {line.strip()}")
        else:
            print(f"❌ System status failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ System status error: {e}")
        return False
    
    print(f"\n🎉 ALL TESTS PASSED!")
    print("✅ Data collection pipeline is working correctly")
    return True

if __name__ == "__main__":
    success = test_collection_pipeline()
    sys.exit(0 if success else 1)

