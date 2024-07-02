import sqlite3

conn = sqlite3.connect("db/main.db")
c = conn.cursor()
c.execute("ALTER TABLE organization ADD COLUMN db_storage_gb REAL DEFAULT 0.0")
c.execute("ALTER TABLE organization ADD COLUMN file_storage_gb REAL DEFAULT 0.0")
# conn.commit()
# c.execute("PRAGMA table_info(organization)")
# print(c.fetchall())
c.execute("SELECT COUNT(*) FROM user")
# c.execute("SELECT * FROM organization LIMIT 1")
print(c.fetchall())
