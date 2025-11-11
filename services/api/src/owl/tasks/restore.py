import multiprocessing
import os
import sqlite3
import time

import boto3
import click
from botocore.client import Config
from loguru import logger

from owl.configs import ENV_CONFIG
from owl.utils.logging import setup_logger_sinks

setup_logger_sinks(f"{ENV_CONFIG.log_dir}/restoration.log")
logger.info(f"Using configuration: {ENV_CONFIG}")


def _get_s3_client():
    _session = boto3.session.Session()
    return _session.client(
        "s3",
        endpoint_url=ENV_CONFIG.s3_endpoint,
        aws_access_key_id=ENV_CONFIG.s3_access_key_id,
        aws_secret_access_key=ENV_CONFIG.s3_secret_access_key_plain,
        config=Config(signature_version="s3v4"),
    )


def _initialize_databases(table_info_list):
    initialized_dbs = set()
    for item in table_info_list:
        org_id = item["org_id"]
        project_id = item["project_id"]
        table_type = item["table_type"]

        lance_path = os.path.join(ENV_CONFIG.db_dir, org_id, project_id, table_type)
        sqlite_path = f"{lance_path}.db"
        if table_type != "file":
            if sqlite_path not in initialized_dbs:
                os.makedirs(os.path.dirname(sqlite_path), exist_ok=True)
                with sqlite3.connect(sqlite_path) as conn:
                    conn.execute("PRAGMA journal_mode=WAL;")
                initialized_dbs.add(sqlite_path)


def get_default_workers():
    return max(multiprocessing.cpu_count() * 8, 1)


# def restore(item):
#     import asyncio

#     try:
#         s3_client = _get_s3_client()
#         org_id = item["org_id"]
#         project_id = item["project_id"]
#         table_type = item["table_type"]
#         table_parquet = item["table_parquet"]

#         if table_type == "file":
#             file_parquet_key = os.path.join(
#                 item["datetime"], "db", org_id, project_id, "file", "file.parquet"
#             )
#             file_lance_dir = os.path.join(
#                 ENV_CONFIG.db_dir, org_id, project_id, "file", "file.lance"
#             )
#             logger.info(f"Processing {org_id}/{project_id}/{table_type}/{table_parquet}")

#             if not os.path.exists(file_lance_dir):
#                 response = s3_client.get_object(
#                     Bucket=ENV_CONFIG.s3_backup_bucket_name, Key=file_parquet_key
#                 )
#                 logger.info(f"Processing {org_id}/{project_id}/file/file.parquet")
#                 body = response["Body"].read()
#                 parquet_table = pq.read_table(BytesIO(body))
#                 lance.write_dataset(parquet_table, file_lance_dir)
#         else:
#             object_key = (
#                 f"{item['datetime']}/db/{org_id}/{project_id}/{table_type}/{table_parquet}"
#             )
#             logger.info(f"Processing {org_id}/{project_id}/{table_type}/{table_parquet}")
#             response = s3_client.get_object(
#                 Bucket=ENV_CONFIG.s3_backup_bucket_name, Key=object_key
#             )
#             table_id = re.sub(r"\.parquet$", "", table_parquet, flags=re.IGNORECASE)
#             table = GenerativeTable.from_ids(org_id, project_id, p.TableType(table_type))

#             body = response["Body"].read()
#             with table.create_session() as session:
#                 _, meta = asyncio.get_event_loop().run_until_complete(
#                     table.import_parquet(
#                         session=session,
#                         source=BytesIO(body),
#                         table_id_dst=table_id,
#                     )
#                 )
#             meta = TableMetaResponse(**meta.model_dump(), num_rows=table.count_rows(meta.id))
#             return meta
#     except Exception as e:
#         logger.error(f"Failed to import table from parquet due to {e.__class__.__name__}: {e}")


@click.command()
def main():
    s3_client = _get_s3_client()
    try:
        datetime_set = set()
        table_info_list = []
        continuation_token = None
        total_objects = 0
        fetch_start_time = time.time()

        # # Ask for the number of workers
        # max_workers = get_default_workers()
        # workers = click.prompt(
        #     f"Enter the number of worker processes to use (1-{max_workers}). Default:",
        #     type=click.IntRange(1, max_workers),
        #     default=max_workers,
        # )

        click.echo("Fetching S3 objects...")
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
                    datetime = prefix["Prefix"].rstrip("/")
                    if datetime != "main-db":
                        datetime_set.add(datetime)

            if not response.get("IsTruncated"):
                break

            continuation_token = response.get("NextContinuationToken")
            total_objects += response.get("KeyCount")

        fetch_end_time = time.time()
        total_fetch_time = fetch_end_time - fetch_start_time
        average_fetch_speed = total_objects / total_fetch_time
        click.echo(
            f"Fetching completed. Total objects: {total_objects}. Average speed: {average_fetch_speed:.2f} objects/second"
        )

        # Display available dates and let user choose
        click.echo("Available dates:")
        for idx, date in enumerate(sorted(datetime_set), 1):
            click.echo(f"{idx}. {date}")

        date_choice = click.prompt("Select a date (enter the number)", type=int, default=1)
        specific_date = sorted(datetime_set)[date_choice - 1]

        try:
            paginator = s3_client.get_paginator("list_objects_v2")
            page_iterator = paginator.paginate(
                Bucket=ENV_CONFIG.s3_backup_bucket_name, Prefix=specific_date
            )

            for page in page_iterator:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        parts = obj["Key"].split("/")

                        datetime, org_id, project_id, table_type, table_parquet = (
                            parts[0],
                            parts[2],
                            parts[3],
                            parts[4],
                            parts[5],
                        )

                        datetime_set.add(datetime)
                        table_info_list.append(
                            {
                                "datetime": datetime,
                                "org_id": org_id,
                                "project_id": project_id,
                                "table_type": table_type,
                                "table_parquet": table_parquet,
                            }
                        )

        except Exception as e:
            logger.error(f"An error occurred: {e}")

        # Check if database files exist and ask for overwrite confirmation
        current_files = os.listdir(ENV_CONFIG.db_dir)
        if current_files:
            click.echo(f"Current database path: {ENV_CONFIG.db_dir}")
            if not click.confirm("Do you want to overwrite the existing files?"):
                click.echo("Operation cancelled.")
                return
        else:
            click.echo(f"Current database path: {ENV_CONFIG.db_dir}")
            if not click.confirm("Confirm restoring to this directory?"):
                click.echo("Operation cancelled.")
                return

    #     table_info_list = sorted(table_info_list, key=lambda x: x["org_id"])
    #     filtered_list = [item for item in table_info_list if item["datetime"] == specific_date]

    #     # Use this before starting the multiprocessing pool
    #     _initialize_databases(filtered_list)
    #     click.echo(f"Using {workers} worker processes")
    #     tic = time.time()

    #     with multiprocessing.Pool(workers, maxtasksperchild=2) as pool:
    #         list(
    #             tqdm(
    #                 pool.imap_unordered(restore, filtered_list),
    #                 total=len(filtered_list),
    #                 desc="Importing tables",
    #                 unit="table",
    #             )
    #         )

    #     click.echo(f"Import completed successfully! {time.time() - tic:.2f}s")

    except Exception as e:
        logger.error(f"Failed to import table from parquet: {e}")
        raise


if __name__ == "__main__":
    main()
