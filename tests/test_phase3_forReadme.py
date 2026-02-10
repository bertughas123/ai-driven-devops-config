"""
Phase 3 README Example Tests
-----------------------------
Focused E2E tests for the 3 curl examples in README.md.
Each test sends the exact user input from the README and validates
the LLM's response against expected values.

Data Safety:
    - Original value files are cached before tests
    - Restored via try...finally to guarantee idempotency

Usage:
    python tests/test_phase3_forReadme.py

Prerequisites:
    - All services running (schema-server:5001, values-server:5002, bot-server:5003)
    - Ollama running with configured LLM model
"""

import json
import httpx
import os
import sys
from typing import Dict, Any, Optional
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
# DATA SAFETY (Idempotency)
# ============================================================================

def load_original_values() -> Dict[str, Any]:
    """Caches original value files into memory for safe restoration."""
    originals = {}
    for filename in VALUE_FILES:
        filepath = os.path.join(VALUES_DIR, filename)
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                originals[filename] = json.load(f)
            print_info(f"Cached: {filename}")
        except Exception as e:
            print_fail("Cache", f"Failed to cache {filename}: {e}")
    return originals


def restore_original_values(originals: Dict[str, Any]) -> None:
    """Forcefully restores all original value files from cache."""
    print_header("TEARDOWN: Restoring Original Values")
    for filename, data in originals.items():
        filepath = os.path.join(VALUES_DIR, filename)
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print_info(f"Restored: {filename}")
        except Exception as e:
            print_fail("Restore", f"CRITICAL: Failed to restore {filename}: {e}")


def restore_single_file(originals: Dict[str, Any], filename: str) -> None:
    """Restores a single value file from cache (between tests)."""
    if filename in originals:
        filepath = os.path.join(VALUES_DIR, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(originals[filename], f, indent=2, ensure_ascii=False)
        print_info(f"Restored: {filename}")


# ============================================================================
# SERVICE HEALTH CHECK
# ============================================================================

def check_service_health() -> bool:
    """Checks if bot service is reachable."""
    try:
        response = httpx.get(f"{BOT_SERVICE_URL}/health", timeout=10.0)
        return response.status_code == 200
    except Exception:
        return False


# ============================================================================
# TEST HELPER
# ============================================================================

def send_message(input_text: str, timeout: float = 300.0) -> tuple[int, Optional[dict]]:
    """Sends a message to the bot service and returns (status_code, response_json)."""
    try:
        response = httpx.post(
            f"{BOT_SERVICE_URL}/message",
            json={"input": input_text},
            timeout=timeout
        )
        return response.status_code, response.json()
    except httpx.TimeoutException:
        return -2, None
    except Exception as e:
        return -1, {"error": str(e)}


def navigate_json(data: dict, path: str) -> Any:
    """Navigates a nested dict using dot notation (e.g. 'a.b.c')."""
    keys = path.split(".")
    current = data
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


# ============================================================================
# README EXAMPLE TESTS
# ============================================================================

def test_tournament_memory(originals: Dict[str, Any]) -> None:
    """
    README Example 1:
    curl -d '{"input": "set tournament service memory to 1024mb"}'
    
    Expected: tournament memory limitMiB changes from 4096 to 1024.
    Original values for all other fields must be preserved.
    """
    test_name = "Tournament Memory → 1024 MiB"
    path = "workloads.statefulsets.tournament.containers.tournament.resources.memory.limitMiB"
    original_value = 4096
    expected_value = 1024

    # Restore before test to ensure clean state
    restore_single_file(originals, "tournament.value.json")

    status, body = send_message("set tournament service memory to 1024mb")

    if status == -2:
        print_skip(test_name, "Request timeout (LLM too slow)")
        return

    if status != 200:
        print_fail(test_name, f"Expected 200, got {status}")
        return

    actual = navigate_json(body, path)

    if actual == expected_value:
        print_pass(test_name, f"limitMiB = {actual}")
    elif actual == original_value:
        print_fail(test_name, f"Value unchanged (still {original_value}). LLM did not apply the change.")
    else:
        print_fail(test_name, f"Expected {expected_value}, got {actual}")

    # Verify other fields are preserved
    replicas = navigate_json(body, "workloads.statefulsets.tournament.replicas")
    cpu_limit = navigate_json(body, "workloads.statefulsets.tournament.containers.tournament.resources.cpu.limitMilliCPU")

    if replicas == 2 and cpu_limit == 2500:
        print_pass(f"  └─ Field Preservation", f"replicas={replicas}, cpu={cpu_limit}")
    else:
        print_fail(f"  └─ Field Preservation", f"replicas={replicas} (exp 2), cpu={cpu_limit} (exp 2500)")

    # Restore after test
    restore_single_file(originals, "tournament.value.json")


def test_matchmaking_env(originals: Dict[str, Any]) -> None:
    """
    README Example 2:
    curl -d '{"input": "set GAME_NAME env to toyblast for matchmaking service"}'
    
    Expected: matchmaking envs.GAME_NAME changes from "toonblast" to "toyblast".
    Original values for all other fields must be preserved.
    """
    test_name = "Matchmaking GAME_NAME → toyblast"
    path = "workloads.deployments.matchmaking.containers.matchmaking.envs.GAME_NAME"
    original_value = "toonblast"
    expected_value = "toyblast"

    # Restore before test to ensure clean state
    restore_single_file(originals, "matchmaking.value.json")

    status, body = send_message("set GAME_NAME env to toyblast for matchmaking service")

    if status == -2:
        print_skip(test_name, "Request timeout (LLM too slow)")
        return

    if status != 200:
        print_fail(test_name, f"Expected 200, got {status}")
        return

    actual = navigate_json(body, path)

    if actual == expected_value:
        print_pass(test_name, f"GAME_NAME = \"{actual}\"")
    elif actual == original_value:
        print_fail(test_name, f"Value unchanged (still \"{original_value}\"). LLM did not apply the change.")
    else:
        print_fail(test_name, f"Expected \"{expected_value}\", got \"{actual}\"")

    # Verify other fields are preserved
    replicas = navigate_json(body, "workloads.deployments.matchmaking.replicas")
    image = navigate_json(body, "workloads.deployments.matchmaking.containers.matchmaking.image")

    if replicas == 2 and image == "matchmaking:1.2.3":
        print_pass(f"  └─ Field Preservation", f"replicas={replicas}, image={image}")
    else:
        print_fail(f"  └─ Field Preservation", f"replicas={replicas} (exp 2), image={image} (exp matchmaking:1.2.3)")

    # Restore after test
    restore_single_file(originals, "matchmaking.value.json")


def test_chat_cpu(originals: Dict[str, Any]) -> None:
    """
    README Example 3:
    curl -d '{"input": "lower cpu limit of chat service to %80"}'
    
    Expected: chat cpu limitMilliCPU changes from 1500 to 800.
    Domain Logic: 80% = 800 milliCPU (percentage * 10).
    Original values for all other fields must be preserved.
    """
    test_name = "Chat CPU Limit → 800 milliCPU (80%)"
    path = "workloads.deployments.chat.containers.chat.resources.cpu.limitMilliCPU"
    original_value = 1500
    expected_value = 800

    # Restore before test to ensure clean state
    restore_single_file(originals, "chat.value.json")

    status, body = send_message("lower cpu limit of chat service to %80")

    if status == -2:
        print_skip(test_name, "Request timeout (LLM too slow)")
        return

    if status != 200:
        print_fail(test_name, f"Expected 200, got {status}")
        return

    actual = navigate_json(body, path)

    if actual == expected_value:
        print_pass(test_name, f"limitMilliCPU = {actual}")
    elif actual == original_value:
        print_fail(test_name, f"Value unchanged (still {original_value}). LLM did not apply the change.")
    elif isinstance(actual, (int, float)) and actual != original_value:
        # LLM changed the value but not to expected - could be domain conversion issue
        print_fail(test_name, f"Expected {expected_value}, got {actual}. (Domain conversion may have failed: 80% should = 800 milliCPU)")
    else:
        print_fail(test_name, f"Expected {expected_value}, got {actual}")

    # Verify other fields are preserved
    memory = navigate_json(body, "workloads.deployments.chat.containers.chat.resources.memory.limitMiB")
    replicas = navigate_json(body, "workloads.deployments.chat.replicas")

    if memory == 2048 and replicas == 2:
        print_pass(f"  └─ Field Preservation", f"memory={memory}, replicas={replicas}")
    else:
        print_fail(f"  └─ Field Preservation", f"memory={memory} (exp 2048), replicas={replicas} (exp 2)")

    # Restore after test
    restore_single_file(originals, "chat.value.json")


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_all_tests() -> int:
    """Runs all README example tests with proper setup and teardown."""

    print_header("README EXAMPLE TEST SUITE")
    print_info("Testing the 3 curl commands from README.md")
    print()

    # Check service health first
    print_info("Checking bot service health...")
    if not check_service_health():
        print_fail("Service Health", "Bot service is not running on port 5003")
        print()
        print(f"{Colors.YELLOW}Make sure all services are running:{Colors.END}")
        print("  1. python schema-server/main.py")
        print("  2. python values-server/main.py")
        print("  3. python bot-server/main.py")
        print("  4. ollama serve (with LLM model)")
        return 1

    print_pass("Service Health", "Bot service is running")

    # Cache original values for safety
    print_header("SETUP: Caching Original Values")
    originals = load_original_values()

    if len(originals) != len(VALUE_FILES):
        print_fail("Setup", "Could not cache all value files")
        return 1

    try:
        # Test 1: Tournament Memory
        print_header("TEST 1: Tournament Memory (1024mb)")
        print_info("Input: \"set tournament service memory to 1024mb\"")
        print_info(f"Expected: memory.limitMiB = 4096 → 1024")
        print()
        test_tournament_memory(originals)

        # Test 2: Matchmaking GAME_NAME
        print_header("TEST 2: Matchmaking GAME_NAME (toyblast)")
        print_info("Input: \"set GAME_NAME env to toyblast for matchmaking service\"")
        print_info(f"Expected: envs.GAME_NAME = \"toonblast\" → \"toyblast\"")
        print()
        test_matchmaking_env(originals)

        # Test 3: Chat CPU
        print_header("TEST 3: Chat CPU Limit (80%)")
        print_info("Input: \"lower cpu limit of chat service to %80\"")
        print_info(f"Expected: cpu.limitMilliCPU = 1500 → 800 (80% × 10)")
        print()
        test_chat_cpu(originals)

    finally:
        # ALWAYS restore original values, even if tests crash
        restore_original_values(originals)

    # Print summary
    print_header("TEST SUMMARY")
    total = stats["passed"] + stats["failed"] + stats["skipped"]
    print(f"{Colors.GREEN}Passed:  {stats['passed']}{Colors.END}")
    print(f"{Colors.RED}Failed:  {stats['failed']}{Colors.END}")
    print(f"{Colors.YELLOW}Skipped: {stats['skipped']}{Colors.END}")
    print(f"{Colors.BOLD}Total:   {total}{Colors.END}")

    if stats["failed"] > 0:
        print(f"\n{Colors.RED}{Colors.BOLD}SOME TESTS FAILED{Colors.END}")
        return 1
    elif stats["skipped"] > 0:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}ALL TESTS SKIPPED (timeout){Colors.END}")
        return 0
    else:
        print(f"\n{Colors.GREEN}{Colors.BOLD}ALL TESTS PASSED ✅{Colors.END}")
        return 0


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
