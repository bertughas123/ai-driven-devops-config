"""
Values Service
--------------
Microservice that serves current configuration values for applications.

Environment Variables:
    VALUES_DIR: Directory containing value files (default: ./data/values)
    HOST: Host to bind to (default: 0.0.0.0)
    PORT: Port to listen on (default: 5002)
"""

import os
import json
import uvicorn
from typing import Dict, Any
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


# Configuration
VALUES_DIR = os.getenv("VALUES_DIR", "./data/values")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5002"))


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
    title="Values Service",
    description="Serves current configuration values for applications",
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
async def get_values(app_name: str) -> Dict[str, Any]:
    """
    Returns the current configuration values for the specified application.
    
    Args:
        app_name: Application name (e.g., tournament, chat, matchmaking)
    
    Returns:
        The configuration values as a dictionary
    
    Raises:
        AppNotFoundError: If values file does not exist (404)
        JSONDecodeError: If values file contains invalid JSON (500)
    """
    file_path = os.path.join(VALUES_DIR, f"{app_name}.value.json")
    
    if not os.path.exists(file_path):
        raise AppNotFoundError(app_name, "Values")
    
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Entry Point
if __name__ == "__main__":
    print(f"🚀 Values Service starting...")
    print(f"📁 Values directory: {VALUES_DIR}")
    print(f"🌐 Listening on: {HOST}:{PORT}")
    
    uvicorn.run(app, host=HOST, port=PORT)
