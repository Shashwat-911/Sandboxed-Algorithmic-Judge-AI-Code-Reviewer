import socket
import threading
import time
import pytest
import uvicorn
import httpx
import main


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server():
    """Starts the ATF FastAPI application in a background thread for browser E2E tests."""
    port = _get_free_port()
    config = uvicorn.Config(main.app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    base_url = f"http://127.0.0.1:{port}"

    # Wait for the health check to succeed
    deadline = time.time() + 10
    started = False
    while time.time() < deadline:
        try:
            res = httpx.get(f"{base_url}/health", timeout=1.0)
            if res.status_code == 200:
                started = True
                break
        except Exception:
            time.sleep(0.15)

    if not started:
        raise RuntimeError("Failed to start FastAPI test server within 10 seconds.")

    yield base_url

    server.should_exit = True
    server_thread.join(timeout=3)
