import json, urllib.request, urllib.error, http.cookiejar, datetime as dt

BASE = "http://localhost:8000/api"
jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))

def req(path, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"Content-Type": "application/json"})
    try:
        with opener.open(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "null")

fails = []
def check(cond, msg):
    print(("PASS" if cond else "FAIL") + ": " + msg)
    if not cond: fails.append(msg)

# 1. login
s, _ = req("/auth/login", "POST", {"username": "admin", "password": "admin123"})
check(s == 200, f"login admin (status {s})")

# 2. pick a cycle with start_date; ensure sprint_count>=2
s, cycles = req("/pi-cycles")
check(s == 200 and cycles, "pi-cycles list non-empty")
cycle = next((c for c in cycles if c.get("start_date")), cycles[0] if cycles else None)
cid = cycle["id"]
ver = cycle["version"]
print(f"   cycle {cid} year={cycle['year']} {cycle['quarter']} start={cycle.get('start_date')} sc={cycle['sprint_count']} v={ver}")
if not cycle.get("start_date") or cycle["sprint_count"] < 2:
    new_start = cycle.get("start_date") or "2026-01-12"
    s, c2 = req(f"/pi-cycles/{cid}", "PATCH",
                {"start_date": new_start, "sprint_count": 6, "expected_version": ver})
    check(s == 200, f"ensure start_date/sprint_count (status {s})")
    cycle = c2; ver = cycle["version"]
start = dt.date.fromisoformat(cycle["start_date"])
sc = cycle["sprint_count"]

# 3. data tab has regressions field; existing pirs intact
s, data = req(f"/pi-cycles/{cid}/data")
check(s == 200, "GET /data ok")
check("regressions" in data, "'regressions' key present in /data")
check(isinstance(data.get("pirs"), list), "'pirs' still a list")
check(all("event_type" in p and "end_date" in p for p in data["pirs"]), "pirs rows carry event_type+end_date")

# 4. create single-day regression + range regression crossing sprint boundary
d1 = (start + dt.timedelta(days=5)).isoformat()          # sprint 0 only
d2s = (start + dt.timedelta(days=10)).isoformat()        # sprint 0
d2e = (start + dt.timedelta(days=20)).isoformat()        # sprint 1 -> overlaps both
name1, name2 = "РЕГР-ОДИН", "РЕГР-ДИАПАЗОН"
s, data = req(f"/pi-cycles/{cid}/regressions", "POST",
              {"name": name1, "date": d1, "expected_version": ver})
check(s == 200, f"create single-day regression (status {s})")
ver = data["cycle"]["version"]
s, data = req(f"/pi-cycles/{cid}/regressions", "POST",
              {"name": name2, "date": d2s, "end_date": d2e, "expected_version": ver})
check(s == 200, f"create range regression crossing sprint boundary (status {s})")
ver = data["cycle"]["version"]

reg_list = data.get("regressions", [])
check(any(r["name"] == name1 for r in reg_list), "single-day regression listed in /data")
check(any(r["name"] == name2 and r.get("end_date") == d2e for r in reg_list), "range regression listed with end_date")
check(all(r["event_type"] == "regression" for r in reg_list), "regressions typed as 'regression'")

# 5. schedule overlap: name2 in sprint 0 AND 1; name1 only in sprint 0
s, data = req(f"/pi-cycles/{cid}/data")
sprints = data["schedule"]["sprints"]
sp0_names = {r["name"] for r in sprints[0].get("regressions", [])}
sp1_names = {r["name"] for r in sprints[1].get("regressions", [])}
check("regressions" in sprints[0], "schedule sprint has 'regressions' key")
check(name1 in sp0_names and name1 not in sp1_names, "single-day regression only in sprint 0")
check(name2 in sp0_names and name2 in sp1_names, "range regression in sprint 0 AND sprint 1 (overlap)")

# 6. Program Board events carry event_type/end_date and overlap
s, pb = req(f"/pi-cycles/{cid}/program-board")
check(s == 200, "GET program-board ok")
ev = [e for sp in pb["sprints"] for e in sp.get("events", [])]
check(all("event_type" in e and "end_date" in e for e in ev), "PB events carry event_type+end_date")
pb_sp0 = {e["name"] for e in pb["sprints"][0].get("events", [])}
pb_sp1 = {e["name"] for e in pb["sprints"][1].get("events", [])}
check(name2 in pb_sp0 and name2 in pb_sp1, "PB: range regression in sprint 0 AND 1")

# 7. uniqueness within type: same name as a PIR is allowed (per-type scope)
pir_name = data["pirs"][0]["name"] if data["pirs"] else None
if pir_name:
    s, _ = req(f"/pi-cycles/{cid}/regressions", "POST",
               {"name": pir_name, "date": d1, "expected_version": ver})
    check(s == 200, f"regression can share name with a PIR (per-type uniqueness, status {s})")
    ver = req(f"/pi-cycles/{cid}/data")[1]["cycle"]["version"]

# 8. cleanup: delete the regressions we created
for r in req(f"/pi-cycles/{cid}/data")[1]["regressions"]:
    if r["name"] in (name1, name2, pir_name):
        s, _ = req(f"/pi-cycles/{cid}/regressions/{r['id']}", "DELETE",
                   {"expected_version": ver})
        if s == 200: ver = req(f"/pi-cycles/{cid}/data")[1]["cycle"]["version"]
check(True, "cleanup of test regressions attempted")

print("\nRESULT:", "ALL PASS" if not fails else f"{len(fails)} FAILURES: {fails}")
