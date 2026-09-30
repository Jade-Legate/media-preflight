"""업로드 → 진단 → 수정 → 재검증 → 다운로드 전체 흐름. 실제 Postgres/Redis/S3(MinIO) 사용, worker는 동기 실행."""

import os

import httpx
import pytest
from fastapi.testclient import TestClient

from preflight.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def upload(client, paths, names=None, **settings):
    names = names or [os.path.basename(p) for p in paths]
    res = client.post("/api/v1/jobs", json={"files": [{"name": n, "sizeBytes": os.path.getsize(p)} for n, p in zip(names, paths)], **settings})
    assert res.status_code == 201, res.text
    body = res.json()
    for f, p in zip(body["files"], paths):
        with open(p, "rb") as fh:
            assert httpx.put(f["uploadUrl"], content=fh.read()).status_code == 200
        assert client.post(f"/api/v1/jobs/{body['jobId']}/files/complete", json={"fileId": f["fileId"]}).status_code == 200
        assert client.post(f"/api/v1/files/{f['fileId']}/diagnose").status_code == 202
    return body["jobId"], [f["fileId"] for f in body["files"]]


def read_job(client, job_id):
    return client.get(f"/api/v1/jobs/{job_id}").json()


def test_채널_이상_파일은_진단_자동수정_재검증_다운로드까지_완료된다(client, samples):
    # Given 역상 stereo 파일을 업로드하고 진단하면
    job_id, [fid] = upload(client, [samples["phase_inverted.mp4"]])
    f = read_job(client, job_id)["files"][0]
    assert f["status"] == "NOT_READY"
    source = f["diagnostic"]["metrics"]["channelDecision"]["sourceChannel"]

    # When 권장된 FIX-001을 적용하면
    res = client.post(f"/api/v1/files/{fid}/fix", json={"fixId": "FIX-001", "params": {"sourceChannel": source}})
    assert res.status_code == 202

    # Then 수정본이 재검증을 통과해 READY가 되고
    fx = read_job(client, job_id)["files"][0]["fixes"][0]
    assert fx["status"] == "SUCCEEDED", fx
    assert all(c["status"] == "PASS" for c in fx["checks"])
    assert fx["output"]["status"] == "READY"
    # And 수정본을 다운로드할 수 있으며 원본은 보존된다
    url = client.get(f"/api/v1/files/{fx['output']['fileId']}/download").json()["url"]
    assert httpx.get(url).status_code == 200
    assert read_job(client, job_id)["files"][0]["status"] == "NOT_READY"


def test_판단이_애매한_파일에는_채널_자동수정을_거부한다(client, samples):
    job_id, [fid] = upload(client, [samples["weak_right.mp4"]])
    res = client.post(f"/api/v1/files/{fid}/fix", json={"fixId": "FIX-001", "params": {"sourceChannel": 0}})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CHANNEL_UNCERTAIN"


def test_batch_최적화는_한_파일이_실패해도_나머지를_처리한다(client, samples):
    # Given 용량 제한 1MB로 정상 대용량 파일 + 손상 파일을 올리고 (QA-009)
    job_id, fids = upload(client, [samples["large_normal.mp4"], samples["corrupt.mp4"]], maxFileSizeMb=1)
    assert read_job(client, job_id)["summary"]["OPTIMIZATION_REQUIRED"] == 1
    # When 두 파일 모두 MP3 변환을 요청하면
    res = client.post("/api/v1/batch/optimize", json={"jobId": job_id, "fileIds": fids, "fixId": "FIX-002", "params": {"bitrateKbps": 64}})
    assert res.status_code == 202
    # Then 정상 파일은 성공, 손상 파일만 실패한다
    statuses = [f["fixes"][0]["status"] for f in read_job(client, job_id)["files"]]
    assert statuses == ["SUCCEEDED", "FAILED"]


def test_특수문자_파일명과_중복_업로드도_독립적으로_처리된다(client, samples):
    # QA-011, QA-012
    p = samples["normal_stereo.mp4"]
    a, _ = upload(client, [p], names=["../강의 01 (최종)#.mp4"])
    b, _ = upload(client, [p], names=["../강의 01 (최종)#.mp4"])
    ja, jb = read_job(client, a), read_job(client, b)
    assert a != b
    assert ja["files"][0]["name"] == "강의 01 (최종)#.mp4"
    assert ja["files"][0]["status"] == jb["files"][0]["status"] == "READY"


def test_지원하지_않는_파일은_업로드_전에_거부한다(client):
    res = client.post("/api/v1/jobs", json={"files": [{"name": "a.exe", "sizeBytes": 10}, {"name": "b.mp4", "sizeBytes": 0}]})
    assert res.status_code == 422
    assert [f["code"] for f in res.json()["error"]["details"]["files"]] == ["UNSUPPORTED_FORMAT", "EMPTY_FILE"]


def test_KPI와_health를_조회할_수_있다(client):
    kpi = client.get("/api/v1/kpi").json()
    assert kpi["diagnosedFiles"] >= 1
    assert kpi["verificationPassRate"] is not None
    assert client.get("/api/v1/health").json()["db"] == "ok"


def test_worker_HTTP_엔드포인트로도_작업을_실행할_수_있다(client, samples):
    # Given 진단 대기 중인 파일 (Cloud Run에서는 Cloud Tasks가 이 엔드포인트를 호출한다)
    from preflight.db import Diagnostic, Session, new_id
    from preflight.worker import app as worker_app

    job_id, [fid] = upload(client, [samples["mono.mp4"]])
    with Session() as s:
        d = Diagnostic(id=new_id("d"), file_id=fid)
        s.add(d)
        s.commit()
    # When worker HTTP로 진단을 실행하면
    with TestClient(worker_app) as w:
        assert w.post("/tasks/diagnose", json={"id": d.id}).json() == {"ok": True}
    # Then 결과가 저장된다
    assert client.get(f"/api/v1/diagnostics/{d.id}").json()["overallStatus"] == "READY"


def test_여러_영상의_채널_이상을_한_번에_수정하고_ZIP으로_받는다(client, samples):
    import io
    import zipfile

    # Given 채널 이상 2개(역상, 한쪽 무음) + 판단이 애매한 1개를 한 번에 올리고
    job_id, fids = upload(client, [samples["phase_inverted.mp4"], samples["dead_right.mp4"], samples["weak_right.mp4"]])
    # When 일괄 채널 교정을 요청하면
    res = client.post("/api/v1/batch/fix", json={"jobId": job_id, "fileIds": fids, "fixId": "FIX-001"}).json()
    # Then 근거가 명확한 2개만 수정하고, 애매한 파일은 건너뛴다
    assert len(res["queued"]) == 2
    assert [x["fileId"] for x in res["skipped"]] == [fids[2]]
    outputs = [f["fixes"][0]["output"]["status"] for f in read_job(client, job_id)["files"][:2]]
    assert outputs == ["READY", "READY"]
    # And 수정된 파일의 최종 상태는 READY로 집계된다
    job = read_job(client, job_id)
    assert [f["effectiveStatus"] for f in job["files"]] == ["READY", "READY", "REVIEW_REQUIRED"]
    assert job["summary"]["READY"] == 2
    # And 선택한 3개를 ZIP 하나로 받으면 수정된 파일은 수정본, 나머지는 원본이 담긴다
    z = client.get(f"/api/v1/jobs/{job_id}/download.zip", params={"files": ",".join(fids)})
    assert z.status_code == 200
    assert sorted(zipfile.ZipFile(io.BytesIO(z.content)).namelist()) == [
        "dead_right_fix-001.mp4", "phase_inverted_fix-001.mp4", "weak_right.mp4"]
    # And 내 처리 기록에서 요청 단위로 요약이 보인다
    [summary] = client.get("/api/v1/jobs", params={"ids": job_id}).json()
    assert summary["fileCount"] == 3 and summary["fixedCount"] == 2
