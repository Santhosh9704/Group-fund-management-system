import sqlite3
import os
from flask import g, current_app

def get_db_connection():
    """Establish a database connection based on config."""
    db_url = current_app.config.get("DATABASE_URL")
    if db_url and (db_url.startswith("postgres://") or db_url.startswith("postgresql://")):
        # We need to import psycopg2 here to avoid strict dependency if running sqlite only
        import psycopg2
        from psycopg2.extras import RealDictCursor
        
        # Handle Render's postgres:// vs postgresql:// protocol if necessary
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
            
        conn = psycopg2.connect(db_url, cursor_factory=RealDictCursor)
        return conn, True
    else:
        # SQLite
        db_path = current_app.config["DATABASE_PATH"]
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        # Enforce foreign key constraints
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn, False

def get_db():
    """Get or create database connection for the current request context."""
    if "db" not in g:
        g.db, g.is_postgres = get_db_connection()
    return g.db

def close_db(e=None):
    """Close the database connection if it exists."""
    db = g.pop("db", None)
    if db is not None:
        db.close()

def query_db(query, args=(), one=False):
    """Execute a query and return results as list of dicts/Rows."""
    db = get_db()
    is_pg = getattr(g, "is_postgres", False)
    
    if is_pg:
        # Translate placeholder '?' to '%s' for PostgreSQL
        query = query.replace("?", "%s")
        cur = db.cursor()
        cur.execute(query, args)
        if cur.description:
            rv = cur.fetchall()
        else:
            rv = None
        cur.close()
    else:
        # SQLite
        cur = db.execute(query, args)
        rv = cur.fetchall()
        cur.close()
        
    return (rv[0] if rv else None) if one else rv

def execute_db(query, args=()):
    """Execute a query without fetching rows (INSERT, UPDATE, DELETE)."""
    db = get_db()
    is_pg = getattr(g, "is_postgres", False)
    
    if is_pg:
        query = query.replace("?", "%s")
        cur = db.cursor()
        cur.execute(query, args)
        # For Postgres, standard cursor doesn't auto-commit unless configured, but our factory handles it or we commit on request end/transaction
        cur.close()
    else:
        db.execute(query, args)

def init_db():
    """Initialize database tables with schema.sql."""
    db, is_pg = get_db_connection()
    schema_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema.sql")
    
    with open(schema_path, "r") as f:
        schema = f.read()
        
    if is_pg:
        # Remove SQLite specific commands
        schema = schema.replace("PRAGMA foreign_keys = ON;", "")
        # SQLite autoincrement translated to PostgreSQL Serial
        schema = schema.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
        
        cur = db.cursor()
        cur.execute(schema)
        db.commit()
        cur.close()
    else:
        db.executescript(schema)
        db.commit()
        
    db.close()
