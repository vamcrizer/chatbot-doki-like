"""
AI Companion API — Development server entry point.

Usage:
    python run.py              # default: port 8080, auto-reload
    python run.py --port 9000  # custom port
    python run.py --prod       # production mode (no reload, 4 workers)
"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description="AI Companion API server")
    parser.add_argument("--port", type=int, default=8080, help="Port (default: 8080)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--prod", action="store_true", help="Production mode (no reload, 4 workers)")
    args = parser.parse_args()

    if args.prod:
        uvicorn.run(
            "api.main:app",
            host=args.host,
            port=args.port,
            workers=4,
            access_log=True,
        )
    else:
        uvicorn.run(
            "api.main:app",
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=["api", "core", "characters", "db", "memory"],
            log_level="info",
        )


if __name__ == "__main__":
    main()
