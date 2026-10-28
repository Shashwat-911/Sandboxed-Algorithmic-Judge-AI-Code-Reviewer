"""Helper to wait for local server to become healthy."""
import sys
import time
import urllib.request

url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000/health"
timeout = float(sys.argv[2]) if len(sys.argv) > 2 else 15.0

start = time.time()
while time.time() - start < timeout:
    try:
        with urllib.request.urlopen(url, timeout=1.0) as resp:
            if resp.status == 200:
                print(f"[OK] Server is ready at {url}")
                sys.exit(0)
    except Exception:
        time.sleep(0.3)

print(f"[WARN] Server did not respond within {timeout}s.")
sys.exit(1)
