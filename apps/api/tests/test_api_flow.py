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
