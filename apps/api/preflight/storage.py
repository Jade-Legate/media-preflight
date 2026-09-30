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

