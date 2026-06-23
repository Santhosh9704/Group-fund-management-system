from flask import request, redirect, render_template, session, url_for
from datetime import datetime
from finance_app.db import get_db, query_db, execute_db
from finance_app.utils.helpers import login_required
from . import chat_bp

@chat_bp.route("/chat")
@login_required
def chat():
    messages = query_db("""
        SELECT m.*, u.name 
        FROM messages m 
        JOIN members u ON m.member_id = u.member_id 
        ORDER BY m.timestamp
    """)
    return render_template("chat.html", 
                         messages=messages, 
                         user_id=session["user_id"], 
                         user_name=session["name"])

@chat_bp.route("/send_message", methods=["POST"])
@login_required
def send_message():
    content = request.form.get("content", "").strip()
    if content:
        execute_db("INSERT INTO messages (member_id, content, timestamp) VALUES (?, ?, ?)",
                   (session["user_id"], content, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        get_db().commit()
    return redirect(url_for("chat.chat"))
