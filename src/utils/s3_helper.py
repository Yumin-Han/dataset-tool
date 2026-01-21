"""S3/MinIO 연동 헬퍼"""

import os
from typing import List, Optional

try:
    import boto3
    from botocore.client import Config
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False


# MinIO/S3 Configuration
DEFAULT_MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://mlops-showroom-minio:9000").strip()
DEFAULT_BUCKET = os.environ.get("MINIO_BUCKET", "seamless").strip()
DEFAULT_PREFIX = os.environ.get("MINIO_DST_PREFIX", "detection/v1.0/").strip()


def build_s3_client():
    """S3/MinIO 클라이언트를 생성합니다.
    
    환경 변수:
        MINIO_ENDPOINT: MinIO 엔드포인트 URL
        MINIO_ACCESS_KEY: 액세스 키
        MINIO_SECRET_KEY: 시크릿 키
    
    Returns:
        boto3 S3 client 또는 None (boto3 미설치 시)
    """
    if not BOTO3_AVAILABLE:
        print("경고: boto3가 설치되지 않았습니다. S3 기능을 사용할 수 없습니다.")
        print("설치: uv add boto3")
        return None
    
    endpoint_url = DEFAULT_MINIO_ENDPOINT
    access_key = os.environ.get("MINIO_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("MINIO_SECRET_KEY", "").strip()
    
    if not access_key or not secret_key:
        print("경고: MINIO_ACCESS_KEY 또는 MINIO_SECRET_KEY가 설정되지 않았습니다.")
        return None
    
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        region_name="us-east-1",
    )


def s3_list_scenes(s3, bucket: str, prefix_root: str) -> List[str]:
    """S3에서 씬 목록을 조회합니다.
    
    Args:
        s3: boto3 S3 client
        bucket: 버킷 이름
        prefix_root: 루트 프리픽스
    
    Returns:
        씬 이름 리스트
    """
    scenes = []
    prefix = prefix_root
    if prefix and not prefix.endswith("/"):
        prefix += "/"

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            p = cp.get("Prefix")
            name = p[len(prefix):].strip("/")
            if name:
                scenes.append(name)
    return sorted(scenes)


def s3_exists(s3, bucket: str, key: str) -> bool:
    """S3 객체 존재 여부를 확인합니다.
    
    Args:
        s3: boto3 S3 client
        bucket: 버킷 이름
        key: 객체 키
    
    Returns:
        존재 여부
    """
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


def s3_download_dir(s3, bucket: str, s3_prefix: str, local_dir: str) -> None:
    """S3 디렉토리를 로컬로 다운로드합니다.
    
    Args:
        s3: boto3 S3 client
        bucket: 버킷 이름
        s3_prefix: S3 프리픽스
        local_dir: 로컬 대상 디렉토리
    """
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=s3_prefix):
        if "Contents" not in page:
            continue
        for obj in page["Contents"]:
            key = obj["Key"]
            if key.endswith("/") or not key.startswith(s3_prefix):
                continue
            rel_path = key[len(s3_prefix):].lstrip("/")
            local_path = os.path.join(local_dir, rel_path)
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            print(f"다운로드: s3://{bucket}/{key} -> {local_path}")
            s3.download_file(bucket, key, local_path)


def s3_upload_dir(s3, local_dir: str, bucket: str, s3_prefix: str) -> None:
    """로컬 디렉토리를 S3로 업로드합니다.
    
    Args:
        s3: boto3 S3 client
        local_dir: 로컬 소스 디렉토리
        bucket: 버킷 이름
        s3_prefix: S3 프리픽스
    """
    for root, dirs, files in os.walk(local_dir):
        for file in files:
            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, local_dir)
            s3_key = os.path.join(s3_prefix, rel_path).replace("\\", "/")
            print(f"업로드: {local_path} -> s3://{bucket}/{s3_key}")
            s3.upload_file(local_path, bucket, s3_key)


def parse_s3_uri(s3_uri: str) -> Optional[tuple]:
    """S3 URI를 파싱합니다.
    
    Args:
        s3_uri: s3://bucket/prefix/path 형식
    
    Returns:
        (bucket, prefix) 튜플 또는 None
    """
    if not s3_uri.startswith("s3://"):
        return None
    
    path = s3_uri[5:]  # "s3://" 제거
    parts = path.split("/", 1)
    bucket = parts[0]
    prefix = parts[1] if len(parts) > 1 else ""
    
    return bucket, prefix
