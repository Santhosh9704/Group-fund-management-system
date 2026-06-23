import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash

# Create admin user with hashed password
conn = sqlite3.connect('database.db')
cur = conn.cursor()

try:
    hashed_password = generate_password_hash("admin123")
    cur.execute("INSERT INTO members (name, username, password, role, join_date) VALUES (?, ?, ?, ?, ?)",
                ("Super Admin", "admin", hashed_password, "admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    cur.execute("INSERT INTO fund (id, total_balance) VALUES (1, 20000)")
    conn.commit()
    print("✅ Admin user created successfully with secure hashed password!")
    print("Username: admin")
    print("Password: admin123")
except sqlite3.IntegrityError as e:
    print(f"ℹ️ Admin already exists or database error: {e}")
finally:
    conn.close()
