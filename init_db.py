import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

# Initialize local SQLite database
conn = sqlite3.connect('database.db')
cur = conn.cursor()

# Execute schema script
with open('schema.sql', 'r') as f:
    schema = f.read()
    cur.executescript(schema)

# Seed admin user and default fund balance
try:
    hashed_pwd = generate_password_hash("admin123")
    cur.execute(
        "INSERT INTO members (name, username, password, role, join_date) VALUES (?, ?, ?, ?, ?)",
        ("Super Admin", "admin", hashed_pwd, "admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    cur.execute("INSERT INTO fund (id, total_balance) VALUES (1, 20000)")
    conn.commit()
    print("✅ Database initialized and seed admin user created successfully!")
    print("Default Username: admin")
    print("Default Password: admin123")
except sqlite3.IntegrityError:
    print("ℹ️ Database schema already set up. Seeding skipped.")
finally:
    conn.close()
