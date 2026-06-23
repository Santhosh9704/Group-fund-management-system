import click
from flask.cli import with_appcontext
from finance_app.db import init_db, get_db
from werkzeug.security import generate_password_hash
from datetime import datetime

@click.command("init-db")
@with_appcontext
def init_db_command():
    """Clear existing data and create new tables."""
    init_db()
    click.echo("✅ Database initialized successfully!")

@click.command("create-admin")
@click.argument("username")
@click.argument("password")
@with_appcontext
def create_admin_command(username, password):
    """Create a new administrator account."""
    db = get_db()
    hashed_pwd = generate_password_hash(password)
    
    # We can use our wrapper or raw sql cursor depending on DB type
    try:
        from finance_app.db import query_db, execute_db
        # Create Super Admin
        execute_db(
            "INSERT INTO members (name, username, password, role, join_date) VALUES (?, ?, ?, ?, ?)",
            ("Super Admin", username, hashed_pwd, "admin", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
        # Initialize default fund balance
        execute_db(
            "INSERT INTO fund (id, total_balance) VALUES (1, 20000)"
        )
        db.commit()
        click.echo(f"✅ Admin user '{username}' created successfully!")
    except Exception as e:
        click.echo(f"❌ Error creating admin user: {e}")

def register_commands(app):
    """Register CLI commands with the Flask application."""
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_admin_command)
