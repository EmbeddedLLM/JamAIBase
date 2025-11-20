# JamAIBase v1 to v2 migration guide

## Overview

This guide helps migrate your JamAIBase instance from v1 to v2.

## Pre-requisites

- During migration, you will need to have both instances of JamAIBase running concurrently
- For the existing v1 JamAIBase, please re-launch with the new port mapping, to prevent clashing with the v2 instance.

## Launching v1 with updated port mapping

- Update the .env

```
API_PORT=26969
```

- Update the docker/compose.cpu.yml

```
# under the owl service
# from
# image: jamai/owl
# to
image: jamai/owl:v1
```

- Launch v1 JamAIBase with a subset of the services

```
cd /path/to/your/v1/dir
docker compose --env-file .env -f docker/compose.cpu.yml up --scale infinity=0 --scale starling=0 --scale frontend=0 --scale docling=0
```

> if on windows (powershell)

```
cd C:\path\to\your\v1\dir
docker compose -p jamai --env-file .env -f docker/compose.cpu.yml up --scale infinity=0 --scale starling=0 --scale frontend=0 --scale docling=0
```

---

## Launching v2

- Launch v2 JamAIBase

```
cd /path/to/your/v2/dir
docker compose -p jamai --env-file .env -f docker/compose.oss.yml up
```

> if on windows (powershell)

```
cd C:\path\to\your\v2\dir
docker compose -p jamai --env-file .env -f docker/compose.oss.yml up
```

## Run the migration

- Install JamAIBase locally

```
cd /path/to/your/v2/dir
cd services/api
pip install -e .
cd -
cd clients/python
pip install -e .
```

> if on windows (powershell)

```
cd C:\path\to\your\v2\dir

cd services\api
pip install -e .

cd ..\..
cd clients\python
pip install -e .
```

- Run the migration scripts

```
# Check your v1 db path
export OWL_V1_DB=/path/to/your/v1/db/main.db
export OWL_V1_FILE=/path/to/your/v1/file # path to your v1 file directory
export OWL_REDIS_HOST=localhost
export OWL_DB_PATH=postgresql+psycopg://owlpguser:owlpgpassword@localhost:5432/jamaibase_owl

python scripts/oss_migrate.py --db_v1_path ${OWL_V1_DB} --migrate --reset --api_base_dst http://localhost:6969/api --api_base_src http://localhost:26969/api --v1_file_path ${OWL_V1_FILE} --s3_endpoint_dst http://localhost:9000
```

> if on windows (powershell)

```
# Set environment variables for the current PowerShell session
# Use Windows-style paths for your files and databases
 $env:OWL_V1_DB = "C:\path\to\your\v1\db\main.db"
 $env:OWL_V1_FILE = "C:\path\to\your\v1\file"
 $env:OWL_REDIS_HOST = "localhost"
 $env:OWL_DB_PATH = "postgresql+psycopg://owlpguser:owlpgpassword@localhost:5432/jamaibase_owl"

# Run the migration script
# Note the use of '.\' to execute a script in the current directory
# and $env:VAR_NAME to reference environment variables
python .\scripts\oss_migrate.py --db_v1_path $env:OWL_V1_DB --migrate --reset --api_base_dst http://localhost:6969/api --api_base_src http://localhost:26969/api --v1_file_path $env:OWL_V1_FILE --s3_endpoint_dst http://localhost:9000
```

- If everything is successful, you can close the v1 instance
