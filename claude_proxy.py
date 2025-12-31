#!/usr/bin/env python3
"""
Claude Code Sampling Proxy

Intercepts API requests from Claude Code and injects temperature/top_p/top_k
parameters before forwarding to Anthropic's API.

Usage:
    python claude_proxy.py -t 0.7 -p 0.95 -k 40
    python claude_proxy.py --config ~/.claude/sampling.json

Then set:
    export ANTHROPIC_BASE_URL=http://localhost:8080
"""

import json
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.error
import ssl

ANTHROPIC_API_URL = "https://api.anthropic.com"
MAX_LOG_LENGTH = 200  # Truncate long values in logs

# Global config set at startup
SAMPLING_CONFIG = {
    "temperature": None,
    "top_p": None,
    "top_k": None,
}


def truncate(value, max_len=MAX_LOG_LENGTH):
    """Truncate a value for logging"""
    s = str(value)
    if len(s) > max_len:
        return s[:max_len] + f"... ({len(s)} chars)"
    return s


def load_config_file(config_path):
    """Load sampling config from a JSON file"""
    path = Path(config_path).expanduser()
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
                return {
                    "temperature": data.get("temperature") or data.get("preferred_temperature"),
                    "top_p": data.get("top_p") or data.get("preferred_top_p"),
                    "top_k": data.get("top_k") or data.get("preferred_top_k"),
                }
        except (json.JSONDecodeError, IOError) as e:
            print(f"[proxy] Warning: Could not load config file: {e}")
    return {}


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Custom logging format"""
        print(f"[proxy] {args[0]}")

    def do_POST(self):
        """Handle POST requests (main API calls)"""
        self._proxy_request("POST")

    def do_GET(self):
        """Handle GET requests"""
        self._proxy_request("GET")

    def do_OPTIONS(self):
        """Handle preflight requests"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()

    def _proxy_request(self, method):
        """Proxy the request to Anthropic's API"""
        target_url = f"{ANTHROPIC_API_URL}{self.path}"

        # Read request body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        # Inject sampling parameters for messages endpoint
        if body and "/messages" in self.path:
            body = self._inject_sampling_params(body)

        # Forward headers (except Host)
        headers = {}
        for key, value in self.headers.items():
            if key.lower() not in ("host", "content-length"):
                headers[key] = value

        # Make request to Anthropic
        try:
            req = urllib.request.Request(
                target_url,
                data=body,
                headers=headers,
                method=method,
            )

            # Create SSL context
            ctx = ssl.create_default_context()

            with urllib.request.urlopen(req, context=ctx) as response:
                # Send response back to client
                self.send_response(response.status)

                # Forward response headers
                for key, value in response.headers.items():
                    if key.lower() not in ("transfer-encoding", "connection"):
                        self.send_header(key, value)
                self.end_headers()

                # Stream response body
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    self.wfile.flush()

        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, value in e.headers.items():
                if key.lower() not in ("transfer-encoding", "connection"):
                    self.send_header(key, value)
            self.end_headers()
            self.wfile.write(e.read())

        except Exception as e:
            print(f"[proxy] Error: {e}")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def _inject_sampling_params(self, body: bytes) -> bytes:
        """Inject sampling parameters into the request body"""
        try:
            data = json.loads(body)

            # Log all request parameters (truncate long values)
            print(f"[proxy] Request parameters:")
            for key, value in data.items():
                print(f"[proxy]   {key}: {truncate(value)}")

            modified = False
            for param in ("temperature", "top_p", "top_k"):
                if SAMPLING_CONFIG.get(param) is not None:
                    old_val = data.get(param)
                    data[param] = SAMPLING_CONFIG[param]
                    if old_val != SAMPLING_CONFIG[param]:
                        print(f"[proxy] Injected {param}: {old_val} -> {SAMPLING_CONFIG[param]}")
                        modified = True

            if modified:
                return json.dumps(data).encode()
            return body

        except json.JSONDecodeError:
            return body


def main():
    parser = argparse.ArgumentParser(
        description="Claude Code Sampling Proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python claude_proxy.py -t 0.7
  python claude_proxy.py -t 0.7 -p 0.95 -k 40
  python claude_proxy.py --config ~/.claude/sampling.json
  python claude_proxy.py --config config.json -t 0.5  # CLI overrides file
        """
    )
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on (default: 8080)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--config", "-c", type=str, help="Path to JSON config file")
    parser.add_argument("--temperature", "-t", type=float, help="Temperature (0.0-1.0)")
    parser.add_argument("--top-p", "-p", type=float, help="Top-p / nucleus sampling (0.0-1.0)")
    parser.add_argument("--top-k", "-k", type=int, help="Top-k sampling (1-100+)")
    args = parser.parse_args()

    # Load config file first (if specified)
    if args.config:
        file_config = load_config_file(args.config)
        SAMPLING_CONFIG.update({k: v for k, v in file_config.items() if v is not None})
        print(f"[proxy] Loaded config from: {args.config}")

    # CLI args override config file
    if args.temperature is not None:
        SAMPLING_CONFIG["temperature"] = args.temperature
    if args.top_p is not None:
        SAMPLING_CONFIG["top_p"] = args.top_p
    if args.top_k is not None:
        SAMPLING_CONFIG["top_k"] = args.top_k

    # Show current config
    print(f"[proxy] Sampling config: {SAMPLING_CONFIG}")
    print(f"[proxy] Starting proxy on http://{args.host}:{args.port}")
    print(f"[proxy] Forwarding to {ANTHROPIC_API_URL}")
    print()
    print("To use with Claude Code, run:")
    print(f"  ANTHROPIC_BASE_URL=http://{args.host}:{args.port} claude")
    print()

    server = HTTPServer((args.host, args.port), ProxyHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[proxy] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    main()
