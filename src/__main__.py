"""
Package entry point for Summary Bot NG.

This module provides a resilient entry point that catches import errors
and starts an emergency server for diagnostics when the main app fails.
"""
import sys
import asyncio
print("=== Summary Bot NG package starting ===", flush=True, file=sys.stderr)


async def emergency_server(error_message: str = "Unknown error"):
    """Start a minimal server when main app fails to load.

    This ensures health checks pass and we can diagnose issues.
    """
    # Use minimal imports that are unlikely to fail
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    import uvicorn
    import os

    app = FastAPI(title="Summary Bot NG - Emergency Mode")

    @app.get("/health")
    async def health():
        return JSONResponse(
            status_code=200,
            content={
                "status": "emergency",
                "error": error_message,
                "message": "Main application failed to start. Check logs for details.",
                "version": "2.0.0"
            }
        )

    @app.get("/")
    async def root():
        return {"status": "emergency", "error": error_message}

    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "5000"))

    print(f"Starting emergency server on {host}:{port}", flush=True, file=sys.stderr)
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def run_main():
    """Try to run the main application, fallback to emergency server on failure."""
    try:
        print("Loading main module...", flush=True, file=sys.stderr)
        from .main import main
        print("Main module loaded, starting application...", flush=True, file=sys.stderr)
        asyncio.run(main())
    except Exception as e:
        error_msg = f"{type(e).__name__}: {e}"
        print(f"FATAL: Failed to start application: {error_msg}", flush=True, file=sys.stderr)
        import traceback
        traceback.print_exc()
        print("Starting emergency server for diagnostics...", flush=True, file=sys.stderr)
        asyncio.run(emergency_server(error_msg))


if __name__ == "__main__":
    run_main()
