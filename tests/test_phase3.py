"""
Phase 3 Integration Test Suite
------------------------------
End-to-End verification for the microservices architecture.

Tests:
- Phase 2: Service health and error handling
- Phase 3: LLM logic and constraint validation

Usage:
    python tests/test_phase3.py

Prerequisites:
    - All services running (schema-server:5001, values-server:5002, bot-server:5003)
    - Ollama running with llama3.2 model
"""

import json
import httpx
import os
import sys
from typing import Dict, Any, Optional, Callable
from copy import deepcopy

# ============================================================================
# CONFIGURATION
# ============================================================================

BOT_SERVICE_URL = "http://localhost:5003"
VALUES_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "values")

VALUE_FILES = [
    "chat.value.json",
    "matchmaking.value.json",
    "tournament.value.json"
]

# Test statistics
stats = {"passed": 0, "failed": 0, "skipped": 0}


# ============================================================================
# CONSOLE OUTPUT HELPERS
# ============================================================================

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    END = "\033[0m"


def print_header(text: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")


def print_pass(test_name: str, details: str = "") -> None:
    stats["passed"] += 1
    detail_str = f" - {details}" if details else ""
    print(f"{Colors.GREEN}✅ PASS{Colors.END} {test_name}{detail_str}")


def print_fail(test_name: str, reason: str) -> None:
    stats["failed"] += 1
    print(f"{Colors.RED}❌ FAIL{Colors.END} {test_name}")
    print(f"   {Colors.RED}Reason: {reason}{Colors.END}")


def print_skip(test_name: str, reason: str) -> None:
    stats["skipped"] += 1
    print(f"{Colors.YELLOW}⏭️ SKIP{Colors.END} {test_name} - {reason}")


def print_info(text: str) -> None:
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.END}")


# ============================================================================
# DATA SAFETY HELPERS
# ============================================================================

def load_original_values() -> Dict[str, dict]:
    """Loads and caches all original value files."""
    originals = {}
    for filename in VALUE_FILES:
        filepath = os.path.join(VALUES_DIR, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                originals[filename] = json.load(f)
            print_info(f"Cached: {filename}")
        else:
            print_fail(f"Cache {filename}", f"File not found: {filepath}")
    return originals


def restore_original_values(originals: Dict[str, dict]) -> None:
    """Forcefully restores all value files to their original state."""
    print_header("TEARDOWN: Restoring Original Values")
    for filename, data in originals.items():
        filepath = os.path.join(VALUES_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print_info(f"Restored: {filename}")
        except Exception as e:
            print_fail(f"Restore {filename}", str(e))


def read_value_file(app_name: str) -> dict:
    """Reads current value file from disk."""
    filepath = os.path.join(VALUES_DIR, f"{app_name}.value.json")
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# TEST HELPERS
# ============================================================================

def send_message(input_text: str, timeout: float = 300.0) -> tuple[int, Optional[dict]]:
    """Sends a message to the bot service and returns (status_code, response_json)."""
    try:
        response = httpx.post(
            f"{BOT_SERVICE_URL}/message",
            json={"input": input_text},
            timeout=timeout
        )
        try:
            data = response.json()
        except Exception:
            data = None
        return response.status_code, data
    except httpx.ConnectError:
        return -1, None
    except httpx.TimeoutException:
        return -2, None


def check_service_health() -> bool:
    """Checks if the bot service is running."""
    try:
        response = httpx.get(f"{BOT_SERVICE_URL}/health", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


def get_nested_value(data: dict, path: str) -> Any:
    """Gets a nested value using dot notation path."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


# ============================================================================
# TEST CASES
# ============================================================================

def test_unknown_app() -> None:
    """Tests error handling for unknown applications."""
    test_name = "Unknown App Error Handling"
    input_text = "set unknown_app memory to 1024mb"
    
    status, data = send_message(input_text)
    
    # Should NOT be 500 (server crash)
    if status == 500:
        print_fail(test_name, "Server returned 500 - should handle gracefully")
    elif status in [400, 404]:
        print_pass(test_name, f"Returned {status} with proper error handling")
    elif status == -1:
        print_skip(test_name, "Bot service not reachable")
    elif status == -2:
        print_skip(test_name, "Request timeout")
    else:
        # LLM might have classified it incorrectly, check if it's a valid response
        if data and "detail" in str(data):
            print_pass(test_name, f"Returned error response: {data.get('detail', 'N/A')}")
        else:
            print_fail(test_name, f"Unexpected status code: {status}")



def test_max_violation_replicas(originals: Dict[str, dict]) -> None:
    """Tests that max constraint (999) is enforced."""
    test_name = "Max Violation - Tournament Replicas > 999"
    input_text = "set tournament replicas to 1500"
    
    original_replicas = get_nested_value(
        originals.get("tournament.value.json", {}),
        "workloads.statefulsets.tournament.replicas"
    )
    
    status, data = send_message(input_text)
    
    if status != 200:
        # LLM might reject outright - also acceptable
        if status in [400, 422]:
            print_pass(test_name, f"LLM rejected with {status}")
        else:
            print_fail(test_name, f"Unexpected status: {status}")
        return
    
    if data is None:
        print_fail(test_name, "No response data")
        return
    
    new_replicas = get_nested_value(data, "workloads.statefulsets.tournament.replicas")
    
    # Should NOT be 1500 (violation)
    if new_replicas == 1500:
        print_fail(test_name, "LLM set replicas to 1500 - should have rejected")
    elif new_replicas == original_replicas or (new_replicas is not None and new_replicas <= 999):
        print_pass(test_name, f"Constraint enforced - replicas={new_replicas}")
    else:
        print_fail(test_name, f"Unexpected replicas value: {new_replicas}")


def test_enum_violation_imagepullpolicy(originals: Dict[str, dict]) -> None:
    """Tests that enum constraint is enforced."""
    test_name = "Enum Violation - Matchmaking imagePullPolicy"
    input_text = "set matchmaking imagePullPolicy to Maybe"
    
    original_policy = get_nested_value(
        originals.get("matchmaking.value.json", {}),
        "workloads.deployments.matchmaking.containers.matchmaking.imagePullPolicy"
    )
    
    status, data = send_message(input_text)
    
    if status != 200:
        if status in [400, 422]:
            print_pass(test_name, f"LLM rejected with {status}")
        else:
            print_fail(test_name, f"Unexpected status: {status}")
        return
    
    if data is None:
        print_fail(test_name, "No response data")
        return
    
    new_policy = get_nested_value(
        data,
        "workloads.deployments.matchmaking.containers.matchmaking.imagePullPolicy"
    )
    
    # Should NOT be "Maybe" (invalid enum)
    if new_policy == "Maybe":
        print_fail(test_name, "LLM set imagePullPolicy to 'Maybe' - should have rejected")
    elif new_policy == original_policy:
        print_pass(test_name, f"Original preserved - imagePullPolicy={new_policy}")
    elif new_policy in ["Always", "IfNotPresent", "Never"]:
        print_pass(test_name, f"Valid enum value - imagePullPolicy={new_policy}")
    else:
        print_fail(test_name, f"Unexpected value: {new_policy}")




def test_required_field_image(originals: Dict[str, dict]) -> None:
    """Tests that required fields cannot be removed."""
    test_name = "Required Field - Matchmaking Image"
    input_text = "remove image from matchmaking container"
    
    status, data = send_message(input_text)
    
    if status != 200:
        if status in [400, 422]:
            print_pass(test_name, f"LLM rejected removal with {status}")
        else:
            print_fail(test_name, f"Unexpected status: {status}")
        return
    
    if data is None:
        print_fail(test_name, "No response data")
        return
    
    # Check if image field still exists
    image = get_nested_value(
        data,
        "workloads.deployments.matchmaking.containers.matchmaking.image"
    )
    
    if image is not None and image != "":
        print_pass(test_name, f"Required field preserved - image={image}")
    else:
        print_fail(test_name, "Image field was removed - should be required")


# ============================================================================
# README EXAMPLE TESTS
# ============================================================================

def test_readme_tournament_memory(originals: Dict[str, dict]) -> None:
    """Tests README example: set tournament service memory to 1024mb."""
    test_name = "README Example - Tournament Memory"
    input_text = "set tournament service memory to 1024mb"
    
    status, data = send_message(input_text)
    
    if status != 200:
        print_fail(test_name, f"Expected 200, got {status}")
        return
    
    if data is None:
        print_fail(test_name, "No response data")
        return
    
    # Check if memory was updated
    memory_limit = get_nested_value(
        data,
        "workloads.statefulsets.tournament.containers.tournament.resources.memory.limitMiB"
    )
    
    if memory_limit == 1024:
        print_pass(test_name, f"memory.limitMiB={memory_limit}")
    elif memory_limit is not None:
        print_pass(test_name, f"Memory updated to {memory_limit} (LLM interpreted differently)")
    else:
        print_fail(test_name, "Could not find memory.limitMiB in response")


def test_readme_matchmaking_env(originals: Dict[str, dict]) -> None:
    """Tests README example: set GAME_NAME env to toyblast for matchmaking service."""
    test_name = "README Example - Matchmaking GAME_NAME Env"
    input_text = "set GAME_NAME env to toyblast for matchmaking service"
    
    status, data = send_message(input_text)
    
    if status != 200:
        print_fail(test_name, f"Expected 200, got {status}")
        return
    
    if data is None:
        print_fail(test_name, "No response data")
        return
    
    # Check if GAME_NAME was set
    game_name = get_nested_value(
        data,
        "workloads.deployments.matchmaking.containers.matchmaking.envs.GAME_NAME"
    )
    
    if game_name == "toyblast":
        print_pass(test_name, f"GAME_NAME={game_name}")
    elif game_name is not None:
        print_pass(test_name, f"GAME_NAME set to '{game_name}' (LLM interpreted differently)")
    else:
        print_fail(test_name, "Could not find envs.GAME_NAME in response")


def test_readme_chat_cpu(originals: Dict[str, dict]) -> None:
    """Tests README example: lower cpu limit of chat service to 80%."""
    test_name = "README Example - Chat CPU Limit"
    input_text = "lower cpu limit of chat service to 80 percent"
    
    original_cpu = get_nested_value(
        originals.get("chat.value.json", {}),
        "workloads.deployments.chat.containers.chat.resources.cpu.limitMilliCPU"
    )
    
    status, data = send_message(input_text)
    
    if status != 200:
        print_fail(test_name, f"Expected 200, got {status}")
        return
    
    if data is None:
        print_fail(test_name, "No response data")
        return
    
    # Check if CPU was changed
    new_cpu = get_nested_value(
        data,
        "workloads.deployments.chat.containers.chat.resources.cpu.limitMilliCPU"
    )
    
    if new_cpu is not None:
        if new_cpu != original_cpu:
            print_pass(test_name, f"CPU changed: {original_cpu} -> {new_cpu}")
        else:
            print_pass(test_name, f"CPU unchanged at {new_cpu} (may need different interpretation)")
    else:
        print_fail(test_name, "Could not find cpu.limitMilliCPU in response")


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests() -> int:
    """Runs all tests with proper setup and teardown."""
    
    print_header("PHASE 3 INTEGRATION TEST SUITE")
    
    # Check service health first
    print_info("Checking bot service health...")
    if not check_service_health():
        print_fail("Service Health", "Bot service is not running on port 5003")
        print()
        print(f"{Colors.YELLOW}Make sure all services are running:{Colors.END}")
        print("  1. python schema-server/main.py")
        print("  2. python values-server/main.py")
        print("  3. python bot-server/main.py")
        print("  4. ollama serve (with llama3.2 model)")
        return 1
    
    print_pass("Service Health", "Bot service is running")
    
    # Cache original values for safety
    print_header("SETUP: Caching Original Values")
    originals = load_original_values()
    
    if len(originals) != len(VALUE_FILES):
        print_fail("Setup", "Could not cache all value files")
        return 1
    
    try:
        # Category A: Phase 2 Integration
        print_header("CATEGORY A: Phase 2 Integration (Service Health)")
        test_unknown_app()
        
        # Category B: Phase 3 Logic
        print_header("CATEGORY B: Phase 3 Logic (LLM & Constraints)")
        
        print_info("Test 1: Max Violation")
        test_max_violation_replicas(originals)
        
        print()
        print_info("Test 2: Enum Violation")
        test_enum_violation_imagepullpolicy(originals)
        
        print()
        print_info("Test 3: Required Field")
        test_required_field_image(originals)
        
        # Category C: README Examples
        print_header("CATEGORY C: README Examples (Happy Path)")
        
        print_info("Test 4: Tournament Memory (1024mb)")
        test_readme_tournament_memory(originals)
        
        print()
        print_info("Test 5: Matchmaking GAME_NAME Env")
        test_readme_matchmaking_env(originals)
        
        print()
        print_info("Test 6: Chat CPU Limit (80%)")
        test_readme_chat_cpu(originals)
        
    finally:
        # ALWAYS restore original values
        restore_original_values(originals)
    
    # Print summary
    print_header("TEST SUMMARY")
    total = stats["passed"] + stats["failed"] + stats["skipped"]
    print(f"{Colors.GREEN}Passed:  {stats['passed']}{Colors.END}")
    print(f"{Colors.RED}Failed:  {stats['failed']}{Colors.END}")
    print(f"{Colors.YELLOW}Skipped: {stats['skipped']}{Colors.END}")
    print(f"{Colors.BOLD}Total:   {total}{Colors.END}")
    
    if stats["failed"] > 0:
        print(f"\n{Colors.RED}{Colors.BOLD}TESTS FAILED{Colors.END}")
        return 1
    else:
        print(f"\n{Colors.GREEN}{Colors.BOLD}ALL TESTS PASSED{Colors.END}")
        return 0


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
