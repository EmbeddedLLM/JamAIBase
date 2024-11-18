# tasks.py
import os
import pathlib
import tempfile
from datetime import datetime, timedelta, timezone

import boto3
from botocore.client import Config
from celery import Celery, chord
from loguru import logger

from owl.configs.manager import ENV_CONFIG
from owl.db.gen_table import GenerativeTable
from owl.protocol import TableType

# Set up Celery
app = Celery("tasks", broker=f"redis://{ENV_CONFIG.owl_redis_host}:{ENV_CONFIG.owl_redis_port}/0")

# Configure Celery
app.conf.update(
    result_backend=f"redis://{ENV_CONFIG.owl_redis_host}:{ENV_CONFIG.owl_redis_port}/0",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)


def get_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d-%H")


def _get_s3_client():
    _session = boto3.session.Session()
    return _session.client(
        "s3",
        endpoint_url=ENV_CONFIG.s3_endpoint,
        aws_access_key_id=ENV_CONFIG.s3_access_key_id,
        aws_secret_access_key=ENV_CONFIG.s3_secret_access_key_plain,
        config=Config(signature_version="s3v4"),
    )


@app.task
def s3_cleanup():
    s3_client = _get_s3_client()
    current_date = datetime.utcnow().date()
    retention_period = timedelta(days=7)
    try:
        datetime_list = []
        continuation_token = None

        while True:
            params = {
                "Bucket": ENV_CONFIG.s3_backup_bucket_name,
                "MaxKeys": 1000,
                "Delimiter": "/",
            }
            if continuation_token:
                params["ContinuationToken"] = continuation_token

            response = s3_client.list_objects_v2(**params)
            if "CommonPrefixes" in response:
                for prefix in response["CommonPrefixes"]:
                    date_hour = prefix["Prefix"].rstrip("/")
                    if date_hour != "main-db":
                        backup_date = datetime.strptime(date_hour, "%Y-%m-%d-%H").date()
                        if current_date - backup_date > retention_period:
                            datetime_list.append(date_hour)

            if not response.get("IsTruncated"):
                break

            continuation_token = response.get("NextContinuationToken")

        date_objects = [datetime.strptime(date_str, "%Y-%m-%d-%H") for date_str in datetime_list]

        # Find the latest hour for each day
        latest_by_day = {}
        for date_obj in date_objects:
            date_key = date_obj.date()
            if date_key not in latest_by_day or date_obj > latest_by_day[date_key]:
                latest_by_day[date_key] = date_obj

        # Create a list of all entries except the latest for each day
        datetime_list = [
            date_obj.strftime("%Y-%m-%d-%H")
            for date_obj in date_objects
            if date_obj != latest_by_day[date_obj.date()]
        ]

        for time in datetime_list:
            paginator = s3_client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=ENV_CONFIG.s3_backup_bucket_name, Prefix=time
            )

            for page in page_iterator:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        s3_client.delete_object(
                            Bucket=ENV_CONFIG.s3_backup_bucket_name, Key=obj["Key"]
                        )
            logger.info(f"S3 Cleanup done for {time}!")

    except Exception as e:
        logger.error(f"S3 Cleanup failed:\n {e}")


@app.task
def backup_to_s3():
    db_dir = pathlib.Path(ENV_CONFIG.owl_db_dir)
    logger.info(f"DB PATH: {db_dir}")
    all_chains = []

    for org_dir in db_dir.iterdir():
        if not org_dir.is_dir() or not org_dir.name.startswith("org_"):
            continue
        for project_dir in org_dir.iterdir():
            if not project_dir.is_dir():
                continue
            table_types = [TableType.ACTION, TableType.KNOWLEDGE, TableType.CHAT]

            lance_chains = [
                backup_gen_table_parquet.s(str(org_dir.name), str(project_dir.name), table_type)
                for table_type in table_types
            ]

            all_chains.extend(lance_chains)

    if all_chains:
        return chord(all_chains)(backup_project_results.s())
    else:
        logger.warning("No tasks to execute in the chord.")
        return None


@app.task
def backup_project_results(results):
    failed_project = []
    status_dict = {}
    for success, org_id, project_id in results:
        status_dict[(org_id, project_id)] = status_dict.get((org_id, project_id), True) and success

    results = [[status, *key] for key, status in status_dict.items()]
    true_count = sum(status for status, _, _ in results)

    for success, org_id, project_id in results:
        if not success:
            failed_project.append(f"{org_id}/{project_id}")

    logger.info(
        f"Total number of successful project backup: {true_count} out of {len(results)}. \n {failed_project}"
    )


@app.task
def backup_gen_table_parquet(org_id: str, project_id: str, table_type: str):
    try:
        table = GenerativeTable.from_ids(org_id, project_id, table_type)
        table_dir = f"{ENV_CONFIG.owl_db_dir}/{org_id}/{project_id}/{table_type}"
        with table.create_session() as session:
            offset, total = 0, 1
            while offset < total:
                metas, total = table.list_meta(
                    session,
                    offset=offset,
                    limit=50,
                    remove_state_cols=True,
                    parent_id=None,
                )
                offset += 50
                for meta in metas:
                    upload_path = (
                        f"{get_timestamp()}/db/{org_id}/{project_id}/{table_type}/{meta.id}"
                    )
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_file = os.path.join(tmp_dir, f"{meta.id}.parquet")
                        table.dump_parquet(session=session, table_id=meta.id, dest=tmp_file)
                        s3_client = _get_s3_client()
                        s3_client.upload_file(
                            tmp_file,
                            ENV_CONFIG.s3_backup_bucket_name,
                            f"{upload_path}.parquet",
                        )
                        logger.info(
                            f"Backup to s3://{ENV_CONFIG.s3_backup_bucket_name}/{upload_path}.parquet"
                        )
            return True, org_id, project_id

    except Exception as e:
        logger.error(f"Error backing up Lance table {table_dir}: {e}")
        return False, org_id, project_id
