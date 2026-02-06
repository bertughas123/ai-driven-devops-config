"""
Phase 2 Integration Tests
-------------------------
Simple tests for Schema Service and Values Service.
These tests use actual files from ./data directory (no mocking).

Run with: python tests/test_phase2_simple.py
"""

import os
import sys
import json

# Change to project root
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)

# Set environment variables BEFORE importing the apps
os.environ["SCHEMA_DIR"] = "./data/schemas"
os.environ["VALUES_DIR"] = "./data/values"

# Import modules dynamically
import importlib.util

def load_module_from_path(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_schema_service():
    """Test Schema Service endpoints."""
    print("\n" + "=" * 60)
    print("Testing Schema Service")
    print("=" * 60)
    
    schema_service = load_module_from_path("schema_main", "./schema-server/main.py")
    
    # Import TestClient here after loading the module
    from starlette.testclient import TestClient
    client = TestClient(schema_service.app)
    
    # Test 1: Get tournament schema (200 OK)
    print("\n✓ Test 1: GET /tournament")
    response = client.get("/tournament")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert isinstance(response.json(), dict), "Response should be a dict"
    print(f"  Status: {response.status_code} OK")
    
    # Test 2: Get chat schema (200 OK)
    print("\n✓ Test 2: GET /chat")
    response = client.get("/chat")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"  Status: {response.status_code} OK")
    
    # Test 3: Get matchmaking schema (200 OK)
    print("\n✓ Test 3: GET /matchmaking")
    response = client.get("/matchmaking")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"  Status: {response.status_code} OK")
    
    # Test 4: Non-existent app (404 Not Found)
    print("\n✓ Test 4: GET /nonexistent (expect 404)")
    response = client.get("/nonexistent")
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    assert "Schema not found" in response.json()["detail"]
    print(f"  Status: {response.status_code} Not Found")
    
    print("\n✅ Schema Service: All tests passed!")


def test_values_service():
    """Test Values Service endpoints."""
    print("\n" + "=" * 60)
    print("Testing Values Service")
    print("=" * 60)
    
    values_service = load_module_from_path("values_main", "./values-server/main.py")
    
    from starlette.testclient import TestClient
    client = TestClient(values_service.app)
    
    # Test 1: Get tournament values (200 OK)
    print("\n✓ Test 1: GET /tournament")
    response = client.get("/tournament")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    assert isinstance(response.json(), dict), "Response should be a dict"
    print(f"  Status: {response.status_code} OK")
    
    # Test 2: Get chat values (200 OK)
    print("\n✓ Test 2: GET /chat")
    response = client.get("/chat")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"  Status: {response.status_code} OK")
    
    # Test 3: Get matchmaking values (200 OK)
    print("\n✓ Test 3: GET /matchmaking")
    response = client.get("/matchmaking")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"  Status: {response.status_code} OK")
    
    # Test 4: Non-existent app (404 Not Found)
    print("\n✓ Test 4: GET /nonexistent (expect 404)")
    response = client.get("/nonexistent")
    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    assert "Values not found" in response.json()["detail"]
    print(f"  Status: {response.status_code} Not Found")
    
    print("\n✅ Values Service: All tests passed!")


if __name__ == "__main__":
    try:
        test_schema_service()
        test_values_service()
        print("\n" + "=" * 60)
        print("🎉 ALL PHASE 2 TESTS PASSED!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)
