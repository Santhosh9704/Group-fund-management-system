from functools import wraps
from flask import session, redirect, url_for, flash, current_app

def login_required(f):
    """Decorator to require user login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    """Decorator to require administrator access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("auth.login"))
        if session.get("role") != "admin":
            flash("⚠️ Access denied. Administrators only.", "danger")
            return redirect(url_for("member.dashboard"))
        return f(*args, **kwargs)
    return decorated_function

def format_currency(value):
    """Format currency values as Indian Rupees."""
    try:
        return f"₹{float(value):,.2f}"
    except (ValueError, TypeError):
        return f"₹{value}"

def allowed_file(filename):
    """Validate upload files against allowed extensions."""
    allowed_exts = current_app.config.get("ALLOWED_EXTENSIONS", {'png', 'jpg', 'jpeg', 'gif'})
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_exts

def calculate_dynamic_emi(loan_amount, total_months, interest_rate_percent, month_no):
    """
    Calculates EMI using Reducing Balance Method (straight-line principal reduction).
    Returns dictionary with details.
    """
    if month_no > total_months:
        return None
        
    principal_constant = loan_amount / total_months
    remaining_principal_start = loan_amount - (principal_constant * (month_no - 1))
    
    if remaining_principal_start < 0:
        remaining_principal_start = 0
        
    interest_amount = (remaining_principal_start * interest_rate_percent) / 100
    total_emi = principal_constant + interest_amount
    
    return {
        "month": month_no,
        "principal_component": principal_constant,
        "interest_component": interest_amount,
        "total_emi": total_emi,
        "remaining_principal_start": remaining_principal_start
    }
