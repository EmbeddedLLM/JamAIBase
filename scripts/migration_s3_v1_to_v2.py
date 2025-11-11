import concurrent.futures
import math
import os
import sys
import time

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from dotenv import load_dotenv
from loguru import logger


def logger_config(max_workers: int = 10):
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    logger.add(
        f"s3_migration_{max_workers}.log",
        level="INFO",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation="5 MB",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )
    logger.info("Logger configured. Starting S3 migration script...")


def get_s3_client(endpoint, access_key, secret_key):
    try:
        client = boto3.client(
            "s3",
            endpoint_url=f"http://{endpoint}",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
        )
        client.list_buckets()
        logger.info(f"Successfully connected to MinIO at {endpoint}")
        return client
    except (NoCredentialsError, ClientError) as e:
        logger.error(f"Failed to connect to MinIO at {endpoint}. Error: {e}")
        return None


def get_all_organization_ids(s3_client, bucket_name: str) -> list[str]:
    org_ids = set()
    prefix_to_scan = "raw/"
    logger.info(f"Discovering all organization IDs in s3://{bucket_name}/{prefix_to_scan}...")
    try:
        paginator = s3_client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix_to_scan, Delimiter="/")
        for page in pages:
            if "CommonPrefixes" in page:
                for common_prefix in page["CommonPrefixes"]:
                    parts = common_prefix.get("Prefix", "").strip("/").split("/")
                    if len(parts) > 1:
                        org_ids.add(parts[1])
    except ClientError as e:
        logger.error(f"Failed to scan for organization IDs in s3://{bucket_name}/. Error: {e}")
        return []
    found_ids = list(org_ids)
    if found_ids:
        logger.info(f"Found {len(found_ids)} organization IDs: {found_ids}")
    else:
        logger.warning(f"No organization IDs found under the '{prefix_to_scan}' prefix.")
    return found_ids


def format_bytes(size_bytes: int) -> str:
    """Converts a size in bytes to a human-readable format (KB, MB, GB, etc.)."""
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"


def get_organization_storage_size(
    s3_client, bucket_name: str, organization_id: str, log_summary: bool = True
) -> tuple[int, int]:
    """
    Calculates the total number of files and storage size for a specific organization.
    The `log_summary` parameter controls if the function prints its own summary.
    """
    if log_summary:
        logger.info(
            f"Calculating storage size for organization '{organization_id}' in bucket '{bucket_name}'..."
        )

    total_bytes, total_files = 0, 0
    prefixes_to_scan = [f"raw/{organization_id}/", f"thumb/{organization_id}/"]

    try:
        for prefix in prefixes_to_scan:
            paginator = s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                for obj in page.get("Contents", []):
                    total_bytes += obj["Size"]
                    total_files += 1

        if log_summary:
            readable_size = format_bytes(total_bytes)
            logger.info("=" * 40)
            logger.info(f"Storage Summary for Organization: '{organization_id}'")
            logger.info(f"  Total Files: {total_files:,}")
            logger.info(f"  Total Size: {readable_size} ({total_bytes:,} bytes)")
            logger.info("=" * 40)

        return total_bytes, total_files
    except ClientError as e:
        logger.error(f"Could not calculate storage for org '{organization_id}'. Error: {e}")
        return 0, 0


def analyze_all_organizations_storage(s3_client, bucket_name: str):
    """
    Analyzes storage for all organizations, then logs a sorted report.
    """
    logger.info(f"Starting storage analysis for all organizations in bucket '{bucket_name}'...")

    organization_ids = get_all_organization_ids(s3_client, bucket_name)
    if not organization_ids:
        logger.warning("No organizations found to analyze.")
        return

    storage_data = []
    grand_total_bytes = 0
    grand_total_files = 0

    analysis_start_time = time.time()
    for org_id in organization_ids:
        # Call with log_summary=False to prevent noisy individual logs
        total_bytes, total_files = get_organization_storage_size(
            s3_client, bucket_name, org_id, log_summary=False
        )
        if total_files > 0:
            storage_data.append(
                {
                    "org_id": org_id,
                    "total_bytes": total_bytes,
                    "total_files": total_files,
                }
            )
            grand_total_bytes += total_bytes
            grand_total_files += total_files

    # Sort the collected data by size, from lowest to highest
    sorted_storage_data = sorted(storage_data, key=lambda x: x["total_bytes"])

    analysis_end_time = time.time()
    logger.info(
        f"Completed storage analysis in {analysis_end_time - analysis_start_time:.2f} seconds."
    )

    # --- Log the formatted report ---
    logger.info("=" * 70)
    logger.info("Storage Size Report by Organization (Sorted Lowest to Highest)")
    logger.info("-" * 70)
    logger.info(f"{'Organization ID':<40} | {'Total Files':>12} | {'Total Size':>12}")
    logger.info("-" * 70)

    for data in sorted_storage_data:
        readable_size = format_bytes(data["total_bytes"])
        # Use f-string alignment and formatting for a clean table
        logger.info(f"{data['org_id']:<40} | {data['total_files']:>12,} | {readable_size:>12}")

    logger.info("-" * 70)
    readable_grand_total = format_bytes(grand_total_bytes)
    logger.info(f"{'GRAND TOTAL':<40} | {grand_total_files:>12,} | {readable_grand_total:>12}")
    logger.info("=" * 70)


def _copy_single_object(
    source_s3_client, dest_s3_client, source_bucket, source_key, dest_bucket, dest_key
):
    """
    Worker function executed by each thread. Handles one object.
    Returns a status string: "COPIED", "SKIPPED", "FAILED".
    """
    source_loc = f"s3://{source_bucket}/{source_key}"
    dest_loc = f"s3://{dest_bucket}/{dest_key}"
    try:
        # 1. Check if the object already exists at the destination
        dest_s3_client.head_object(Bucket=dest_bucket, Key=dest_key)
        logger.info(f"[SKIP-EXISTING] Destination object already exists: {dest_loc}")
        return "SKIPPED"
    except ClientError as e:
        if e.response["Error"]["Code"] != "404":
            logger.error(f"[FAIL] Failed to check destination {dest_loc}: {e}")
            return "FAILED"

    # 2. If it doesn't exist, copy it
    try:
        response = source_s3_client.get_object(Bucket=source_bucket, Key=source_key)
        dest_s3_client.put_object(
            Bucket=dest_bucket,
            Key=dest_key,
            Body=response["Body"].read(),
            ContentType=response.get("ContentType", "application/octet-stream"),
        )
        logger.info(f"[COPIED] {source_loc} -> {dest_loc}")
        return "COPIED"
    except ClientError as e:
        logger.error(f"[FAIL] Failed during copy for {source_loc}: {e}")
        return "FAILED"


def migrate_s3_structure_across_endpoints(
    source_s3_client,
    dest_s3_client,
    old_organization_id: str,
    source_bucket: str,
    dest_bucket: str,
    new_organization_id: str = None,
    max_workers: int = 10,
    dry_run: bool = True,
):
    """
    Migrates a SINGLE organization's files in parallel, skipping existing files.
    """
    if new_organization_id is None:
        new_organization_id = old_organization_id

    if dry_run:
        logger.info(f"DRY RUN for org '{old_organization_id}'. No changes will be made.")
        # Perform a simple listing for the dry run plan
        total_planned = 0
        for prefix in [f"raw/{old_organization_id}/", f"thumb/{old_organization_id}/"]:
            paginator = source_s3_client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=source_bucket, Prefix=prefix):
                for obj in page.get("Contents", []):
                    logger.info(f"[PLAN-COPY] s3://{source_bucket}/{obj['Key']}")
                    total_planned += 1
        logger.info(
            f"Dry run summary for org '{old_organization_id}': Planned to copy {total_planned} objects."
        )
        return total_planned, 0, 0

    total_copied, total_skipped, total_failed = 0, 0, 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for prefix in [f"raw/{old_organization_id}/", f"thumb/{old_organization_id}/"]:
            try:
                paginator = source_s3_client.get_paginator("list_objects_v2")
                for page in paginator.paginate(Bucket=source_bucket, Prefix=prefix):
                    for obj in page.get("Contents", []):
                        source_key = obj["Key"]
                        dest_key = source_key.replace(
                            f"/{old_organization_id}/", f"/{new_organization_id}/", 1
                        )

                        future = executor.submit(
                            _copy_single_object,
                            source_s3_client,
                            dest_s3_client,
                            source_bucket,
                            source_key,
                            dest_bucket,
                            dest_key,
                        )
                        futures[future] = source_key
            except ClientError as e:
                logger.error(
                    f"Could not list objects in s3://{source_bucket}/{prefix}. Error: {e}"
                )
                total_failed += 1  # Count listing itself as a failure

        for future in concurrent.futures.as_completed(futures):
            status = future.result()
            if status == "COPIED":
                total_copied += 1
            elif status == "SKIPPED":
                total_skipped += 1
            else:
                total_failed += 1

    logger.info(
        f"Summary for org '{old_organization_id}' (Workers: {max_workers}): "
        f"Copied={total_copied}, Skipped={total_skipped}, Failed={total_failed}"
    )
    return total_copied, total_skipped, total_failed


def migrate_all_organizations(
    source_s3_client,
    dest_s3_client,
    source_bucket: str,
    dest_bucket: str = None,
    max_workers: int = 10,
    dry_run: bool = True,
):
    """
    Discovers all organization IDs and migrates their files in parallel, logging time per org.
    """
    if dest_bucket is None:
        dest_bucket = source_bucket
    if not dry_run:
        try:
            dest_s3_client.create_bucket(Bucket=dest_bucket)
            logger.info(f"Ensured destination bucket '{dest_bucket}' exists.")
        except ClientError as e:
            if e.response["Error"]["Code"] not in [
                "BucketAlreadyOwnedByYou",
                "BucketAlreadyExists",
            ]:
                logger.error(
                    f"Could not create/verify destination bucket '{dest_bucket}'. Aborting. Error: {e}"
                )
                return

    organization_ids = get_all_organization_ids(source_s3_client, source_bucket)
    if not organization_ids:
        logger.warning("No organizations found to migrate. Exiting.")
        return

    grand_total_copied, grand_total_skipped, grand_total_failed = 0, 0, 0
    for i, org_id in enumerate(organization_ids):
        logger.info("-" * 50)
        logger.info(
            f"Starting migration for Organization {i + 1}/{len(organization_ids)}: '{org_id}'"
        )

        org_start_time = time.time()

        copied, skipped, failed = migrate_s3_structure_across_endpoints(
            source_s3_client=source_s3_client,
            dest_s3_client=dest_s3_client,
            source_bucket=source_bucket,
            dest_bucket=dest_bucket,
            old_organization_id=org_id,
            new_organization_id="0" if org_id == "org_82d01c923f25d5939b9d4188" else org_id,
            max_workers=max_workers,
            dry_run=dry_run,
        )

        org_end_time = time.time()
        org_time_taken_sec = org_end_time - org_start_time
        org_time_taken_min = org_time_taken_sec / 60
        logger.warning(
            f"\n'{org_id}' migration completed in {org_time_taken_sec:.3f} seconds ({org_time_taken_min:.3f} minutes)."
        )

        grand_total_copied += copied
        grand_total_skipped += skipped
        grand_total_failed += failed

    logger.info("=" * 50)
    logger.info("BULK MIGRATION COMPLETE")
    logger.info(f"Total organizations processed: {len(organization_ids)}")
    logger.info(f"Grand total objects copied: {grand_total_copied}")
    logger.info(f"Grand total objects skipped (already exist): {grand_total_skipped}")
    logger.info(f"Grand total failures: {grand_total_failed}")
    if dry_run:
        logger.warning("This was a DRY RUN. No actual data was moved.")
    logger.info("=" * 50)


def setup_dummy_v1_data(s3_client, bucket_name, org_id, project_id, uuid):
    try:
        s3_client.create_bucket(Bucket=bucket_name)
    except ClientError as e:
        if e.response["Error"]["Code"] not in ["BucketAlreadyOwnedByYou", "BucketAlreadyExists"]:
            raise
    raw_key = f"raw/{org_id}/{project_id}/{uuid}/report.pdf"
    s3_client.put_object(
        Bucket=bucket_name, Key=raw_key, Body=b"pdf content", ContentType="application/pdf"
    )
    thumb_key = f"thumb/{org_id}/{project_id}/{uuid}/report.webp"
    s3_client.put_object(
        Bucket=bucket_name, Key=thumb_key, Body=b"thumbnail", ContentType="image/webp"
    )
    logger.info(f"  Created dummy data for org '{org_id}' in bucket '{bucket_name}'")


if __name__ == "__main__":
    script_start_time = time.time()
    load_dotenv()

    MAX_WORKERS = int(os.getenv("MIGRATION_MAX_WORKERS", 12))
    logger_config(MAX_WORKERS)

    SOURCE_MINIO_ENDPOINT = os.getenv("SOURCE_MINIO_ENDPOINT", "localhost:9000")
    SOURCE_MINIO_ACCESS_KEY = os.getenv("OWL_S3_ACCESS_KEY_ID")
    SOURCE_MINIO_SECRET_KEY = os.getenv("OWL_S3_SECRET_ACCESS_KEY")
    SOURCE_BUCKET_NAME = os.getenv("SOURCE_BUCKET_NAME", "v1-company-bucket")

    DEST_MINIO_ENDPOINT = os.getenv("DEST_MINIO_ENDPOINT", "localhost:9000")
    DEST_MINIO_ACCESS_KEY = os.getenv("OWL_S3_ACCESS_KEY_ID")
    DEST_MINIO_SECRET_KEY = os.getenv("OWL_S3_SECRET_ACCESS_KEY")
    DEST_BUCKET_NAME = os.getenv("DEST_BUCKET_NAME", "v2-migrated-data")

    logger.info(f"Source Endpoint: {SOURCE_MINIO_ENDPOINT}, Source Bucket: {SOURCE_BUCKET_NAME}")
    logger.info(
        f"Destination Endpoint: {DEST_MINIO_ENDPOINT}, Destination Bucket: {DEST_BUCKET_NAME}"
    )
    logger.info(f"Using a maximum of {MAX_WORKERS} parallel workers.")

    s3_source = get_s3_client(
        SOURCE_MINIO_ENDPOINT, SOURCE_MINIO_ACCESS_KEY, SOURCE_MINIO_SECRET_KEY
    )
    s3_dest = get_s3_client(DEST_MINIO_ENDPOINT, DEST_MINIO_ACCESS_KEY, DEST_MINIO_SECRET_KEY)

    if not s3_source or not s3_dest:
        logger.error("Could not establish connection to MinIO. Exiting.")
        sys.exit(1)

    # # --- Setup Dummy Data for Testing ---
    # logger.info("\n--- Setting up test data ---")
    # setup_dummy_v1_data(
    #     s3_source, SOURCE_BUCKET_NAME, "org-acme-corp", "proj-q1-reports", "uuid-acme-1"
    # )
    # setup_dummy_v1_data(
    #     s3_source, SOURCE_BUCKET_NAME, "org-acme-corp", "proj-q1-reports", "uuid-acme-2"
    # )
    # setup_dummy_v1_data(
    #     s3_source, SOURCE_BUCKET_NAME, "org-globex-inc", "proj-doomsday", "uuid-globex-1"
    # )
    # setup_dummy_v1_data(
    #     s3_source, SOURCE_BUCKET_NAME, "org-stark-industries", "proj-arc-reactor", "uuid-stark-1"
    # )

    logger.info("\n--- Starting ALL-ORG Migration (Dry Run) ---")
    migrate_all_organizations(
        source_s3_client=s3_source,
        dest_s3_client=s3_dest,
        source_bucket=SOURCE_BUCKET_NAME,
        dest_bucket=DEST_BUCKET_NAME,
        max_workers=MAX_WORKERS,
        dry_run=True,
    )

    logger.info("\n--- Starting ALL-ORG Migration (Actual Run) ---")
    # This run will copy some files and skip the one that was pre-seeded.
    migrate_all_organizations(
        source_s3_client=s3_source,
        dest_s3_client=s3_dest,
        source_bucket=SOURCE_BUCKET_NAME,
        dest_bucket=DEST_BUCKET_NAME,
        max_workers=MAX_WORKERS,
        dry_run=False,
    )

    logger.info("\n--- Re-running Migration to demonstrate idempotency ---")
    # This second run should skip all files, as they were all copied in the previous step.
    migrate_all_organizations(
        source_s3_client=s3_source,
        dest_s3_client=s3_dest,
        source_bucket=SOURCE_BUCKET_NAME,
        dest_bucket=DEST_BUCKET_NAME,
        max_workers=MAX_WORKERS,
        dry_run=False,
    )

    script_end_time = time.time()
    time_taken_min = (script_end_time - script_start_time) / 60
    time_taken_hrs = time_taken_min / 60
    logger.warning(
        f"\nScript completed in {time_taken_min:.3f} minutes ({time_taken_hrs:.3f} hours)."
    )

    # source_org_size = get_organization_storage_size(
    #     s3_client=s3_source,
    #     bucket_name=SOURCE_BUCKET_NAME,
    #     organization_id="org_82d01c923f25d5939b9d4188",
    # )
    # dest_org_size = get_organization_storage_size(
    #     s3_client=s3_dest, bucket_name=DEST_BUCKET_NAME, organization_id="0"
    # )
    # assert (
    #     source_org_size[0] == dest_org_size[0]
    # ), f"Source size {source_org_size[0]} does not match destination size {dest_org_size[0]}"
    # assert (
    #     source_org_size[1] == dest_org_size[1]
    # ), f"Source files {source_org_size[1]} do not match destination files {dest_org_size[1]}"

    # logger.info("\n--- Generating Storage Analysis Report for All Organizations ---")
    # analyze_all_organizations_storage(s3_client=s3_source, bucket_name=SOURCE_BUCKET_NAME)

    logger.info("\n--- Generating Storage Analysis Report for All Organizations ---")
    analyze_all_organizations_storage(s3_client=s3_dest, bucket_name=DEST_BUCKET_NAME)
