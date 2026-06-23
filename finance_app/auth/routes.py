from flask import request, redirect, render_template, session, url_for, flash
from werkzeug.security import check_password_hash
from finance_app.db import query_db
from . import auth_bp

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for("member.dashboard"))
        
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        
        if not username or not password:
            return render_template("login.html", error="Please enter both username and password")
            
        user = query_db("SELECT * FROM members WHERE username = ?", (username,), one=True)
        
        # Verify password hash
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["member_id"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            if user["role"] == "admin":
                return redirect(url_for("admin.dashboard"))
            return redirect(url_for("member.dashboard"))
        else:
            return render_template("login.html", error="Invalid username or password")
            
    return render_template("login.html")

@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out successfully.", "info")
    return redirect(url_for("auth.login"))
