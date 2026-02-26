## 1. System Architecture

### 1.1 FastAPI & Asynchronous Design
FastAPI provides a modern, high-performance foundation for the system:

- Async/await prevents blocking during slow LLM calls — server stays responsive, ensuring responsiveness for concurrent tasks like health checks
- Built-in path parameter validation — no manual if-else checks needed
- Auto-generated /docs (Swagger UI) for instant API testing

### 1.2 Microservice Separation
- 3 services, each with one job: Schema serves schemas, Values serves configs, Bot runs LLM logic
- Fault isolation: one service down ≠ whole system down
- Bot uses httpx (instead of requests) to leverage FastAPI's async architecture — non-blocking HTTP calls during LLM wait
- All config via env vars (OLLAMA_HOST, LLM_MODEL, etc.) — same code, any environment (the twelve-factor app principles)
- Environment variables over CLI arguments: README specified `--schema-dir` and `--listen host:port`, but env vars (`SCHEMA_DIR`, `HOST`, `PORT`) work natively with Docker Compose, require no arg parsing code, and allow runtime config changes without rebuilding images

## 2. LLM Model Selection & Reasoning

### 2.1 Why Ollama?
- Local inference: no data leaves the machine, fully offline after first model download
- Privacy: config files contain sensitive infra details; cloud APIs would be a security risk
- Docker-native: `ollama/ollama:latest` in Compose stack, auto model pull via `init-ollama`

### 2.2 Model Selection Journey
- While Llama 3.1 8B is technically superior in terms of IFEval scores, the actual bottleneck was the input context size rather than model capability.
    - **Attempt 1 Llama 3.1 (8B), no Schema Pruning**: Full JSON (~700 token values + ~1700-line schema) sent to LLM. On 16GB RAM + GTX 1650 (4GB VRAM): 10+ minutes per request, **"lazy output"** (returned first few keys, dropped the rest), system-wide memory pressure. **Failed.**
    - **Attempt 2 Llama 3.2 (3B), no Schema Pruning**: Faster (~3-4 minutes) but couldn't process full context, especially in deeply nested structures (e.g.,`workloads.deployments.tournament.containers.tournament.resources.memory`) irrelevant values were modified or some keys were being dropped. 1 / 8 tests passed. **Failed.**
    - **Attempt 3 Phi-3 (3.8B)**: Slower than Llama 3.2 (~3-4 minutes), worse JSON compliance — injected explanation text even with `format="json"`. **Failed.**
    - **Solution: architecture change, not model change**: The problem was input size, not model capability. Redesigned the pipeline:
        1. **Schema Pruning**: ~1700-line schema → ~10-line sub-schema (`extract_schema_fragment()`)
        2. **Micro-Fragment**: ~700 token values → ~30 token fragment (`detect_target_path()` + `get_nested_value()`)
        3. **Deep Merge**: LLM output merged with original (`deep_merge()`), preserving any skipped keys

After this change, Llama 3.2 3B passed all 8 test cases consistently(see test_results.md for detailed results). Same model — different input strategy.

### 2.3 Final Decision: Llama 3.2 (3B)
- 2 GB disk / 2-3 GB VRAM — fits GTX 1650 comfortably
- 50-60s per request with Micro-Fragment architecture
- Schema Pruning + small context → consistent, correct JSON output
> **Key insight**: The bottleneck was input size, not model size. Right architecture makes a 3B model outperform an 8B one.

## 3. Prompt Engineering
### 3.1 Two-Stage LLM Pipeline
- **Classifier** extracts target app name (`chat`, `matchmaking`, `tournament`). Single word output, 3 few-shot examples, `temperature=0.0`, `num_ctx=2048`(to avoid unnecessarily overloading the computer by using 128k context)
- **Generator** edits a micro JSON fragment. Receives pruned schema + current values + request. Returns modified JSON only, `temperature=0.1`, `num_ctx=4096`(to avoid unnecessarily overloading the computer by using 128k context), `format="json"`
### 3.2 Classifier Design
- User input wrapped in `<request>` tags acts as a boundary to prevent prompt injection (LLM only processes content inside tags, ignores anything outside)
- Strict role constraint: ignores numbers, verbs, parameter names outputs only the app name
### 3.3 Generator Design
- 4-step logical instructions: **IDENTIFY** → **CONVERT** → **RETAIN** → **NEW KEYS**
- Domain-specific conversions as explicit rules: `"cpu %80" → 800 milliCPU`, `"2048mb" → 2048 MiB`
- One generic few-shot example keeps prompt short and model-agnostic
- JSON minification via `json.dumps(separators=(',',':'))` removes all whitespace, reduces token count before sending to LLM
- `format="json"` forces Ollama to return pure JSON only, so no need to strip markdown fences or parse prose from the output

## 4. Micro-Fragment + Schema Pruning Architecture

**Problem**: Small models fail on large JSON, "lazy output" (drop keys) and "flattening" (merge nested structures).

**Solution**: Send only the relevant fragment, not the full JSON. Five-step pipeline:

1. [detect_target_path()]: maps user request to JSON path via keyword matching
2. [get_nested_value()] + [extract_schema_fragment()]: extracts micro fragment + matching sub-schema
3. [ollama.chat()]: LLM receives only the tiny fragment
4. [deep_merge()]: merges LLM output with original, preserving skipped keys
5. [set_nested_value()]: injects updated fragment back into full JSON

**Result**: Values ~700 → **~30 tokens**, Schema ~1700 → **~10 lines**. This is what makes 3B viable.

## 5. Safety & Validation

LLMs are non-deterministic, so three defense layers protect against bad output:

- **Schema Validation**: `jsonschema.validate()` checks the final full JSON against the full schema before saving
- **Safety Net**: if validation fails, original values are returned unchanged — no corrupted config ever reaches disk
- **Deep Merge**: even if LLM drops a key, [deep_merge()] preserves the original value from the base fragment

Error codes: `400` unrecognized app name, `404` schema/values not found, `500` validation failure or invalid LLM JSON, `503` Ollama or upstream service unreachable/timeout

## 6. Inter-Service Communication

- Bot calls Schema and Values services via `httpx.AsyncClient` (async, non-blocking)
- Timeout: `900s` to accommodate slow LLM inference on consumer hardware (for my own slow computer)
- Error handling: `ConnectError` / `TimeoutException` → returns 503
- Docker Compose service discovery: container names as hostnames (`http://schema-server:5001`, `http://values-server:5002`, `http://ollama:11434`)

## 7. End-to-End Request Flow

User sends `POST /message` with for example `{"input": "set tournament memory to 2048mb"}`. The pipeline:

1. **Classifier LLM** extracts app name → `"tournament"` (`temperature=0.0`)
2. **Fetch data** (async): `GET schema-server:5001/tournament` + `GET values-server:5002/tournament`
3. [detect_target_path()] maps request to JSON path → `workloads.deployments.tournament.containers.tournament.resources.memory`
4. [get_nested_value()] + [extract_schema_fragment()] extracts micro fragment + pruned schema
5. **Generator LLM** edits the fragment (`temperature=0.1`, `format="json"`)
6. [deep_merge()] merges LLM output with original fragment, then [set_nested_value()] injects back into full JSON
7. [validate_against_schema()] validates final JSON against full schema
8. If valid → [save_values()] writes to disk, returns HTTP 200. If invalid → **Safety Net** returns original values unchanged.

## 8. Docker & Containerization

The entire system runs as 5 containers via [docker-compose.yml]: Ollama (LLM engine), init-ollama (one-shot model puller), and the three app services.

All app services use `python:3.11-slim` with `curl` installed for healthchecks. A [.dockerignore] keeps images lean by excluding tests, docs, and IDE files.

The `init-ollama` container automatically pulls the LLM model on first startup using a simple curl request, then exits. No manual model setup needed.

Healthchecks are curl-based: Ollama checks `ollama list`, app services hit their own endpoints. Bot Service only starts after all dependencies are healthy (`depends_on: condition: service_healthy`).

The `./data` directory is shared across services (read-only for schema, read-write for values). Ollama model files persist via a named volume (`ollama_data`).

All configuration lives in environment variables. `LLM_MODEL` defaults to `llama3.2` but can be overridden without rebuilding any image.

## 9. Test Strategy

- [tests/test_phase3.py]: 8 tests covering service health, schema constraint enforcement (max, enum, required), and README curl examples
- [tests/test_phase3_forReadme.py]: 3 focused tests validating exact README examples with field-by-field assertions
- All tests backup and restore original value files before/after each test

## 10. How to Run

Start the entire stack:
```bash
docker compose up --build
```
First run takes a few minutes — init-ollama automatically pulls the Llama 3.2 model (~2 GB).

Linux/macOS:
```bash
curl -X POST http://localhost:5003/message \
  -H "Content-Type: application/json" \
  -d '{"input": "set tournament service memory to 1024mb"}'
```
Windows PowerShell:
```bash
curl.exe --% -X POST http://localhost:5003/message -H "Content-Type: application/json" -d "{\"input\": \"set tournament service memory to 1024mb\"}"
```

---

> For detailed implementation notes and per-phase development logs, see the `development_notes/` directory.
