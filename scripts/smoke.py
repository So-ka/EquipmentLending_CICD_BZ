#!/usr/bin/env python3
"""End-to-end smoke test against a *running* server (stdlib only, so it can be piped into a container).

    python scripts/smoke.py http://localhost:8000 write   # create data, check rules
    python scripts/smoke.py http://localhost:8000 read    # check the data survived a restart
Exit code 0 = pass.
"""
import json
import sys
import time
import urllib.error
import urllib.request


def call(base, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(label, got, want):
    ok = got == want
    print(("PASS" if ok else "FAIL"), label, "" if ok else f"(got {got!r}, wanted {want!r})")
    if not ok:
        sys.exit(1)


def wait_ready(base, seconds=30):
    for _ in range(seconds):
        try:
            if call(base, "GET", "/api/v1/health")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(1)
    print("FAIL server never became healthy")
    sys.exit(1)


def main():
    base, mode = sys.argv[1].rstrip("/"), sys.argv[2]
    wait_ready(base)
    api = "/api/v1"
    if mode == "write":
        s, eq = call(base, "POST", f"{api}/equipment", {"name": "CI projector"})
        check("create equipment -> 201", s, 201)
        s, loan = call(base, "POST", f"{api}/loans",
                       {"equipment_id": eq["id"], "from_date": "2030-01-01", "to_date": "2030-01-05"})
        check("create loan -> 201", s, 201)
        s, body = call(base, "POST", f"{api}/loans",
                       {"equipment_id": eq["id"], "from_date": "2030-01-05", "to_date": "2030-01-09"})
        check("overlapping loan -> 409", (s, body["error"]["code"]), (409, "conflict"))
        s, body = call(base, "GET", f"{api}/equipment?available_from=2030-01-02&available_to=2030-01-03")
        check("busy equipment not offered", body["count"], 0)
        s, _ = call(base, "POST", f"{api}/loans/{loan['id']}/cancel")
        check("cancel loan -> 200", s, 200)
        s, body = call(base, "GET", f"{api}/equipment?available_from=2030-01-02&available_to=2030-01-03")
        check("equipment free after cancel", body["count"], 1)
        s, body = call(base, "GET", f"{api}/loans")
        check("loan kept as cancelled", [x["status"] for x in body["items"]], ["cancelled"])
        s = urllib.request.urlopen(base + "/equipment", timeout=5).status
        check("HTML page /equipment -> 200", s, 200)
    elif mode == "read":
        s, body = call(base, "GET", f"{api}/equipment")
        check("equipment survived restart", [e["name"] for e in body["items"]], ["CI projector"])
        s, body = call(base, "GET", f"{api}/loans")
        check("loans survived restart", body["count"], 1)
    else:
        sys.exit("mode must be 'write' or 'read'")
    print("smoke test OK")


if __name__ == "__main__":
    main()
