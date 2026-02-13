"""
Package entry point for Summary Bot NG.

Ultra-resilient entry point that GUARANTEES a web server starts,
even if all other imports fail. This is critical for Fly.io health checks.
"""
import sys
import os

# Immediately print to stderr for debugging
print("=== Summary Bot NG package loading ===", flush=True, file=sys.stderr)

# Store any startup errors for the health endpoint
_startup_error = None


def create_emergency_app(error_message: str):
    """Create a minimal FastAPI app for emergency mode."""
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    app = FastAPI(title="Summary Bot NG - Emergency Mode")

    @app.get("/health")
    async def health():
        return JSONResponse(
            status_code=200,
            content={
                "status": "emergency",
                "error": error_message,
                "message": "Main application failed to start. Check container logs.",
                "version": "2.0.0",
                "env": {
                    "DISCORD_TOKEN_SET": bool(os.environ.get("DISCORD_TOKEN")),
                    "OPENROUTER_API_KEY_SET": bool(os.environ.get("OPENROUTER_API_KEY")),
                    "FLY_APP_NAME": os.environ.get("FLY_APP_NAME", "not-set"),
                }
            }
        )

    @app.get("/")
    async def root():
        return {
            "status": "emergency",
            "error": error_message,
            "docs": "/docs"
        }

    return app


def run_emergency_server(error_message: str):
    """Start emergency server synchronously."""
    import uvicorn

    host = os.environ.get("WEBHOOK_HOST", "0.0.0.0")
    port = int(os.environ.get("WEBHOOK_PORT", "5000"))

    print(f"EMERGENCY: Starting fallback server on {host}:{port}", flush=True, file=sys.stderr)
    print(f"EMERGENCY: Error was: {error_message}", flush=True, file=sys.stderr)

    app = create_emergency_app(error_message)
    uvicorn.run(app, host=host, port=port, log_level="info")


def run_main():
    """Try to run the main application, fallback to emergency server on failure."""
    global _startup_error

    try:
        print("Step 1: Importing main module...", flush=True, file=sys.stderr)
        from .main import main
        print("Step 2: Main module imported OK", flush=True, file=sys.stderr)

        import asyncio
        print("Step 3: Starting async main()...", flush=True, file=sys.stderr)
        asyncio.run(main())

    except Exception as e:
        import traceback
        _startup_error = f"{type(e).__name__}: {e}"
        print(f"FATAL: {_startup_error}", flush=True, file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

        # Start emergency server
        run_emergency_server(_startup_error)


if __name__ == "__main__":
    print("=== Entry point reached ===", flush=True, file=sys.stderr)
    run_main()
