import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, redirect, url_for, session
from flask_wtf.csrf import CSRFProtect

from finance_app.config import config_by_name
from finance_app.db import close_db
from finance_app.cli import register_commands
from finance_app.utils.helpers import format_currency

csrf = CSRFProtect()

def create_app(config_name="development"):
    # Reference the root templates and static folders relative to this package file
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    template_dir = os.path.join(base_dir, "templates")
    static_dir = os.path.join(base_dir, "static")
    
    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)
    
    # Load configuration
    app.config.from_object(config_by_name[config_name])
    
    # Initialize CSRF Protection
    csrf.init_app(app)
    
    # Register Jinja2 Filters
    app.jinja_env.filters['currency'] = format_currency
    
    # Register blueprints
    from finance_app.auth import auth_bp
    from finance_app.admin import admin_bp
    from finance_app.member import member_bp
    from finance_app.chat import chat_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(member_bp)
    app.register_blueprint(chat_bp)
    
    # Root Redirect Route
    @app.route("/")
    def index():
        if "user_id" in session:
            return redirect(url_for("member.dashboard"))
        return redirect(url_for("auth.login"))
        
    # Database Teardown
    app.teardown_appcontext(close_db)
    
    # Register CLI Commands
    register_commands(app)
    
    # Error Handlers
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def internal_server_error(e):
        return render_template("errors/500.html"), 500

    @app.errorhandler(413)
    def request_entity_too_large(e):
        app.logger.warning("Upload rejected: File size exceeded limit.")
        return render_template("errors/413.html"), 413

    # Production logging configuration
    if not app.debug and not app.testing:
        log_dir = os.path.join(base_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        file_handler = RotatingFileHandler(
            os.path.join(log_dir, "finance_app.log"), maxBytes=102400, backupCount=5
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info("Finance System App startup")
        
    return app
