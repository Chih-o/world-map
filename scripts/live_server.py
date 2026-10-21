"""Run the site on this computer with live stock data.

Serves the repository at http://localhost:8000 and answers /api/tsmc.json with fresh
data, rebuilt at most every 25 seconds, so tsmc.html can update every 30 seconds.
Stop with Ctrl+C or by closing the window.
"""
import http.server
import json
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from fetch_tsmc import build

PORT = 8000
TTL = 25
cache = {"t": 0.0, "body": b""}
lock = threading.Lock()


def live_json():
    with lock:
        if time.time() - cache["t"] > TTL:
            try:
                cache["body"] = json.dumps(build(), ensure_ascii=False).encode("utf-8")
                cache["t"] = time.time()
                print(time.strftime("%H:%M:%S"), "資料已更新")
            except Exception as e:
                print(time.strftime("%H:%M:%S"), "更新失敗：", e)
                if not cache["body"]:
                    raise
        return cache["body"]


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        if self.path.split("?")[0] == "/api/tsmc.json":
            try:
                body = live_json()
            except Exception as e:
                self.send_error(502, str(e))
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, *args):
        pass


def main():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://localhost:{PORT}/tsmc.html"
    print(f"即時模式已啟動：{url}")
    print("資料每 30 秒更新。要停止請按 Ctrl+C 或關閉這個視窗。")
    threading.Timer(1, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
