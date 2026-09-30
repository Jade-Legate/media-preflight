"""배포된 API 스모크 테스트: 업로드 → 진단 → 자동수정 → 재검증 → 다운로드.

uv run --with httpx python infra/smoke.py https://<api> samples/phase_inverted.mp4
"""

import os
import sys
import time

import httpx

api, path = sys.argv[1].rstrip("/"), sys.argv[2]
c = httpx.Client(base_url=api, timeout=120)


def wait(pred, what, limit=300):
    t0 = time.time()
    while time.time() - t0 < limit:
        job = c.get(f"/api/v1/jobs/{job_id}").json()
        if pred(job["files"][0]):
            return job["files"][0]
        time.sleep(2)
    sys.exit(f"timeout: {what}")


print("health", c.get("/api/v1/health").json())
r = c.post("/api/v1/jobs", json={"files": [{"name": os.path.basename(path), "sizeBytes": os.path.getsize(path)}]}).json()
job_id, f = r["jobId"], r["files"][0]
with open(path, "rb") as fh:
    assert httpx.put(f["uploadUrl"], content=fh.read(), timeout=120).status_code == 200
c.post(f"/api/v1/jobs/{job_id}/files/complete", json={"fileId": f["fileId"]}).raise_for_status()
c.post(f"/api/v1/files/{f['fileId']}/diagnose").raise_for_status()
file = wait(lambda x: x["diagnostic"] and x["diagnostic"]["status"] in ("DONE", "FAILED"), "diagnose")
d = file["diagnostic"]
print("diagnosis", d["overallStatus"], [r["ruleId"] for r in d["results"] if r["status"] in ("WARN", "FAIL")])
decision = d["metrics"]["channelDecision"]
if decision["state"] == "ONE_SIDED":
    c.post(f"/api/v1/files/{f['fileId']}/fix", json={"fixId": "FIX-001", "params": {"sourceChannel": decision["sourceChannel"]}}).raise_for_status()
    file = wait(lambda x: x["fixes"] and x["fixes"][0]["status"] not in ("QUEUED", "RUNNING"), "fix")
    fx = file["fixes"][0]
    print("fix", fx["status"], "→ output", fx["output"]["status"], [c_["ruleId"] + ":" + c_["status"] for c_ in fx["checks"]])
    url = c.get(f"/api/v1/files/{fx['output']['fileId']}/download").json()["url"]
    r = httpx.get(url, timeout=120)
    print("download", r.status_code, len(r.content), "bytes")
print("job", f"{job_id}")
