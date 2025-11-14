# JamAIBase — pgaudit Setup

1. PostgreSQL cluster wide auditing is set by pgaudit params in cnpg-cluster-deploy.yaml
2. Object auditing is set in owl db/\_\_init\_\_.py

---

## 1) CNPG Cluster Config (role + pgaudit parameters)

- Can customize the logging option in the parameters, ref. https://github.com/pgaudit/pgaudit/blob/main/README.md
- jamaibase_auditor is the role required for object auditing

```yaml
spec:
  managed:
    roles:
      - name: jamaibase_auditor
        ensure: present
        comment: pgaudit role for jamaibase
        login: false

  postgresql:
    parameters:
      # pgaudit for logging DDL and role changes; include useful context
      # NOTE: Ensure pgaudit is actually loaded via shared_preload_libraries in your cluster.
      # If not already set elsewhere, add:
      # shared_preload_libraries: "pgaudit"
      pgaudit.log: "ddl, role"
      pgaudit.log_catalog: "off"
      pgaudit.log_parameter: "on"
      pgaudit.log_client: "on"
      pgaudit.role: "jamaibase_auditor" # object-based auditing role
```

---

## 2) Object Auditing Grants (in db/\_\_init\_\_.py)

- customize audit_statement based on the level of DML statement you would want to monitor

```python
async def _grant_auditor_priviledge(engine: AsyncEngine) -> bool:
    """
    Apply the necessary grants to allow the auditor role to audit the database.
    """
    auditor_role = "jamaibase_auditor"
    audit_statement = "UPDATE, DELETE"

    async with engine.connect() as conn:
        role_exists = await conn.scalar(
            text(f"SELECT 1 FROM pg_roles WHERE rolname = '{auditor_role}'")
        )
        if role_exists is None:
            return False

        # FUTURE tables in this schema
        await conn.execute(
            text(
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{SCHEMA}" '
                f"GRANT {audit_statement} ON TABLES TO {auditor_role};"
            )
        )

        # EXISTING tables now
        await conn.exec_driver_sql(
            f'GRANT {audit_statement} ON ALL TABLES IN SCHEMA "{SCHEMA}" TO {auditor_role};'
        )
        await conn.commit()

    return True
```
