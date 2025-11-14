from datetime import datetime, timedelta, timezone

import boto3
from botocore.client import Config
from loguru import logger

from owl.configs import ENV_CONFIG, celery_app

AWS_DELETE_API_MAX_OBJECT_LIMIT = 1000


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


@celery_app.task
def s3_cleanup():
    s3_client = _get_s3_client()
    current_date = datetime.utcnow().date()
    hourly_backup_retention_period = timedelta(days=7)
    daily_backup_retention_period = timedelta(days=30)
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
                        if current_date - backup_date > hourly_backup_retention_period:
                            datetime_list.append(date_hour)

            if not response.get("IsTruncated"):
                break

            continuation_token = response.get("NextContinuationToken")

        date_objects = [datetime.strptime(date_str, "%Y-%m-%d-%H") for date_str in datetime_list]

        # Separate backups older than 2 months
        older_than_daily_rentention_period = [
            date_obj
            for date_obj in date_objects
            if current_date - date_obj.date() > daily_backup_retention_period
        ]

        within_daily_rentention_period = [
            date_obj
            for date_obj in date_objects
            if current_date - date_obj.date() <= daily_backup_retention_period
        ]

        # Find the latest backup for each month older than two months
        latest_by_month = {}
        for date_obj in older_than_daily_rentention_period:
            month_key = (date_obj.year, date_obj.month)
            if month_key not in latest_by_month or date_obj > latest_by_month[month_key]:
                latest_by_month[month_key] = date_obj

        # Find the latest hour for each day
        latest_by_day = {}
        for date_obj in within_daily_rentention_period:
            date_key = date_obj.date()
            if date_key not in latest_by_day or date_obj > latest_by_day[date_key]:
                latest_by_day[date_key] = date_obj

        # Create a list of all entries except the latest for each day and month
        datetime_list = [
            date_obj.strftime("%Y-%m-%d-%H")
            for date_obj in date_objects
            if (
                current_date - date_obj.date() <= daily_backup_retention_period
                and date_obj != latest_by_day[date_obj.date()]
            )
            or (
                current_date - date_obj.date() > daily_backup_retention_period
                and date_obj != latest_by_month[(date_obj.year, date_obj.month)]
            )
        ]
        for time in datetime_list:
            paginator = s3_client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=ENV_CONFIG.s3_backup_bucket_name, Prefix=time
            )

            for page in page_iterator:
                if "Contents" in page:
                    # Collect object keys to delete
                    objects_to_delete = [{"Key": obj["Key"]} for obj in page["Contents"]]

                    # Delete objects in batches of up to 1000
                    for i in range(0, len(objects_to_delete), AWS_DELETE_API_MAX_OBJECT_LIMIT):
                        batch = objects_to_delete[i : i + AWS_DELETE_API_MAX_OBJECT_LIMIT]
                        response = s3_client.delete_objects(
                            Bucket=ENV_CONFIG.s3_backup_bucket_name,
                            Delete={"Objects": batch, "Quiet": True},
                        )

            logger.info(f"S3 Cleanup done for {time}!")

    except Exception as e:
        logger.error(f"S3 Cleanup failed:\n {e}")


@celery_app.task
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
        f"Total number of successful project backup: {true_count} out of {len(results)}. \n Failed projects: {failed_project}"
    )
