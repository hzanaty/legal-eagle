import subprocess, time, urllib.request

def start_server(directory: str, port: int = 9999) -> subprocess.Popen:
    proc = subprocess.Popen(
        ["python3", "-m", "http.server", str(port), "--directory", directory],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://localhost:{port}/", timeout=0.2)
            return proc
        except Exception:
            time.sleep(0.1)
    raise RuntimeError(f"Feed server on port {port} did not start in 5s")

def stop_server(proc):
    proc.terminate()
    proc.wait(timeout=5)
