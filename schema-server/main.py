"""
Schema Service
--------------
Microservice that serves JSON Schemas for applications.

Environment Variables:
    SCHEMA_DIR: Directory containing schema files (default: ./data/schemas)
    HOST: Host to bind to (default: 0.0.0.0)
    PORT: Port to listen on (default: 5001)
"""

import os
import json
import uvicorn
from typing import Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# Configuration
SCHEMA_DIR = os.getenv("SCHEMA_DIR", "./data/schemas")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5001"))


# Custom Exceptions
class AppNotFoundError(Exception):
    """Raised when an application file is not found."""
    
    def __init__(self, app_name: str, file_type: str):
        self.app_name = app_name
        self.file_type = file_type
        self.message = f"{file_type} not found for application: {app_name}"
        super().__init__(self.message)


# FastAPI Application
app = FastAPI(
    title="Schema Service",
    description="Serves JSON Schemas for applications",
    version="1.0.0"
)


# Global Exception Handlers
@app.exception_handler(AppNotFoundError)
async def handle_app_not_found(request: Request, exc: AppNotFoundError):
    return JSONResponse(
        status_code=404,
        content={"detail": exc.message}
    )


@app.exception_handler(json.JSONDecodeError)
async def handle_json_decode_error(request: Request, exc: json.JSONDecodeError):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Invalid JSON format: {str(exc)}"}
    )


@app.exception_handler(Exception)
async def handle_general_exception(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {str(exc)}"}
    )


# Endpoints
@app.get("/{app_name}", response_model=Dict[str, Any])
async def get_schema(app_name: str) -> Dict[str, Any]:
    """
    Returns the JSON Schema for the specified application.
    
    Args:
        app_name: Application name (e.g., tournament, chat, matchmaking)
    
    Returns:
        The JSON Schema as a dictionary
    
    Raises:
        AppNotFoundError: If schema file does not exist (404)
        JSONDecodeError: If schema file contains invalid JSON (500)
    """
    file_path = os.path.join(SCHEMA_DIR, f"{app_name}.schema.json")
    
    if not os.path.exists(file_path):
        raise AppNotFoundError(app_name, "Schema")
    
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Entry Point
if __name__ == "__main__":
    print(f"🚀 Schema Service starting...")
    print(f"📁 Schema directory: {SCHEMA_DIR}")
    print(f"🌐 Listening on: {HOST}:{PORT}")
    
    uvicorn.run(app, host=HOST, port=PORT)
