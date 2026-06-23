from flask import request, redirect, render_template, session, url_for, flash, current_app
from datetime import datetime
import os
from werkzeug.utils import secure_filename
from finance_app.db import get_db, query_db, execute_db
from finance_app.utils.helpers import login_required, calculate_dynamic_emi, allowed_file
from . import member_bp

@member_bp.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "admin":
        return redirect(url_for("admin.dashboard"))
        
    user_id = session["user_id"]
    db = get_db()
    
    # Global Stats
    fund_row = query_db("SELECT total_balance FROM fund WHERE id = 1", one=True)
    starting_fund = fund_row['total_balance'] if fund_row else 0
    
    total_collections = query_db("SELECT SUM(amount) FROM monthly_contributions WHERE status = 'paid'", one=True)[0] or 0
    total_repayments_received = query_db("SELECT SUM(amount) FROM interest_payments WHERE status = 'paid'", one=True)[0] or 0
    total_loans_issued = query_db("SELECT SUM(amount) FROM loans WHERE status IN ('approved', 'paid')", one=True)[0] or 0
    
    fund = starting_fund + total_collections + total_repayments_received - total_loans_issued
    
    my_loans = query_db("SELECT * FROM loans WHERE member_id = ?", (user_id,))
    my_contributions = query_db("SELECT * FROM monthly_contributions WHERE member_id = ? ORDER BY year DESC, month DESC", (user_id,))
    
    my_total_savings = sum(c['amount'] for c in my_contributions if c['status'] == 'paid')
    my_active_loans_amount = sum(l['amount'] for l in my_loans if l['status'] == 'approved' and l['repayment_status'] == 'open')
    
    # Loan Display Logic
    loans_display = []
    for loan in my_loans:
        loan_dict = dict(loan)
        if loan["status"] == 'approved' and loan["repayment_status"] == 'open':
            paid_months = query_db("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],), one=True)[0]
            next_month = paid_months + 1
            
            try:
                payment_type = loan['payment_type'] if loan['payment_type'] else 'monthly'
            except (KeyError, IndexError):
                payment_type = 'monthly'
            loan_dict['payment_type'] = payment_type
            
            if payment_type == 'lump_sum':
                if paid_months == 0:
                    total_interest = int((loan['amount'] * loan['interest_rate_percent'] * loan['total_months']) / 100)
                    loan_dict["next_emi_amount"] = loan['amount'] + total_interest
                else:
                    loan_dict["next_emi_amount"] = 0
            else:
                emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
                if emi_calc:
                    loan_dict["next_emi_amount"] = emi_calc["total_emi"]
                    loan_dict["next_payment_month"] = next_month
                else:
                    loan_dict["next_emi_amount"] = 0
        else:
            loan_dict["next_emi_amount"] = 0
            
        loans_display.append(loan_dict)
        
    return render_template("dashboard_member.html", 
                         balance=fund, 
                         my_total_savings=my_total_savings,
                         alerts=[], 
                         my_active_loans_amount=my_active_loans_amount,
                         loans=loans_display, 
                         contributions=my_contributions,
                         user_name=session["name"])

@member_bp.route("/request_loan", methods=["GET", "POST"])
@login_required
def request_loan():
    if request.method == "POST":
        amount = int(request.form.get("amount", 0))
        months = int(request.form.get("months", 1))
        interest_rate = 1.0  # Default 1% per month
        
        if amount < 500 or months < 1:
            flash("⚠️ Invalid loan parameters.", "danger")
            return redirect(url_for("member.request_loan"))
            
        interest_portion = int((amount * interest_rate) / 100)
        principal_portion = int(amount / months)
        emi_amount = principal_portion + interest_portion
        
        execute_db("""INSERT INTO loans (member_id, amount, interest_rate_percent, interest_per_month, total_months, 
                                      status, repayment_status, request_time, emi_amount, principal_portion, interest_portion, remaining_balance)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                   (session["user_id"], amount, interest_rate, interest_portion, months, 'pending', 'open', 
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"), emi_amount, principal_portion, interest_portion, amount))
        get_db().commit()
        flash("🎉 Loan request submitted successfully! Pending admin approval.", "success")
        return redirect(url_for("member.dashboard"))
        
    return render_template("request_loan.html", user_name=session["name"])

@member_bp.route("/submit_payment_proof", methods=["GET", "POST"])
@login_required
def submit_payment_proof():
    if request.method == "POST":
        proof_type = request.form.get("proof_type", "emi")
        
        if 'screenshot' not in request.files:
            flash("⚠️ No screenshot uploaded.", "danger")
            return redirect(request.url)
            
        file = request.files['screenshot']
        if file.filename == '':
            flash("⚠️ No selected screenshot.", "danger")
            return redirect(request.url)
            
        if file and allowed_file(file.filename):
            if proof_type == "emi":
                loan_id = request.form.get("loan_id")
                month_no = request.form.get("month_no")
                amount = request.form.get("amount_emi")
                month = None
                year = None
                
                if not loan_id or not month_no or not amount:
                    flash("⚠️ Incomplete EMI details.", "danger")
                    return redirect(request.url)
            else:
                loan_id = None
                month_no = None
                amount = 200
                month = request.form.get("month")
                year = request.form.get("year")
                
                if not month or not year:
                    flash("⚠️ Incomplete savings details.", "danger")
                    return redirect(request.url)
                    
            # Ensure upload directory exists
            os.makedirs(current_app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = secure_filename(f"{session['user_id']}_{proof_type}_{timestamp}_{file.filename}")
            filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Save relative path in database to keep it clean and deployment-friendly
            relative_path = f"uploads/payment_proofs/{filename}"
            
            execute_db("""INSERT INTO payment_proofs (proof_type, loan_id, member_id, month_no, month, year, amount, screenshot_path, status, submission_date) 
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       (proof_type, loan_id, session["user_id"], month_no, month, year, amount, relative_path, 'pending', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            get_db().commit()
            
            flash("🎉 Payment proof uploaded successfully! Admin will review it shortly.", "success")
            return redirect(url_for("member.dashboard"))
        else:
            flash("⚠️ Allowed file types are PNG, JPG, JPEG, GIF.", "danger")
            return redirect(request.url)
            
    # GET
    active_loans = query_db("SELECT * FROM loans WHERE member_id=? AND status='approved' AND repayment_status='open'", (session['user_id'],))
    loans_display = []
    for loan in active_loans:
        l = dict(loan)
        paid_count = query_db("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],), one=True)[0]
        next_month = paid_count + 1
        l['next_payment_month'] = next_month
        
        try:
            payment_type = loan['payment_type'] if loan['payment_type'] else 'monthly'
        except (KeyError, IndexError):
            payment_type = 'monthly'
        l['payment_type'] = payment_type
        
        if payment_type == 'lump_sum':
            if paid_count == 0:
                total_interest = int((loan['amount'] * loan['interest_rate_percent'] * loan['total_months']) / 100)
                l['next_emi_amount'] = loan['amount'] + total_interest
            else:
                l['next_emi_amount'] = 0
        else:
            emi = calculate_dynamic_emi(loan['amount'], loan['total_months'], loan['interest_rate_percent'], next_month)
            l['next_emi_amount'] = emi['total_emi'] if emi else 0
            
        loans_display.append(l)

    return render_template("submit_payment_proof.html", loans=loans_display, user_name=session["name"])

@member_bp.route("/loan_tracking")
@login_required
def loan_tracking():
    loans = query_db("SELECT l.*, m.name FROM loans l JOIN members m ON l.member_id = m.member_id WHERE l.status='approved' ORDER BY l.repayment_status DESC, l.approved_time DESC")
    
    loans_display = []
    for loan in loans:
        l_dict = dict(loan)
        
        paid_count = query_db("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],), one=True)[0]
        l_dict['months_paid'] = paid_count
        
        try:
            payment_type = loan['payment_type'] if loan['payment_type'] else 'monthly'
        except (KeyError, IndexError):
            payment_type = 'monthly'
        l_dict['payment_type'] = payment_type
        
        # Calculate dynamic remaining balance
        if payment_type == 'lump_sum':
            l_dict['dynamic_remaining_balance'] = loan['remaining_balance']
        else:
            current_balance = loan["amount"] - (loan["principal_portion"] * paid_count)
            if current_balance < 0: current_balance = 0
            l_dict['dynamic_remaining_balance'] = current_balance
        
        # Get actual total paid from database
        total_paid = query_db("SELECT SUM(amount) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],), one=True)[0] or 0
        l_dict['total_paid_amount'] = total_paid
        
        if loan["repayment_status"] == 'open':
            next_month = paid_count + 1
            
            if payment_type == 'lump_sum':
                if paid_count == 0:
                    total_interest = int((loan['amount'] * loan['interest_rate_percent'] * loan['total_months']) / 100)
                    l_dict["current_emi_amount"] = loan['amount'] + total_interest
                    l_dict["current_interest_portion"] = total_interest
                else:
                    l_dict["current_emi_amount"] = 0
                    l_dict["current_interest_portion"] = 0
            else:
                emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
                if emi_calc:
                    l_dict["current_emi_amount"] = emi_calc["total_emi"]
                    l_dict["current_interest_portion"] = emi_calc["interest_component"]
                else:
                    l_dict["current_emi_amount"] = 0
                    l_dict["current_interest_portion"] = 0
        else:
             l_dict["current_emi_amount"] = 0
             l_dict["current_interest_portion"] = 0
             
        loans_display.append(l_dict)
        
    return render_template("loan_tracking.html", loans=loans_display)
