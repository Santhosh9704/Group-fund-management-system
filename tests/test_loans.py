import pytest
from finance_app.utils.helpers import calculate_dynamic_emi
from finance_app.db import get_db, query_db, execute_db

def test_calculate_dynamic_emi():
    # Test Reducing Balance EMI calculations
    # Principal portion = 12000 / 12 = 1000 per month
    # Month 1 interest (1% of 12000) = 120
    emi_1 = calculate_dynamic_emi(12000, 12, 1, 1)
    assert emi_1["principal_component"] == 1000
    assert emi_1["interest_component"] == 120
    assert emi_1["total_emi"] == 1120
    assert emi_1["remaining_principal_start"] == 12000

    # Month 2 interest (1% of 11000) = 110
    emi_2 = calculate_dynamic_emi(12000, 12, 1, 2)
    assert emi_2["principal_component"] == 1000
    assert emi_2["interest_component"] == 110
    assert emi_2["total_emi"] == 1110
    assert emi_2["remaining_principal_start"] == 11000

    # Past duration limit
    assert calculate_dynamic_emi(12000, 12, 1, 13) is None

def test_admin_create_loan(client, auth, app):
    auth.login("admin", "testpass")
    
    # Create member to assign loan to
    with app.app_context():
        member = query_db("SELECT member_id FROM members WHERE username='member'", one=True)
        m_id = member["member_id"]
        
    response = client.post(
        "/admin/create_loan",
        data={
            "member_id": m_id,
            "amount": 10000,
            "months": 10,
            "interest_rate": 1.0,
            "payment_type": "monthly"
        }
    )
    assert response.status_code == 302
    
    with app.app_context():
        loan = query_db("SELECT * FROM loans WHERE member_id=?", (m_id,), one=True)
        assert loan is not None
        assert loan["amount"] == 10000
        assert loan["remaining_balance"] == 10000
        assert loan["payment_type"] == "monthly"

def test_update_interest_reducing_balance(client, auth, app):
    auth.login("admin", "testpass")
    
    with app.app_context():
        member = query_db("SELECT member_id FROM members WHERE username='member'", one=True)
        m_id = member["member_id"]
        # Insert a pre-approved monthly loan
        execute_db(
            """INSERT INTO loans (member_id, amount, interest_rate_percent, total_months, status, repayment_status, remaining_balance, principal_portion, payment_type)
               VALUES (?, 10000, 1.0, 10, 'approved', 'open', 10000, 1000, 'monthly')""",
            (m_id,)
        )
        get_db().commit()
        
        loan = query_db("SELECT loan_id FROM loans WHERE member_id=?", (m_id,), one=True)
        l_id = loan["loan_id"]
        
    # Pay first EMI (Interest = 100, Principal = 1000, Payment = 1100)
    # Remaining principal should become 9000
    response = client.post(
        "/update_interest",
        data={
            "loan_id": l_id,
            "month_no": 1,
            "amount": 1100
        }
    )
    assert response.status_code == 302
    
    with app.app_context():
        loan = query_db("SELECT * FROM loans WHERE loan_id=?", (l_id,), one=True)
        assert loan["remaining_balance"] == 9000
        assert loan["repayment_status"] == "open"
        
        payments = query_db("SELECT * FROM interest_payments WHERE loan_id=?", (l_id,))
        assert len(payments) == 1
        assert payments[0]["amount"] == 1100

def test_update_interest_lump_sum(client, auth, app):
    auth.login("admin", "testpass")
    
    with app.app_context():
        member = query_db("SELECT member_id FROM members WHERE username='member'", one=True)
        m_id = member["member_id"]
        # Insert a pre-approved lump-sum loan
        # Total interest = (10000 * 1% * 10) = 1000. Total payment expected = 11000
        execute_db(
            """INSERT INTO loans (member_id, amount, interest_rate_percent, total_months, status, repayment_status, remaining_balance, principal_portion, interest_portion, payment_type)
               VALUES (?, 10000, 1.0, 10, 'approved', 'open', 10000, 10000, 1000, 'lump_sum')""",
            (m_id,)
        )
        get_db().commit()
        
        loan = query_db("SELECT loan_id FROM loans WHERE member_id=?", (m_id,), one=True)
        l_id = loan["loan_id"]
        
    response = client.post(
        "/update_interest",
        data={
            "loan_id": l_id,
            "month_no": 1,
            "amount": 11000
        }
    )
    assert response.status_code == 302
    
    with app.app_context():
        loan = query_db("SELECT * FROM loans WHERE loan_id=?", (l_id,), one=True)
        assert loan["remaining_balance"] == 0
        assert loan["repayment_status"] == "closed"
