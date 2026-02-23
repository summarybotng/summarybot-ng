#!/usr/bin/env python3
"""
End-to-end test for summary regeneration functionality.

This test uses the TEST_AUTH_SECRET bypass to test the API without requiring
actual Discord authentication.

Usage:
    TEST_AUTH_SECRET=mysecret TEST_GUILD_ID=123456 python tests/test_regeneration_e2e.py

Or with pytest:
    TEST_AUTH_SECRET=mysecret TEST_GUILD_ID=123456 pytest tests/test_regeneration_e2e.py -v
"""

import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

# Test configuration
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/api")
TEST_AUTH_SECRET = os.getenv("TEST_AUTH_SECRET", "test_secret_key_12345")
TEST_GUILD_ID = os.getenv("TEST_GUILD_ID", "1234567890")


def get_headers():
    """Get headers with test auth bypass."""
    return {
        "X-Test-Auth-Key": TEST_AUTH_SECRET,
        "Content-Type": "application/json",
    }


async def test_list_summaries():
    """Test listing stored summaries."""
    print("\n=== Testing: List Summaries ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/guilds/{TEST_GUILD_ID}/stored-summaries",
            headers=get_headers(),
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Total summaries: {data.get('total', 0)}")
            items = data.get("items", [])
            if items:
                print(f"First summary ID: {items[0]['id']}")
                return items[0]["id"]
            else:
                print("No summaries found")
                return None
        else:
            print(f"Error: {response.text}")
            return None


async def test_get_summary_detail(summary_id: str):
    """Test getting summary details."""
    print(f"\n=== Testing: Get Summary Detail ({summary_id}) ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/guilds/{TEST_GUILD_ID}/stored-summaries/{summary_id}",
            headers=get_headers(),
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Title: {data.get('title', 'N/A')}")
            print(f"Summary text length: {len(data.get('summary_text', ''))}")
            metadata = data.get("metadata", {})
            print(f"Metadata keys: {list(metadata.keys()) if metadata else 'None'}")
            if metadata:
                print(f"  - Model: {metadata.get('model_used', 'N/A')}")
                print(f"  - Length: {metadata.get('summary_length', 'N/A')}")
                print(f"  - Perspective: {metadata.get('perspective', 'N/A')}")
                print(f"  - Tokens: {metadata.get('tokens_used', 'N/A')}")
                print(f"  - Input tokens: {metadata.get('input_tokens', 'N/A')}")
                print(f"  - Output tokens: {metadata.get('output_tokens', 'N/A')}")
                print(f"  - Generation time ms: {metadata.get('generation_time_ms', 'N/A')}")
                print(f"  - Grounded: {metadata.get('grounded', 'N/A')}")
            return data
        else:
            print(f"Error: {response.text}")
            return None


async def test_regenerate_summary(summary_id: str, options: dict = None):
    """Test regenerating a summary with optional custom options."""
    print(f"\n=== Testing: Regenerate Summary ({summary_id}) ===")
    if options:
        print(f"Options: {options}")

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{API_BASE_URL}/guilds/{TEST_GUILD_ID}/stored-summaries/{summary_id}/regenerate",
            headers=get_headers(),
            json=options,
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Task ID: {data.get('task_id', 'N/A')}")
            print(f"Status: {data.get('status', 'N/A')}")
            return data.get("task_id")
        else:
            print(f"Error: {response.text}")
            return None


async def test_check_task_status(task_id: str):
    """Check regeneration task status."""
    print(f"\n=== Testing: Check Task Status ({task_id}) ===")
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(
            f"{API_BASE_URL}/summaries/tasks/{task_id}",
            headers=get_headers(),
        )
        print(f"Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"Task status: {data.get('status', 'N/A')}")
            if data.get("error"):
                print(f"Error: {data.get('error')}")
            return data
        else:
            print(f"Error: {response.text}")
            return None


async def wait_for_regeneration(task_id: str, max_wait: int = 60):
    """Wait for regeneration to complete."""
    print(f"\n=== Waiting for regeneration (max {max_wait}s) ===")
    import time
    start = time.time()

    async with httpx.AsyncClient(timeout=30.0) as client:
        while time.time() - start < max_wait:
            response = await client.get(
                f"{API_BASE_URL}/summaries/tasks/{task_id}",
                headers=get_headers(),
            )
            if response.status_code == 200:
                data = response.json()
                status = data.get("status")
                print(f"  Status: {status} ({int(time.time() - start)}s)")
                if status == "completed":
                    return True
                elif status == "failed":
                    print(f"  Failed: {data.get('error')}")
                    return False
            await asyncio.sleep(2)

    print("  Timeout waiting for regeneration")
    return False


async def run_full_test():
    """Run the full test suite."""
    print("=" * 60)
    print("Summary Regeneration E2E Test")
    print("=" * 60)
    print(f"API Base URL: {API_BASE_URL}")
    print(f"Test Guild ID: {TEST_GUILD_ID}")
    print(f"Test Auth Secret: {'*' * len(TEST_AUTH_SECRET)}")

    # Test 1: List summaries
    summary_id = await test_list_summaries()
    if not summary_id:
        print("\n❌ Cannot proceed without a summary to test")
        return False

    # Test 2: Get summary detail (before regeneration)
    print("\n--- Before Regeneration ---")
    before = await test_get_summary_detail(summary_id)
    if not before:
        print("\n❌ Failed to get summary details")
        return False

    # Test 3: Regenerate with custom options
    task_id = await test_regenerate_summary(summary_id, {
        "summary_length": "detailed",
        "perspective": "developer",
    })
    if not task_id:
        print("\n❌ Failed to start regeneration")
        return False

    # Test 4: Wait for completion
    success = await wait_for_regeneration(task_id)
    if not success:
        print("\n❌ Regeneration failed or timed out")
        return False

    # Test 5: Get summary detail (after regeneration)
    print("\n--- After Regeneration ---")
    after = await test_get_summary_detail(summary_id)
    if not after:
        print("\n❌ Failed to get summary details after regeneration")
        return False

    # Compare before and after
    print("\n=== Comparison ===")
    before_meta = before.get("metadata", {})
    after_meta = after.get("metadata", {})

    print(f"Model: {before_meta.get('model_used')} -> {after_meta.get('model_used')}")
    print(f"Perspective: {before_meta.get('perspective')} -> {after_meta.get('perspective')}")
    print(f"Tokens: {before_meta.get('tokens_used')} -> {after_meta.get('tokens_used')}")

    text_changed = before.get("summary_text") != after.get("summary_text")
    print(f"Summary text changed: {text_changed}")

    print("\n✅ All tests passed!")
    return True


async def run_api_health_check():
    """Quick health check of the API."""
    print("\n=== API Health Check ===")
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Try the health endpoint if it exists
            response = await client.get(f"{API_BASE_URL.replace('/api', '')}/health")
            print(f"Health endpoint: {response.status_code}")
        except Exception as e:
            print(f"Health check failed: {e}")

        try:
            # Try listing summaries with auth
            response = await client.get(
                f"{API_BASE_URL}/guilds/{TEST_GUILD_ID}/stored-summaries",
                headers=get_headers(),
            )
            print(f"Auth bypass test: {response.status_code}")
            if response.status_code == 401:
                print("  ⚠️  Auth bypass not working - check TEST_AUTH_SECRET env var")
            elif response.status_code == 200:
                print("  ✅ Auth bypass working")
        except Exception as e:
            print(f"API test failed: {e}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test summary regeneration")
    parser.add_argument("--health", action="store_true", help="Just run health check")
    parser.add_argument("--summary-id", help="Test specific summary ID")
    args = parser.parse_args()

    if args.health:
        asyncio.run(run_api_health_check())
    elif args.summary_id:
        async def test_specific():
            await test_get_summary_detail(args.summary_id)
            task_id = await test_regenerate_summary(args.summary_id, {
                "perspective": "developer",
            })
            if task_id:
                await wait_for_regeneration(task_id)
                await test_get_summary_detail(args.summary_id)
        asyncio.run(test_specific())
    else:
        success = asyncio.run(run_full_test())
        sys.exit(0 if success else 1)
