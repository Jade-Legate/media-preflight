from urllib.parse import quote

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from . import config

_cfg = Config(signature_version="s3v4", s3={"addressing_style": "path"})


def _client(endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=config.S3_ACCESS_KEY,
        aws_secret_access_key=config.S3_SECRET_KEY,
        region_name=config.S3_REGION,
        config=_cfg,
    )


s3 = _client(config.S3_ENDPOINT)
# 서명만 하는 클라이언트(네트워크 호출 없음). 브라우저가 볼 수 있는 host로 서명해야 한다.
s3_public = _client(config.S3_PUBLIC_ENDPOINT)


def ensure_bucket():
    try:
        s3.head_bucket(Bucket=config.S3_BUCKET)
    except ClientError:
        s3.create_bucket(Bucket=config.S3_BUCKET)


def create_upload_url(key: str) -> str:
    return s3_public.generate_presigned_url(
        "put_object", Params={"Bucket": config.S3_BUCKET, "Key": key}, ExpiresIn=config.SIGNED_URL_TTL_SECONDS
    )


def create_download_url(key: str, filename: str) -> str:
    return s3_public.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": config.S3_BUCKET,
            "Key": key,
            "ResponseContentDisposition": f"attachment; filename*=UTF-8''{quote(filename, safe='')}",
        },
        ExpiresIn=config.SIGNED_URL_TTL_SECONDS,
    )


def read_size(key: str) -> int | None:
    try:
        return s3.head_object(Bucket=config.S3_BUCKET, Key=key)["ContentLength"]
    except ClientError:
        return None


def download(key: str, path: str):
    s3.download_file(config.S3_BUCKET, key, path)


def upload(path: str, key: str):
    s3.upload_file(path, config.S3_BUCKET, key)


def delete(key: str):
    s3.delete_object(Bucket=config.S3_BUCKET, Key=key)



# ---------------------------------------------------------------- local disk backend
# 단일 서버 배포용. object storage 대신 API가 HMAC 서명된 URL로 파일을 직접 받고 내준다.

import hashlib
import hmac
import os
import shutil
import time


def sign(key: str, method: str, exp: int) -> str:
    msg = f"{method}\n{key}\n{exp}".encode()
    return hmac.new(config.BLOB_SIGNING_KEY.encode(), msg, hashlib.sha256).hexdigest()


def verify(key: str, method: str, exp: int, sig: str) -> bool:
    return exp >= time.time() and hmac.compare_digest(sign(key, method, exp), sig)


def local_path(key: str) -> str:
    # key는 서버가 만든 uploads/{job}/{file}.{ext} 형태만 허용(경로 탈출 방지)
    if ".." in key or key.startswith("/"):
        raise ValueError("invalid key")
    return os.path.join(config.LOCAL_STORAGE_DIR, key)


def _signed_url(key: str, method: str, extra: str = "") -> str:
    exp = int(time.time()) + config.SIGNED_URL_TTL_SECONDS
    return f"{config.PUBLIC_API_URL}/api/v1/blobs/{key}?exp={exp}&sig={sign(key, method, exp)}{extra}"


if config.STORAGE_BACKEND == "local":

    def ensure_bucket():
        os.makedirs(config.LOCAL_STORAGE_DIR, exist_ok=True)

    def create_upload_url(key: str) -> str:
        return _signed_url(key, "PUT")

    def create_download_url(key: str, filename: str) -> str:
        return _signed_url(key, "GET", f"&name={quote(filename, safe='')}")

    def read_size(key: str) -> int | None:
        p = local_path(key)
        return os.path.getsize(p) if os.path.exists(p) else None

    def download(key: str, path: str):
        shutil.copyfile(local_path(key), path)

    def upload(path: str, key: str):
        os.makedirs(os.path.dirname(local_path(key)), exist_ok=True)
        shutil.copyfile(path, local_path(key))

    def delete(key: str):
        try:
            os.remove(local_path(key))
        except FileNotFoundError:
            pass

    def check():
        ensure_bucket()

else:

    def check():
        s3.head_bucket(Bucket=config.S3_BUCKET)
