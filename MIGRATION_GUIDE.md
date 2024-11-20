# Migration Guide

This guide provides instructions to perform a database migration that adds a `version` column and `object` attribute to all gen_config in all action tables. (Migration from owl version earlier than v0.3.0).

## Prerequisites

1. Ensure **owl/jamaibase** has been updated to at least **v0.3.0**.

## Steps to Perform the Migration

1. Navigate to the **JamAIBase** repository directory (with `./db` and `./scripts` in it).

   ```bash
   cd <JamAIBase repository directory>
   ```

2. Run the migration script (ensure the current Python environment is the one with **owl** installed):
   ```bash
   python scripts/migration_v030.py
   ```

## Expected Output

- The script will print messages indicating whether the `version` column was added or if it already exists in each database.
- The script will print messages indicating whether the `object` attribute was added into each `gen_config`.
- If any errors occur, they will be printed to the console.

## Troubleshooting

- Ensure that the migration script is run in the **JamAIBase** repository directory (`./db` and `./scripts` directories should be in this working directory).
- Ensure the Python environment is the one with **owl** installed.
- Check the script's error messages for any issues encountered during the migration process.
- Contact us for further assistance.
