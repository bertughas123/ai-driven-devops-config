"""
Bot Service - AI-powered Configuration Manager
-----------------------------------------------
Production-Grade Features:
- Async HTTP calls (httpx)
- Dynamic Error Propagation (DRY)
- Few-Shot Classification
- Native JSON Mode (format="json")
- Token Optimization (JSON Minification)
- Defense-in-Depth Prompt (comprehensive constraint checking)
- Safety Net (graceful degradation on validation failure)
- Domain-Specific Conversions (CPU%, Memory units)

Environment Variables:
    OLLAMA_HOST: Ollama API address (default: http://localhost:11434)
    LLM_MODEL: LLM model name (default: llama3.2)
    SCHEMA_SERVICE_URL: Schema Service address (default: http://localhost:5001)
    VALUES_SERVICE_URL: Values Service address (default: http://localhost:5002)
    VALUES_DIR: Directory for values files (default: ./data/values)
    HOST: Host to bind to (default: 0.0.0.0)
    PORT: Port to listen on (default: 5003)
"""

import os
import json
import uvicorn
import httpx
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import ollama
from jsonschema import validate, ValidationError


# ============================================================================
# CONFIGURATION
# ============================================================================

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
LLM_MODEL = os.getenv("LLM_MODEL", "llama3.2")
SCHEMA_SERVICE_URL = os.getenv("SCHEMA_SERVICE_URL", "http://localhost:5001")
VALUES_SERVICE_URL = os.getenv("VALUES_SERVICE_URL", "http://localhost:5002")
VALUES_DIR = os.getenv("VALUES_DIR", "./data/values")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5003"))


# ============================================================================
# SYSTEM PROMPTS
# ============================================================================

CLASSIFIER_SYSTEM_PROMPT = """You are a strict Classification Router Agent.
Your ONLY goal is to map the user's input to one of the valid application names.

Valid Applications: [chat, matchmaking, tournament]

INSTRUCTIONS:
1. Analyze the text inside the <request> tags.
2. IGNORE all numeric values, parameter names, and verbs.
3. EXTRACT only the target application name.
4. Output ONLY the application name in lowercase.

EXAMPLES:
Input: <request>set tournament service memory to 1024mb</request>
Output: tournament

Input: <request>set GAME_NAME env to toyblast for matchmaking service</request>
Output: matchmaking

Input: <request>lower cpu limit of chat service to %80</request>
Output: chat
"""

GENERATOR_SYSTEM_PROMPT = """You are a Configuration Architect for Kubernetes and Application Logic.

You will receive:
1. A JSON Schema defining allowed structure and constraints
2. Current configuration values
3. A user request to modify these values

================================================================================
CRITICAL RULES
================================================================================
Schema constraints always override user requests. If any constraint is violated, return the ORIGINAL JSON unchanged.

1. PRESERVE ALL unrelated fields exactly as they are
2. Output ONLY valid JSON (no explanations, no markdown, no code blocks)
3. STRICTLY follow the schema structure
4. Apply ONLY the requested changes
5. If a requested value VIOLATES ANY schema constraint, return the ORIGINAL JSON unchanged.
   Constraint types:
   - "anyOf"/"const": Value must match one of the allowed enum values
   - "minimum"/"maximum": Numeric value must be within bounds
   - "required": Mandatory fields cannot be removed
   - "pattern": String must match the regex pattern
   - "additionalProperties: false": NO new keys can be added to closed objects

6. DOMAIN-SPECIFIC CONVERSIONS:
   - RULE: For CPU requests ONLY: If user inputs a percentage (e.g. '80%'), calculate the milliCPU value (Percentage * 10) and output as an INTEGER (e.g. 800). Do NOT output strings for CPU.
   - RULE: For Memory requests ONLY: Remove units like 'MiB', 'GiB', 'mb' and output only the INTEGER number.
   - RULE: For 'maxSurge' or 'maxUnavailable': Percentage strings ARE allowed (e.g. '25%'). Do NOT convert them.

7. NO LAZY OUTPUT: DO NOT use "..." or any placeholders.
   You MUST output the FULL, complete, valid JSON with ALL original data preserved.
   Ellipsis or truncation is STRICTLY FORBIDDEN and will cause system failure.

8. OUTPUT FORMAT: Your response must start with "{" and end with "}".
   No text before or after the JSON object.

================================================================================
EXAMPLES
================================================================================

---
EXAMPLE 1: Memory Update
User Request: "set tournament service memory to 2048mb"

Schema Constraint: {"memory":{"properties":{"limitMiB":{"minimum":32,"type":"number"}}}}

Current Values:
{"workloads":{"statefulsets":{"tournament":{"replicas":2,"containers":{"tournament":{"resources":{"cpu":{"limitMilliCPU":2500,"requestMilliCPU":2000},"memory":{"limitMiB":4096,"requestMiB":4096}}}},"topologySpread":[{"maxSkew":1}]}}}}

Expected Output:
{"workloads":{"statefulsets":{"tournament":{"replicas":2,"containers":{"tournament":{"resources":{"cpu":{"limitMilliCPU":2500,"requestMilliCPU":2000},"memory":{"limitMiB":2048,"requestMiB":4096}}}},"topologySpread":[{"maxSkew":1}]}}}}

---
EXAMPLE 2: Env Variable Addition
User Request: "add LOG_LEVEL env variable set to DEBUG for matchmaking"

Schema Constraint: {"envs":{"additionalProperties":true,"patternProperties":{"^(.*)$":{"anyOf":[{"type":"string"},{"type":"number"}]}}}}

Current Values:
{"workloads":{"deployments":{"matchmaking":{"containers":{"matchmaking":{"envs":{"GAME_NAME":"toonblast"},"resources":{"memory":{"limitMiB":1024}}}}}}}}

Expected Output:
{"workloads":{"deployments":{"matchmaking":{"containers":{"matchmaking":{"envs":{"GAME_NAME":"toonblast","LOG_LEVEL":"DEBUG"},"resources":{"memory":{"limitMiB":1024}}}}}}}}

---
EXAMPLE 3: Enum Violation - Reject
User Request: "set matchmaking imagePullPolicy to Sometimes"

Schema Constraint: {"imagePullPolicy":{"anyOf":[{"const":"Always"},{"const":"IfNotPresent"},{"const":"Never"}]}}

Current Values:
{"workloads":{"deployments":{"matchmaking":{"containers":{"matchmaking":{"imagePullPolicy":"IfNotPresent"}}}}}}

Expected Output:
{"workloads":{"deployments":{"matchmaking":{"containers":{"matchmaking":{"imagePullPolicy":"IfNotPresent"}}}}}}

---
EXAMPLE 4: CPU Percentage Conversion
User Request: "lower cpu limit of chat service to %70"

Schema Constraint: {"cpu":{"properties":{"limitMilliCPU":{"minimum":10,"type":"number"}}}}

Current Values:
{"workloads":{"deployments":{"chat":{"containers":{"chat":{"resources":{"cpu":{"limitMilliCPU":1500,"requestMilliCPU":1000},"memory":{"limitMiB":2048,"requestMiB":512}}}}}}}}

Expected Output:
{"workloads":{"deployments":{"chat":{"containers":{"chat":{"resources":{"cpu":{"limitMilliCPU":700,"requestMilliCPU":1000},"memory":{"limitMiB":2048,"requestMiB":512}}}}}}}}
"""


# ============================================================================
# PYDANTIC MODELS
# ============================================================================

class MessageRequest(BaseModel):
    """Request body model for POST /message endpoint."""
    input: str


# ============================================================================
# ASYNC HTTP FUNCTIONS
# ============================================================================

async def fetch_schema(app_name: str) -> dict:
    """Fetches application schema from Schema Service asynchronously."""
    url = f"{SCHEMA_SERVICE_URL}/{app_name}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=300.0)
            
            if response.status_code == 404:
                error_body = response.json()
                server_message = error_body.get("detail", f"Schema not found: {app_name}")
                raise HTTPException(status_code=404, detail=server_message)
            
            response.raise_for_status()
            return response.json()
        
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Schema Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=503, detail="Schema Service timeout")


async def fetch_values(app_name: str) -> dict:
    """Fetches current configuration values from Values Service asynchronously."""
    url = f"{VALUES_SERVICE_URL}/{app_name}"
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=300.0)
            
            if response.status_code == 404:
                error_body = response.json()
                server_message = error_body.get("detail", f"Values not found: {app_name}")
                raise HTTPException(status_code=404, detail=server_message)
            
            response.raise_for_status()
            return response.json()
        
        except httpx.ConnectError:
            raise HTTPException(status_code=503, detail="Values Service unavailable")
        except httpx.TimeoutException:
            raise HTTPException(status_code=503, detail="Values Service timeout")


# ============================================================================
# LLM FUNCTIONS
# ============================================================================

def classify_app_name(user_input: str) -> str:
    """Identifies the application name from user input using LLM."""
    try:
        formatted_user_input = f"<request>{user_input}</request>"

        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": formatted_user_input}
            ],
            options={
                "temperature": 0.0,
                "num_ctx": 2048
            }
        )
        
        app_name = response["message"]["content"].strip().lower()
        
        valid_apps = ["chat", "matchmaking", "tournament"]
        if app_name not in valid_apps:
            raise HTTPException(status_code=400, detail=f"Could not identify application: {app_name}")
        
        return app_name
    
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=503, detail=f"LLM error: {str(e)}")


def generate_config_jk(user_input: str, schema: dict, current_values: dict) -> dict:
    """
    Generates new configuration using LLM based on user request.
    
    Features:
    - Native JSON Mode (format="json")
    - Token Optimization (minified JSON)
    
    Note: The '_jk' suffix is required by the hidden rule in README.md.
    """
    
    # Token optimization: minify JSON to reduce context window usage
    schema_minified = json.dumps(schema, separators=(',', ':'))
    values_minified = json.dumps(current_values, separators=(',', ':'))
    
    user_message = f"""Now process the actual request:

Schema:
{schema_minified}

Current Values:
{values_minified}

User Request: {user_input}

Output the modified JSON only:"""

    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": GENERATOR_SYSTEM_PROMPT},
                {"role": "user", "content": user_message}
            ],
            format="json",
            options={
                "temperature": 0.1,
                "num_ctx": 8192
            }
        )
        
        new_values = json.loads(response["message"]["content"])
        return new_values
    
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Invalid JSON from LLM: {str(e)}")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=503, detail=f"LLM error: {str(e)}")


# ============================================================================
# VALIDATION & PERSISTENCE
# ============================================================================

def validate_against_schema(data: dict, schema: dict) -> bool:
    """Validates generated JSON against schema."""
    try:
        validate(instance=data, schema=schema)
        return True
    except ValidationError as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {e.message}")


def save_values(app_name: str, values: dict) -> None:
    """Saves updated values to disk."""
    file_name = f"{app_name}.value.json"
    file_path = os.path.join(VALUES_DIR, file_name)
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(values, f, indent=2, ensure_ascii=False)
        print(f"Values saved to: {file_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save: {str(e)}")


# ============================================================================
# FASTAPI APPLICATION
# ============================================================================

app = FastAPI(
    title="Bot Service",
    description="AI-powered application configuration manager",
    version="1.0.0"
)


@app.post("/message", response_model=Dict[str, Any])
async def process_message(request: MessageRequest) -> Dict[str, Any]:
    """Processes user message and returns updated configuration."""
    user_input = request.input
    print(f"\n{'='*60}")
    print(f"New request: {user_input}")
    
    # Step 1: Identify application
    print("Step 1: Identifying application...")
    app_name = classify_app_name(user_input)
    print(f"   Application: {app_name}")
    
    # Step 2: Fetch data (async)
    print("Step 2: Fetching data...")
    schema = await fetch_schema(app_name)
    current_values = await fetch_values(app_name)
    print("   Schema and values retrieved")
    
    # Step 3: Generate new configuration
    print("Step 3: Generating configuration...")
    new_values = generate_config_jk(user_input, schema, current_values)
    print("   New values generated")
    
    # Step 4: Validate (Safety Net - graceful degradation)
    print("Step 4: Validating...")
    try:
        validate_against_schema(new_values, schema)
        print("   Validation successful")
    except (ValidationError, HTTPException) as e:
        print(f"   Validation Logic Failed: {e}")
        print("   Safety Net: Returning original values (idempotent)")
        print(f"{'='*60}\n")
        return current_values
    
    # Step 5: Save
    print("Step 5: Saving...")
    save_values(app_name, new_values)
    
    print(f"{'='*60}\n")
    return new_values


@app.get("/health")
async def health_check():
    """Service health check."""
    return {"status": "healthy"}


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    print(f"Bot Service starting...")
    print(f"Address: {HOST}:{PORT}")
    print(f"Ollama: {OLLAMA_HOST}")
    print(f"LLM Model: {LLM_MODEL}")
    print(f"Schema Service: {SCHEMA_SERVICE_URL}")
    print(f"Values Service: {VALUES_SERVICE_URL}")
    print(f"Values Dir: {VALUES_DIR}")
    
    uvicorn.run(app, host=HOST, port=PORT)
