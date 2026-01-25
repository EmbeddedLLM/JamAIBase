#!/usr/bin/env python3
import argparse
import asyncio
import os
import sys
from os.path import splitext
from urllib.parse import urlparse

import httpx

from owl.configs import ENV_CONFIG
from owl.utils.io import (
    AUDIO_WHITE_LIST_EXT,
    NON_PDF_DOC_WHITE_LIST_EXT,
    generate_presigned_s3_url,
    get_global_thumbnail_path,
    get_s3_aclient,
)

try:
    from botocore.exceptions import ClientError
except Exception:
    ClientError = Exception


def parse_s3_uri(uri: str) -> tuple[str, str]:
    uri = uri.strip()
    if not uri.startswith("s3://"):
        raise ValueError(f"Not an s3 uri: {uri!r}")
    bucket, key = uri[5:].split("/", 1)
    return bucket, key


def compute_thumb_key(uri: str) -> tuple[str, str, str]:
    ext = splitext(uri)[1].lower()
    bucket, key = parse_s3_uri(uri)
    thumb_ext = "mp3" if ext in AUDIO_WHITE_LIST_EXT else "webp"

    if ext in NON_PDF_DOC_WHITE_LIST_EXT:
        thumb_key = os.path.join(
            key[: key.index("raw/")],
            get_global_thumbnail_path(ext),
        )
    else:
        thumb_key = key.replace("raw", "thumb")
        thumb_key = f"{os.path.splitext(thumb_key)[0]}.{thumb_ext}"

    return bucket, key, thumb_key


def describe_addressing(url: str) -> str:
    """
    Quick human-readable hint whether URL is virtual-hosted or path-style.
    """
    p = urlparse(url)
    host = p.netloc
    path = p.path.lstrip("/")

    # Heuristic only
    if host.startswith("s3.") or host == "s3.amazonaws.com":
        return f"path-style-ish (bucket likely in path: {path.split('/')[0] if path else ''})"
    if ".s3" in host:
        return "virtual-hosted style (bucket in hostname)"
    return "unknown style (custom endpoint?)"


async def http_check(url: str, *, verify: bool = True) -> None:
    timeout = httpx.Timeout(60.0, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=verify) as client:
        print(f"\n[HTTP] HEAD {url}")
        r = await client.head(url)
        print(f"[HTTP] status={r.status_code}")
        for h in (
            "content-type",
            "content-length",
            "etag",
            "last-modified",
            "accept-ranges",
            "content-range",
        ):
            if h in r.headers:
                print(f"[HTTP] {h}: {r.headers[h]}")

        if r.status_code >= 400:
            print(r.text)
            print("\n[HTTP] GET (Range: bytes=0-255)")
            g = await client.get(url, headers={"Range": "bytes=0-255"})
            print(f"[HTTP] status={g.status_code}")
            for h in (
                "content-type",
                "content-length",
                "etag",
                "last-modified",
                "accept-ranges",
                "content-range",
            ):
                if h in g.headers:
                    print(f"[HTTP] {h}: {g.headers[h]}")
            print(f"[HTTP] first_bytes_len={len(g.content)}")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("uri", help="s3://bucket/key")
    ap.add_argument("--mode", choices=["raw", "thumb"], default="raw")
    ap.add_argument(
        "--check",
        choices=["none", "s3", "proxy", "both"],
        default="s3",
        help="Which URL to validate over HTTP",
    )
    ap.add_argument(
        "--insecure",
        action="store_true",
        help="Disable TLS verification (useful for self-signed localhost)",
    )
    args = ap.parse_args()

    print("=== ENV / CONFIG ===")
    for k in (
        "AWS_REGION",
        "AWS_DEFAULT_REGION",
        "AWS_PROFILE",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
    ):
        if k in os.environ:
            v = os.environ[k]
            if "SECRET" in k or k.endswith("TOKEN"):
                v = v[:4] + "..." if v else v
            print(f"{k}={v}")

    print("\n=== ENV_CONFIG ===")
    for attr in ("s3_endpoint", "file_proxy_url", "s3_region", "aws_region"):
        if hasattr(ENV_CONFIG, attr):
            print(f"ENV_CONFIG.{attr} = {getattr(ENV_CONFIG, attr)}")

    print("\n=== INPUT ===")
    bucket, key = parse_s3_uri(args.uri)
    print(f"bucket={bucket}")
    print(f"key={key}")

    target_key = key
    if args.mode == "thumb":
        ext = splitext(args.uri)[1].lower()
        print(f"ext={ext}")
        _, _, target_key = compute_thumb_key(args.uri)
        print(f"computed thumb_key={target_key}")

    async with get_s3_aclient() as s3:
        # Client endpoint/region introspection
        try:
            endpoint = getattr(s3, "_endpoint", None)
            if endpoint is not None:
                print(f"\nclient endpoint host = {endpoint.host}")
            meta = getattr(s3, "meta", None)
            if meta is not None:
                print(f"client meta.region_name = {meta.region_name}")
        except Exception as e:
            print(f"(could not introspect client endpoint/region: {e})")

        # Bucket location
        print("\n[S3] get_bucket_location ...")
        loc = await s3.get_bucket_location(Bucket=bucket)
        bucket_region = loc.get("LocationConstraint") or "us-east-1"
        print(f"[S3] LocationConstraint={loc.get('LocationConstraint')!r} -> {bucket_region}")

        # Existence check
        print(f"\n[S3] head_object Bucket={bucket} Key={target_key} ...")
        try:
            h = await s3.head_object(Bucket=bucket, Key=target_key)
            print("[S3] head_object OK")
            print(f"  ContentType={h.get('ContentType')}")
            print(f"  ContentLength={h.get('ContentLength')}")
        except ClientError as e:
            print(f"[S3] head_object FAILED: {e}")
            sys.exit(2)

        # 1) RAW S3 presign (definitive)
        print("\n=== PRESIGN (RAW S3) ===")
        s3_url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": target_key},
            ExpiresIn=3600,
        )
        print(s3_url)
        print(f"addressing: {describe_addressing(s3_url)}")

        # 2) Your app helper (rewritten to proxy)
        print("\n=== PRESIGN (APP HELPER / PROXY REWRITE) ===")
        proxy_url = await generate_presigned_s3_url(s3, bucket, target_key)
        print(proxy_url)

    # HTTP validate
    verify = not args.insecure
    if args.check in ("s3", "both"):
        await http_check(s3_url, verify=verify)
    if args.check in ("proxy", "both"):
        await http_check(proxy_url, verify=verify)

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(main())
