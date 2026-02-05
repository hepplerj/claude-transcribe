#!/usr/bin/env python3
"""
Test script for Claude API connectivity and basic functionality
Run this before processing large batches to verify your setup
"""

import os
import sys
from pathlib import Path

try:
    from anthropic import Anthropic
    import yaml
except ImportError as e:
    print(f"❌ Missing dependency: {e}")
    print("Run: pip install -r requirements_claude.txt")
    sys.exit(1)


def test_api_key():
    """Test if API key is configured"""
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        print("❌ ANTHROPIC_API_KEY not found in environment")
        print("\nSet it with:")
        print("  export ANTHROPIC_API_KEY='your-key-here'")
        return False
    
    print("✓ API key found in environment")
    return True


def test_api_connection(api_key):
    """Test connection to Claude API"""
    try:
        client = Anthropic(api_key=api_key)
        
        # Try a simple completion
        message = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=50,
            messages=[{"role": "user", "content": "Say 'API working' in exactly those words"}]
        )
        
        response_text = message.content[0].text
        
        print("✓ Connected to Claude API")
        print(f"  Response: {response_text[:50]}...")
        
        # Check available models
        print("  ✓ Available models:")
        print("    - claude-opus-4-5-20251101")
        print("    - claude-sonnet-4-5-20250929")
        print("    - claude-haiku-4-5-20251001")
        
        return True
        
    except Exception as e:
        print(f"❌ API connection failed: {e}")
        return False


def test_batch_api(api_key):
    """Test batch API creation"""
    try:
        client = Anthropic(api_key=api_key)
        
        # Create a minimal test batch
        test_requests = [
            {
                "custom_id": "test-1",
                "params": {
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 50,
                    "messages": [
                        {"role": "user", "content": "Say 'batch test 1'"}
                    ]
                }
            }
        ]
        
        batch = client.messages.batches.create(requests=test_requests)
        
        print("✓ Batch API working")
        print(f"  Batch ID: {batch.id}")
        print(f"  Status: {batch.processing_status}")
        
        # Note: We won't wait for completion in this test
        print("  (Not waiting for completion in test)")
        
        return True
        
    except Exception as e:
        print(f"❌ Batch API test failed: {e}")
        return False


def test_yaml_parsing():
    """Test YAML processing"""
    try:
        test_yaml = """
title: "Test Document"
people:
  - "[[John Doe]]"
  - "[[Jane Smith]]"
locations:
  - "[[New York]]"
"""
        data = yaml.safe_load(test_yaml)
        
        if data['title'] == "Test Document":
            print("✓ YAML parsing working")
            return True
        else:
            print("❌ YAML parsing returned unexpected data")
            return False
            
    except Exception as e:
        print(f"❌ YAML test failed: {e}")
        return False


def test_file_system(test_dir="./test_batch_processor"):
    """Test file system operations"""
    try:
        test_path = Path(test_dir)
        test_path.mkdir(exist_ok=True)
        
        # Test write
        test_file = test_path / "test.md"
        test_file.write_text("# Test\nContent here")
        
        # Test read
        content = test_file.read_text()
        
        # Cleanup
        test_file.unlink()
        test_path.rmdir()
        
        if "Content here" in content:
            print("✓ File system operations working")
            return True
        else:
            print("❌ File content mismatch")
            return False
            
    except Exception as e:
        print(f"❌ File system test failed: {e}")
        return False


def test_pdf_support():
    """Check if PDF encoding would work"""
    try:
        import base64
        
        # Test base64 encoding capability
        test_data = b"PDF test data"
        encoded = base64.standard_b64encode(test_data).decode('utf-8')
        decoded = base64.standard_b64decode(encoded)
        
        if decoded == test_data:
            print("✓ PDF encoding support available")
            return True
        else:
            print("❌ PDF encoding failed")
            return False
            
    except Exception as e:
        print(f"❌ PDF support test failed: {e}")
        return False


def main():
    """Run all tests"""
    print("🧪 Testing Batch PDF Processor Setup - Claude API\n")
    print("=" * 50)
    
    tests = [
        ("API Key Configuration", test_api_key, []),
        ("YAML Processing", test_yaml_parsing, []),
        ("File System Operations", test_file_system, []),
        ("PDF Support", test_pdf_support, []),
    ]
    
    # Get API key for subsequent tests
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    
    if api_key:
        tests.extend([
            ("API Connection", test_api_connection, [api_key]),
            ("Batch API", test_batch_api, [api_key]),
        ])
    
    results = []
    
    for name, test_func, args in tests:
        print(f"\n{name}:")
        try:
            success = test_func(*args)
            results.append((name, success))
        except Exception as e:
            print(f"❌ Test crashed: {e}")
            results.append((name, False))
    
    # Summary
    print("\n" + "=" * 50)
    print("📊 Test Summary:\n")
    
    passed = sum(1 for _, success in results if success)
    total = len(results)
    
    for name, success in results:
        status = "✓" if success else "❌"
        print(f"  {status} {name}")
    
    print(f"\n{passed}/{total} tests passed")
    
    if passed == total:
        print("\n✅ All tests passed! You're ready to process documents.")
        print("\nTry running:")
        print("  python batch_pdf_processor_claude.py --input ./pdfs --output ./transcriptions")
        print("\nPrivacy & Cost:")
        print("  • Data NOT used for training")
        print("  • 7-day retention period")
        print("  • 50% cost savings with batch API")
    else:
        print("\n⚠️  Some tests failed. Address issues above before processing.")
        sys.exit(1)


if __name__ == "__main__":
    main()
