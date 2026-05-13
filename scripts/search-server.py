import json
import os
import re
import sqlite3
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

DB_DIR = os.path.dirname(os.path.abspath(__file__))

def build_match(raw: str) -> str:
    if not raw:
        return ""
    if re.search(r'[""*]| OR | AND | NOT ', raw):
        return raw
    return " ".join(f"{w}*" for w in raw.strip().split())

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # 精简日志，不写访问日志到终端
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)

        # ── /api/meta ──
        if parsed.path == "/api/meta":
            meta_path = os.path.join(DB_DIR, "meta.json")
            if not os.path.exists(meta_path):
                self._error(404, "meta.json not found")
                return
            with open(meta_path, "r", encoding="utf-8") as f:
                body = f.read().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        # ── /api/search ──
        if parsed.path == "/api/search":
            q = qs.get("q", [""])[0].strip()
            lib = qs.get("lib", [""])[0]
            vol = qs.get("vol", [""])[0]
            limit = min(int(qs.get("limit", ["50000"])[0]), 100000)

            if not q:
                self._error(400, "Missing q")
                return

            match_q = build_match(q)

            # 定位目标数据库
            meta_path = os.path.join(DB_DIR, "meta.json")
            targets = []
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                for v in meta.get("volumes", []):
                    if lib and v["library"] != lib:
                        continue
                    if vol and v["volume"] != vol:
                        continue
                    targets.append(v["db_file"])
                    if lib and vol:
                        break

            results = []
            for db_file in targets:
                db_path = os.path.join(DB_DIR, db_file)
                if not os.path.exists(db_path):
                    continue
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                try:
                    rows = conn.execute(
                        """
                        SELECT d.library, d.volume, d.title, d.url_path, d.headings,
                               snippet(docs_fts, '<mark>', '</mark>', '…', -1, 32) as snippet
                        FROM docs_fts
                        JOIN docs d ON docs_fts.rowid = d.id
                        WHERE docs_fts MATCH ?
                        ORDER BY d.file_path
                        LIMIT ?
                        """,
                        (match_q, limit - len(results)),
                    ).fetchall()
                    results.extend([dict(r) for r in rows])
                    if len(results) >= limit:
                        break
                finally:
                    conn.close()

            body = json.dumps(
                {"query": q, "match": match_q, "total": len(results), "results": results},
                ensure_ascii=False,
            ).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(body)
            return

        self._error(404, "Not Found")

    def _error(self, code, msg):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps({"error": msg}).encode())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 49107))
    print(f"Search API running at http://localhost:{port}")
    print("  /api/meta   → 索引元数据")
    print("  /api/search → 全文检索")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()