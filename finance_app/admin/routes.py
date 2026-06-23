from flask import request, redirect, render_template, session, url_for, flash, send_file, current_app
from datetime import datetime
import io
import pandas as pd
from werkzeug.security import generate_password_hash
from finance_app.db import get_db, query_db, execute_db
from finance_app.utils.helpers import admin_required, calculate_dynamic_emi
from . import admin_bp

@admin_bp.route("/admin/dashboard")
@admin_required
def dashboard():
    db = get_db()
    
    # Global Stats
    fund_row = query_db("SELECT total_balance FROM fund WHERE id = 1", one=True)
    starting_fund = fund_row['total_balance'] if fund_row else 0
    
    total_collections = query_db("SELECT SUM(amount) FROM monthly_contributions WHERE status = 'paid'", one=True)[0] or 0
    total_repayments_received = query_db("SELECT SUM(amount) FROM interest_payments WHERE status = 'paid'", one=True)[0] or 0
    total_loans_issued = query_db("SELECT SUM(amount) FROM loans WHERE status IN ('approved', 'paid')", one=True)[0] or 0
    
    fund = starting_fund + total_collections + total_repayments_received - total_loans_issued
    
    # Real Interest Logic
    payments = query_db("""
        SELECT 
            p.amount as payment_amount, 
            p.month_no,
            l.amount as loan_amount,
            l.total_months,
            l.principal_portion,
            l.interest_rate_percent,
            l.payment_type
        FROM interest_payments p
        JOIN loans l ON p.loan_id = l.loan_id
        WHERE p.status = 'paid'
    """)
    
    real_interest_earned = 0
    for p in payments:
        try:
            ptype = p['payment_type'] if p['payment_type'] else 'monthly'
        except (KeyError, IndexError):
            ptype = 'monthly'
            
        if ptype == 'lump_sum':
            interest_component = (p['loan_amount'] * p['interest_rate_percent'] * p['total_months']) / 100
        else:
            principal_constant = p['principal_portion']
            month_no = p['month_no']
            loan_amt = p['loan_amount']
            
            remaining_principal = loan_amt - (principal_constant * (month_no - 1))
            if remaining_principal < 0: 
                remaining_principal = 0
                
            interest_component = (remaining_principal * p['interest_rate_percent']) / 100
        real_interest_earned += interest_component

    # Pending Principal
    active_loans = query_db("SELECT * FROM loans WHERE status = 'approved' AND repayment_status='open'")
    
    total_pending_principal = 0
    for loan in active_loans:
        try:
            ptype = loan['payment_type'] if loan['payment_type'] else 'monthly'
        except (KeyError, IndexError):
            ptype = 'monthly'
            
        if ptype == 'lump_sum':
            total_pending_principal += loan['remaining_balance']
        else:
            paid_months = query_db("SELECT COUNT(*) FROM interest_payments WHERE loan_id = ? AND status = 'paid'", (loan['loan_id'],), one=True)[0]
            current_balance = loan['amount'] - (loan['principal_portion'] * paid_months)
            if current_balance < 0: 
                current_balance = 0
            total_pending_principal += current_balance

    active_loans_count = len(active_loans)
    closed_loans_count = query_db("SELECT COUNT(*) FROM loans WHERE repayment_status='closed'", one=True)[0]
    
    # Pending Contributions
    current_month = datetime.now().month
    current_year = datetime.now().year
    total_members_count = query_db("SELECT COUNT(*) FROM members WHERE role='member'", one=True)[0]
    paid_members_this_month = query_db("SELECT COUNT(*) FROM monthly_contributions WHERE month=? AND year=? AND status='paid'", (current_month, current_year), one=True)[0]
    pending_contributions_count = total_members_count - paid_members_this_month
    if pending_contributions_count < 0: 
        pending_contributions_count = 0
    
    # Tables Data
    loans = query_db("SELECT l.*, m.name FROM loans l JOIN members m ON l.member_id = m.member_id ORDER BY request_time DESC")
    contributions = query_db("SELECT c.*, m.name FROM monthly_contributions c JOIN members m ON c.member_id = m.member_id ORDER BY year DESC, month DESC")
    members_list = query_db("SELECT * FROM members WHERE role='member'")
    
    return render_template("dashboard_admin.html", 
                         balance=fund, 
                         total_collections=total_collections,
                         total_loans_issued=total_loans_issued,
                         total_interest=real_interest_earned,
                         total_pending_principal=total_pending_principal,
                         active_loans_count=active_loans_count,
                         closed_loans_count=closed_loans_count,
                         pending_contributions_count=pending_contributions_count,
                         members=members_list, 
                         loans=loans, 
                         contributions=contributions)

@admin_bp.route("/admin/update_fund_balance", methods=["POST"])
@admin_required
def update_fund_balance():
    try:
        amount = float(request.form.get("amount", 0))
        execute_db("UPDATE fund SET total_balance = ? WHERE id = 1", (amount,))
        get_db().commit()
    except Exception as e:
        current_app.logger.error(f"Error updating starting fund: {e}")
        flash("⚠️ Error updating fund balance.", "danger")
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/add_member", methods=["POST"])
@admin_required
def add_member():
    name = request.form.get("name", "").strip()
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    
    if not name or not username or not password:
        flash("⚠️ Incomplete member details.", "danger")
        return redirect(url_for("admin.dashboard"))
        
    hashed_pwd = generate_password_hash(password)
    try:
        execute_db("INSERT INTO members (name, username, password, role, join_date) VALUES (?, ?, ?, ?, ?)",
                   (name, username, hashed_pwd, 'member', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        get_db().commit()
        flash(f"🎉 Member '{name}' added successfully!", "success")
    except Exception as e:
        current_app.logger.error(f"Error adding member: {e}")
        flash("⚠️ Username already exists or database error occurred.", "danger")
        
    return redirect(url_for("admin.dashboard"))

@admin_bp.route("/update_contribution_status", methods=["POST"])
@admin_required
def update_contribution_status():
    member_id = request.form.get("member_id")
    month = int(request.form.get("month", 0))
    year = int(request.form.get("year", 0))
    action = request.form.get("action", "pay")
    amount = 200
    
    existing = query_db("SELECT id, status FROM monthly_contributions WHERE member_id=? AND month=? AND year=?", 
                        (member_id, month, year), one=True)
                          
    if action == "pay":
        if not existing:
             execute_db("INSERT INTO monthly_contributions (member_id, month, year, amount, status, paid_date) VALUES (?,?,?,?,?,?)",
                        (member_id, month, year, amount, 'paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        elif existing['status'] == 'pending':
             execute_db("UPDATE monthly_contributions SET status='paid', paid_date=? WHERE id=?", 
                        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), existing['id']))
    elif action == "unpay":
         if existing:
             execute_db("UPDATE monthly_contributions SET status='pending', paid_date=NULL WHERE id=?", 
                        (existing['id'],))
                          
    get_db().commit()
    return redirect(url_for("admin.contribution_tracking", year=year))

@admin_bp.route("/admin/loans")
@admin_required
def admin_loans():
    pending_loans = query_db("SELECT l.*, m.name FROM loans l JOIN members m ON l.member_id = m.member_id WHERE l.status='pending' ORDER BY request_time")
    active_loans_raw = query_db("SELECT l.*, m.name FROM loans l JOIN members m ON l.member_id = m.member_id WHERE l.status='approved' AND l.repayment_status='open' ORDER BY approved_time DESC")
    
    active_loans = []
    total_active_principal = 0
    
    for loan in active_loans_raw:
        l_dict = dict(loan)
        total_active_principal += loan['amount']
        
        paid_count = query_db("SELECT COUNT(*) FROM interest_payments WHERE loan_id=? AND status='paid'", (loan['loan_id'],), one=True)[0]
        next_month = paid_count + 1
        l_dict['next_payment_month'] = next_month
        
        try:
            payment_type = loan['payment_type'] if loan['payment_type'] else 'monthly'
        except (KeyError, IndexError):
            payment_type = 'monthly'
        l_dict['payment_type'] = payment_type
        
        if payment_type == 'lump_sum':
            if paid_count == 0:
                total_interest = int((loan['amount'] * loan['interest_rate_percent'] * loan['total_months']) / 100)
                l_dict['next_emi_amount'] = loan['amount'] + total_interest
                l_dict['payment_label'] = 'Full Payment Due'
            else:
                l_dict['next_emi_amount'] = 0
                l_dict['payment_label'] = 'Paid'
        else:
            emi_calc = calculate_dynamic_emi(loan["amount"], loan["total_months"], loan["interest_rate_percent"], next_month)
            if emi_calc:
                l_dict["next_emi_amount"] = emi_calc["total_emi"]
                l_dict['payment_label'] = f'EMI Month {next_month}'
            else:
                l_dict["next_emi_amount"] = 0
                l_dict['payment_label'] = 'Completed'
            
        active_loans.append(l_dict)
        
    interest_collected_month = 0 
    all_members = query_db("SELECT * FROM members WHERE role='member' ORDER BY name")
    
    return render_template("admin_loans.html",
                         pending_count=len(pending_loans),
                         total_active_principal=total_active_principal,
                         interest_collected_month=interest_collected_month,
                         pending_loans=pending_loans,
                         active_loans=active_loans,
                         all_members=all_members)

@admin_bp.route("/approve_loan/<int:loan_id>")
@admin_required
def approve_loan(loan_id):
    execute_db("UPDATE loans SET status='approved', repayment_status='open', approved_time=? WHERE loan_id=?", 
               (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), loan_id))
    get_db().commit()
    flash("✅ Loan application approved.", "success")
    return redirect(url_for("admin.admin_loans"))

@admin_bp.route("/reject_loan/<int:loan_id>")
@admin_required
def reject_loan(loan_id):
    execute_db("UPDATE loans SET status='rejected' WHERE loan_id=?", (loan_id,))
    get_db().commit()
    flash("ℹ️ Loan application rejected.", "info")
    return redirect(url_for("admin.admin_loans"))

@admin_bp.route("/admin/create_loan", methods=["POST"])
@admin_required
def create_loan():
    member_id = request.form.get("member_id")
    amount = int(request.form.get("amount", 0))
    months = int(request.form.get("months", 1))
    interest_rate = float(request.form.get("interest_rate", 1.0))
    payment_type = request.form.get("payment_type", "monthly")
    
    if not member_id or amount <= 0 or months <= 0:
        flash("⚠️ Invalid parameters for creating loan.", "danger")
        return redirect(url_for("admin.admin_loans"))
        
    if payment_type == "lump_sum":
        total_interest = int((amount * interest_rate * months) / 100)
        interest_portion = total_interest
        principal_portion = amount
        emi_amount = amount + total_interest
    else:
        interest_portion = int((amount * interest_rate) / 100)
        principal_portion = int(amount / months)
        emi_amount = principal_portion + interest_portion
    
    execute_db("""INSERT INTO loans (member_id, amount, interest_rate_percent, interest_per_month, total_months, 
                                  status, repayment_status, request_time, approved_time, emi_amount, principal_portion, interest_portion, remaining_balance, payment_type)
                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
               (member_id, amount, interest_rate, interest_portion, months, 'approved', 'open', 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                emi_amount, principal_portion, interest_portion, amount, payment_type))
    get_db().commit()
    flash("✅ Loan created successfully!", "success")
    return redirect(url_for("admin.admin_loans"))

@admin_bp.route("/update_interest", methods=["POST"])
@admin_required
def update_interest():
    loan_id = request.form.get("loan_id")
    month_no = request.form.get("month_no")
    amount = float(request.form.get("amount", 0))
    
    loan = query_db("SELECT * FROM loans WHERE loan_id=?", (loan_id,), one=True)
    if not loan:
        flash("❌ Loan not found", "danger")
        return redirect(url_for("admin.admin_loans"))
        
    try:
        ptype = loan['payment_type'] if loan['payment_type'] else 'monthly'
    except (KeyError, IndexError):
        ptype = 'monthly'
        
    if ptype == "lump_sum":
        # Entire payment is processed, closing the loan
        interest_component = (loan['amount'] * loan['interest_rate_percent'] * loan['total_months']) / 100
        principal_component = loan['amount']
        new_balance = 0
        status_update = "closed"
    else:
        current_balance = loan['remaining_balance']
        interest_rate = loan['interest_rate_percent']
        interest_component = (current_balance * interest_rate) / 100
        principal_component = amount - interest_component
        new_balance = current_balance - principal_component
        status_update = "open"
        if new_balance <= 1:
            new_balance = 0
            status_update = "closed"
        
    # Record payment
    execute_db("INSERT INTO interest_payments (loan_id, month_no, amount, status, paid_date) VALUES (?, ?, ?, ?, ?)",
               (loan_id, month_no, amount, 'paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
               
    if status_update == "closed":
        execute_db("UPDATE loans SET remaining_balance=?, repayment_status='closed', closed_time=? WHERE loan_id=?", 
                   (new_balance, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), loan_id))
    else:
        execute_db("UPDATE loans SET remaining_balance=? WHERE loan_id=?", 
                   (new_balance, loan_id))
        
    get_db().commit()
    flash(f"✅ Payment recorded. Updated remaining balance to {new_balance}.", "success")
    return redirect(url_for("admin.admin_loans"))

@admin_bp.route("/admin/payment_proofs")
@admin_required
def admin_payment_proofs():
    proofs = query_db("""SELECT p.*, m.name, l.amount as loan_amount 
                           FROM payment_proofs p 
                           JOIN members m ON p.member_id = m.member_id 
                           LEFT JOIN loans l ON p.loan_id = l.loan_id 
                           WHERE p.status='pending' ORDER BY submission_date DESC""")
    return render_template("admin_payment_proofs.html", pending_proofs=proofs)

@admin_bp.route("/admin/manage_payments")
@admin_required
def admin_manage_payments():
    contributions = query_db("SELECT c.*, m.name FROM monthly_contributions c JOIN members m ON c.member_id = m.member_id ORDER BY year DESC, month DESC")
    interest_payments = query_db("SELECT p.*, m.name, l.amount as loan_amount FROM interest_payments p JOIN loans l ON p.loan_id = l.loan_id JOIN members m ON l.member_id = m.member_id ORDER BY paid_date DESC")
    
    return render_template("admin_manage_payments.html", 
                         contributions=contributions, 
                         interest_payments=interest_payments)

@admin_bp.route("/admin/delete_contribution/<int:id>", methods=["POST"])
@admin_required
def delete_contribution(id):
    execute_db("DELETE FROM monthly_contributions WHERE id=?", (id,))
    get_db().commit()
    flash("✅ Contribution deleted successfully.", "success")
    return redirect(url_for("admin.admin_manage_payments"))

@admin_bp.route("/admin/delete_interest/<int:id>", methods=["POST"])
@admin_required
def delete_interest(id):
    payment = query_db("SELECT * FROM interest_payments WHERE id=?", (id,), one=True)
    if not payment:
        flash("❌ Payment not found.", "danger")
        return redirect(url_for("admin.admin_manage_payments"))
    
    loan_id = payment['loan_id']
    loan = query_db("SELECT * FROM loans WHERE loan_id=?", (loan_id,), one=True)
    if not loan:
        flash("❌ Associated loan not found.", "danger")
        return redirect(url_for("admin.admin_manage_payments"))
    
    # Delete payment
    execute_db("DELETE FROM interest_payments WHERE id=?", (id,))
    
    # Recalculate loan balance
    all_payments = query_db("SELECT * FROM interest_payments WHERE loan_id=? ORDER BY id ASC", (loan_id,))
    
    try:
        ptype = loan['payment_type'] if loan['payment_type'] else 'monthly'
    except (KeyError, IndexError):
        ptype = 'monthly'
        
    original_amount = loan['amount']
    new_balance = original_amount
    interest_rate = loan['interest_rate_percent']
    
    for pmt in all_payments:
        if ptype == 'lump_sum':
            new_balance = 0
        else:
            interest_component = (new_balance * interest_rate) / 100
            principal_component = pmt['amount'] - interest_component
            new_balance = new_balance - principal_component
    
    if new_balance > 0:
        execute_db("UPDATE loans SET remaining_balance=?, repayment_status='open', closed_time=NULL WHERE loan_id=?",
                   (new_balance, loan_id))
    else:
        execute_db("UPDATE loans SET remaining_balance=? WHERE loan_id=?", (0, loan_id))
        
    get_db().commit()
    flash(f"✅ Payment deleted successfully. Loan balance updated to {new_balance}.", "success")
    return redirect(url_for("admin.admin_manage_payments"))

@admin_bp.route("/admin/delete_loan/<int:loan_id>", methods=["POST"])
@admin_required
def delete_loan(loan_id):
    execute_db("DELETE FROM interest_payments WHERE loan_id=?", (loan_id,))
    execute_db("DELETE FROM payment_proofs WHERE loan_id=?", (loan_id,))
    execute_db("DELETE FROM loans WHERE loan_id=?", (loan_id,))
    get_db().commit()
    flash("✅ Loan and all associated history deleted successfully.", "success")
    return redirect(url_for("admin.admin_loans"))

@admin_bp.route("/admin/loan_payment_history/<int:loan_id>")
@admin_required
def loan_payment_history(loan_id):
    payments = query_db("SELECT * FROM interest_payments WHERE loan_id=? ORDER BY id DESC", (loan_id,))
    payment_list = [{
        'id': payment['id'],
        'month_no': payment['month_no'],
        'amount': payment['amount'],
        'paid_date': payment['paid_date']
    } for payment in payments]
    return {"payments": payment_list}

@admin_bp.route("/admin/undo_payment/<int:payment_id>", methods=["POST"])
@admin_required
def undo_payment(payment_id):
    payment = query_db("SELECT * FROM interest_payments WHERE id=?", (payment_id,), one=True)
    if not payment:
        flash("❌ Payment not found.", "danger")
        return redirect(url_for("admin.admin_loans"))
    
    loan_id = payment['loan_id']
    loan = query_db("SELECT * FROM loans WHERE loan_id=?", (loan_id,), one=True)
    if not loan:
        flash("❌ Associated loan not found.", "danger")
        return redirect(url_for("admin.admin_loans"))
    
    all_payments = query_db("SELECT * FROM interest_payments WHERE loan_id=? ORDER BY id ASC", (loan_id,))
    
    try:
        ptype = loan['payment_type'] if loan['payment_type'] else 'monthly'
    except (KeyError, IndexError):
        ptype = 'monthly'
        
    original_amount = loan['amount']
    new_balance = original_amount
    interest_rate = loan['interest_rate_percent']
    
    for pmt in all_payments:
        if pmt['id'] == payment_id:
            continue
        if ptype == 'lump_sum':
            new_balance = 0
        else:
            interest_component = (new_balance * interest_rate) / 100
            principal_component = pmt['amount'] - interest_component
            new_balance = new_balance - principal_component
            
    execute_db("DELETE FROM interest_payments WHERE id=?", (payment_id,))
    
    execute_db("UPDATE loans SET remaining_balance=?, repayment_status='open', closed_time=NULL WHERE loan_id=?",
               (new_balance, loan_id))
    get_db().commit()
    flash(f"✅ Payment undone successfully. Balance restored to {new_balance}.", "success")
    return redirect(url_for("admin.admin_loans"))

@admin_bp.route("/admin/approve_payment_proof/<int:proof_id>")
@admin_required
def approve_payment_proof(proof_id):
    proof = query_db("SELECT * FROM payment_proofs WHERE proof_id=?", (proof_id,), one=True)
    
    if proof and proof['status'] == 'pending':
        if proof['proof_type'] == 'emi':
            loan = query_db("SELECT * FROM loans WHERE loan_id=?", (proof['loan_id'],), one=True)
            if loan:
                try:
                    ptype = loan['payment_type'] if loan['payment_type'] else 'monthly'
                except (KeyError, IndexError):
                    ptype = 'monthly'
                
                if ptype == 'lump_sum':
                    interest_component = (loan['amount'] * loan['interest_rate_percent'] * loan['total_months']) / 100
                    principal_component = loan['amount']
                    new_balance = 0
                    status_update = "closed"
                else:
                    current_balance = loan['remaining_balance']
                    interest_rate = loan['interest_rate_percent']
                    interest_component = (current_balance * interest_rate) / 100
                    principal_component = proof['amount'] - interest_component
                    new_balance = current_balance - principal_component
                    status_update = "open"
                    if new_balance <= 1:
                        new_balance = 0
                        status_update = "closed"
                    
                # Update Loan
                if status_update == "closed":
                     execute_db("UPDATE loans SET remaining_balance=?, repayment_status='closed', closed_time=? WHERE loan_id=?", 
                                (new_balance, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), proof['loan_id']))
                else:
                     execute_db("UPDATE loans SET remaining_balance=? WHERE loan_id=?", 
                                (new_balance, proof['loan_id']))
                                
            # Log EMI payment
            execute_db("INSERT INTO interest_payments (loan_id, month_no, amount, status, paid_date) VALUES (?,?,?,?,?)",
                       (proof['loan_id'], proof['month_no'], proof['amount'], 'paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                       
        elif proof['proof_type'] == 'contribution':
             existing = query_db("SELECT id FROM monthly_contributions WHERE member_id=? AND month=? AND year=?",
                                 (proof['member_id'], proof['month'], proof['year']), one=True)
             if existing:
                 execute_db("UPDATE monthly_contributions SET status='paid', paid_date=? WHERE id=?",
                            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), existing['id']))
             else:
                 execute_db("INSERT INTO monthly_contributions (member_id, month, year, amount, status, paid_date) VALUES (?,?,?,?,?,?)",
                            (proof['member_id'], proof['month'], proof['year'], proof['amount'], 'paid', datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        
        execute_db("UPDATE payment_proofs SET status='approved', review_date=? WHERE proof_id=?", 
                   (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), proof_id))
        get_db().commit()
        flash("✅ Payment proof approved successfully.", "success")
        
    return redirect(url_for("admin.admin_payment_proofs"))

@admin_bp.route("/admin/reject_payment_proof/<int:proof_id>", methods=["POST"])
@admin_required
def reject_payment_proof(proof_id):
    admin_notes = request.form.get("admin_notes", "").strip()
    execute_db("UPDATE payment_proofs SET status='rejected', review_date=?, admin_notes=? WHERE proof_id=?", 
               (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), admin_notes, proof_id))
    get_db().commit()
    flash("ℹ️ Payment proof rejected.", "info")
    return redirect(url_for("admin.admin_payment_proofs"))

@admin_bp.route("/contribution_tracking")
@admin_required
def contribution_tracking():
    year = int(request.args.get("year", datetime.now().year))
    members = query_db("SELECT * FROM members WHERE role='member'")
    contributions = query_db("SELECT * FROM monthly_contributions WHERE year=?", (year,))
    
    # {member_id: {month: status}}
    status_map = {}
    for c in contributions:
        if c['member_id'] not in status_map: 
            status_map[c['member_id']] = {}
        status_map[c['member_id']][c['month']] = c['status']
        
    tracking_data = []
    for m in members:
        row = {'id': m['member_id'], 'name': m['name'], 'status_by_month': {}}
        for month in range(1, 13):
            status = status_map.get(m['member_id'], {}).get(month, 'pending')
            row['status_by_month'][month] = status
        tracking_data.append(row)
        
    return render_template("contribution_tracking.html", 
                         tracking_data=tracking_data, 
                         selected_year=year,
                         current_year=datetime.now().year)

@admin_bp.route("/admin/export_transactions")
@admin_required
def export_transactions():
    contributions = query_db("""SELECT m.name as Member, c.month as Month, c.year as Year, c.amount as Amount, 
                                  c.status as Status, c.paid_date as 'Paid Date'
                                  FROM monthly_contributions c 
                                  JOIN members m ON c.member_id = m.member_id
                                  ORDER BY c.year DESC, c.month DESC""")
                                  
    loan_payments = query_db("""SELECT m.name as Member, p.loan_id as 'Loan ID', p.month_no as 'Month No', 
                                  p.amount as Amount, p.status as Status, p.paid_date as 'Paid Date'
                                  FROM interest_payments p 
                                  JOIN loans l ON p.loan_id = l.loan_id
                                  JOIN members m ON l.member_id = m.member_id
                                  ORDER BY p.paid_date DESC""")
                                  
    loans_issued = query_db("""SELECT m.name as Member, l.loan_id as 'Loan ID', l.amount as Amount, 
                                 l.interest_rate_percent as 'Interest Rate', l.total_months as 'Total Months', 
                                 l.status as Status, l.repayment_status as 'Repayment Status', 
                                 l.request_time as 'Request Time', l.approved_time as 'Approved Time', 
                                 l.closed_time as 'Closed Time'
                                 FROM loans l 
                                 JOIN members m ON l.member_id = m.member_id
                                 ORDER BY l.request_time DESC""")
                                  
    df_contrib = pd.DataFrame([dict(row) for row in contributions])
    df_loans = pd.DataFrame([dict(row) for row in loan_payments])
    df_loans_issued = pd.DataFrame([dict(row) for row in loans_issued])
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if not df_contrib.empty:
            df_contrib.to_excel(writer, sheet_name='Contributions', index=False)
        else:
            pd.DataFrame({"Message": ["No Data"]}).to_excel(writer, sheet_name='Contributions', index=False)
            
        if not df_loans.empty:
            df_loans.to_excel(writer, sheet_name='Loan Payments', index=False)
        else:
            pd.DataFrame({"Message": ["No Data"]}).to_excel(writer, sheet_name='Loan Payments', index=False)
            
        if not df_loans_issued.empty:
            df_loans_issued.to_excel(writer, sheet_name='Loans Issued', index=False)
        else:
            pd.DataFrame({"Message": ["No Data"]}).to_excel(writer, sheet_name='Loans Issued', index=False)
            
    output.seek(0)
    filename = f"Transactions_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
