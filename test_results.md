# Test Results — Phase 3 Integration Test Suite

## Summary

| | Count |
|---|---|
| Passed | 8 |
| Failed | 0 |
| Skipped | 0 |
| **Total** | **8** |

**ALL TESTS PASSED**

## Category A: Service Health

| # | Test | Result | Details |
|---|---|---|---|
| 1 | Service Health | ✅ PASS | Bot service is running |
| 2 | Unknown App Error Handling | ✅ PASS | Returned 400 with proper error handling |

## Category B: LLM & Constraints

| # | Test | Result | Details |
|---|---|---|---|
| 3 | Max Violation — Tournament Replicas > 999 | ✅ PASS | Constraint enforced, replicas=2 |
| 4 | Enum Violation — Matchmaking imagePullPolicy | ✅ PASS | Original preserved, imagePullPolicy=IfNotPresent |
| 5 | Required Field — Matchmaking Image | ✅ PASS | Required field preserved, image=matchmaking:1.2.3 |

## Category C: README Examples (Happy Path)

| # | Test | Result | Details |
|---|---|---|---|
| 6 | Tournament Memory (1024mb) | ✅ PASS | memory.limitMiB=1024 |
| 7 | Matchmaking GAME_NAME Env | ✅ PASS | GAME_NAME=toyblast |
| 8 | Chat CPU Limit (80%) | ✅ PASS | CPU changed: 1500 → 800 |

## Data Safety

- Original value files cached before tests
- All value files restored after tests (chat, matchmaking, tournament)
