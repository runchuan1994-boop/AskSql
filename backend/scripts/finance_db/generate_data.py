#!/usr/bin/env python3
"""
金融测试数据库数据生成脚本
使用 Faker 生成零售银行风格的模拟数据，约 10 万行。
固定 seed=42 保证可重复生成。
"""

import os
import random
from datetime import datetime, timedelta
from decimal import Decimal

import psycopg2
from psycopg2.extras import execute_values
from faker import Faker

# ============================================================
# 配置
# ============================================================
SEED = 42
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "dbname": os.environ.get("DB_NAME", "finance_db"),
    "user": os.environ.get("DB_USER", "nl2sql"),
    "password": os.environ.get("DB_PASSWORD", "nl2sql123"),
}

# 数据量配置
NUM_BRANCHES = 20
NUM_EMPLOYEES = 200
NUM_CUSTOMERS = 5000
NUM_ACCOUNTS = 8000          # 每个客户平均 1.6 个账户
NUM_TRANSACTIONS = 80000     # 每个账户平均 10 笔交易
NUM_LOANS = 1200
NUM_LOAN_PAYMENTS = 15000
NUM_CREDIT_CARDS = 3000
NUM_PORTFOLIOS = 1500

# ============================================================
# 初始化
# ============================================================
fake = Faker("en_US")
Faker.seed(SEED)
random.seed(SEED)


def get_conn():
    return psycopg2.connect(**DB_CONFIG)


def print_progress(table: str, count: int):
    print(f"  ✓ {table}: {count} rows")


# ============================================================
# 1. 分支机构
# ============================================================
def generate_branches(cur) -> list[int]:
    cities = [
        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix",
        "Philadelphia", "San Antonio", "San Diego", "Dallas", "San Jose",
        "Austin", "Jacksonville", "Fort Worth", "Columbus", "Charlotte",
        "Indianapolis", "San Francisco", "Seattle", "Denver", "Washington",
    ]
    rows = []
    for i in range(NUM_BRANCHES):
        city = cities[i % len(cities)]
        rows.append((
            f"First Bank of {city} - {fake.street_suffix()} Branch",
            city,
            fake.street_address(),
            fake.phone_number()[:20],
            fake.date_between(start_date="-40y", end_date="-10y"),
        ))
    # page_size 设为总数 +1 确保单批执行，RETURNING 能返回所有 ID
    execute_values(
        cur,
        "INSERT INTO branches (name, city, address, phone, established_at) VALUES %s RETURNING branch_id",
        rows,
        page_size=len(rows) + 1,
    )
    ids = [r[0] for r in cur.fetchall()]
    print_progress("branches", len(ids))
    return ids


# ============================================================
# 2. 员工
# ============================================================
def generate_employees(cur, branch_ids: list[int]) -> list[int]:
    positions = ["manager", "teller", "loan_officer", "financial_advisor", "clerk"]
    position_weights = [0.08, 0.35, 0.15, 0.12, 0.30]
    salary_ranges = {
        "manager": (80000, 150000),
        "teller": (30000, 45000),
        "loan_officer": (50000, 90000),
        "financial_advisor": (60000, 120000),
        "clerk": (28000, 40000),
    }
    rows = []
    for i in range(NUM_EMPLOYEES):
        pos = random.choices(positions, weights=position_weights)[0]
        low, high = salary_ranges[pos]
        first = fake.first_name()
        last = fake.last_name()
        rows.append((
            random.choice(branch_ids),
            first,
            last,
            pos,
            f"{first.lower()}.{last.lower()}@firstbank.com"[:100],
            fake.phone_number()[:20],
            fake.date_between(start_date="-20y", end_date="-1y"),
            round(random.uniform(low, high), 2),
        ))
    execute_values(
        cur,
        "INSERT INTO employees (branch_id, first_name, last_name, position, email, phone, hire_date, salary) VALUES %s RETURNING emp_id",
        rows,
        page_size=len(rows) + 1,
    )
    ids = [r[0] for r in cur.fetchall()]
    print_progress("employees", len(ids))
    return ids


# ============================================================
# 3. 客户
# ============================================================
def generate_customers(cur) -> list[int]:
    occupations = [
        "Software Engineer", "Teacher", "Nurse", "Doctor", "Lawyer",
        "Accountant", "Marketing Manager", "Sales Representative",
        "Construction Worker", "Restaurant Manager", "Financial Analyst",
        "Graphic Designer", "Mechanical Engineer", "Pharmacist", "Dentist",
        "Real Estate Agent", "Pilot", "Police Officer", "Firefighter",
        "College Professor", "Freelance Writer", "Small Business Owner",
    ]
    rows = []
    for i in range(NUM_CUSTOMERS):
        first = fake.first_name()
        last = fake.last_name()
        dob = fake.date_of_birth(minimum_age=18, maximum_age=85)
        # SSN 脱敏：用随机数字生成后保持格式
        ssn = f"{random.randint(100,999)}-{random.randint(10,99)}-{random.randint(1000,9999)}"
        rows.append((
            first,
            last,
            f"{first.lower()}.{last.lower()}{random.randint(1,999)}@{fake.free_email_domain()}"[:100],
            fake.phone_number()[:20],
            ssn,
            fake.street_address()[:200],
            fake.city()[:50],
            fake.state_abbr(),
            fake.zipcode(),
            dob,
            random.choice(occupations),
            round(random.uniform(25000, 250000), 2),
            random.randint(350, 850),
            fake.date_time_between(start_date="-10y", end_date="now"),
        ))
    execute_values(
        cur,
        "INSERT INTO customers (first_name, last_name, email, phone, ssn, address, city, state, zip_code, date_of_birth, occupation, annual_income, risk_score, created_at) VALUES %s RETURNING customer_id",
        rows,
        page_size=len(rows) + 1,
    )
    ids = [r[0] for r in cur.fetchall()]
    print_progress("customers", len(ids))
    return ids


# ============================================================
# 4. 账户
# ============================================================
def generate_accounts(cur, customer_ids: list[int], branch_ids: list[int]) -> list[tuple[int, str, float]]:
    """返回 [(account_id, account_type, balance), ...]"""
    account_types = ["savings", "checking", "credit", "mortgage", "investment"]
    type_weights = [0.35, 0.35, 0.10, 0.05, 0.15]
    balance_ranges = {
        "savings": (100, 50000),
        "checking": (50, 25000),
        "credit": (-5000, 500),
        "mortgage": (-300000, -50000),
        "investment": (1000, 200000),
    }
    statuses = ["active", "active", "active", "active", "active", "frozen", "closed"]

    rows = []
    assigned = 0
    for cust_id in customer_ids:
        # 每个客户 1-3 个账户
        num_acc = random.choices([1, 2, 3], weights=[0.5, 0.35, 0.15])[0]
        if assigned + num_acc > NUM_ACCOUNTS:
            num_acc = NUM_ACCOUNTS - assigned
        if num_acc <= 0:
            break

        used_types = set()
        for _ in range(num_acc):
            # 尽量不重复类型
            available = [t for t in account_types if t not in used_types]
            if not available:
                available = account_types
            acct_type = random.choice(available)
            used_types.add(acct_type)

            low, high = balance_ranges[acct_type]
            balance = round(random.uniform(low, high), 2)
            status = random.choice(statuses)
            open_date = fake.date_between(start_date="-10y", end_date="-6m")
            close_date = fake.date_between(start_date=open_date, end_date="now") if status == "closed" else None

            account_num = f"{random.randint(1000000000, 9999999999)}"

            rows.append((
                cust_id,
                random.choice(branch_ids),
                account_num,
                acct_type,
                balance,
                "USD",
                status,
                open_date,
                close_date,
            ))
            assigned += 1

    # 如果还没够，补满
    while assigned < NUM_ACCOUNTS:
        cust_id = random.choice(customer_ids)
        acct_type = random.choices(account_types, weights=type_weights)[0]
        low, high = balance_ranges[acct_type]
        balance = round(random.uniform(low, high), 2)
        status = "active"
        open_date = fake.date_between(start_date="-10y", end_date="-6m")
        account_num = f"{random.randint(1000000000, 9999999999)}"
        rows.append((
            cust_id,
            random.choice(branch_ids),
            account_num,
            acct_type,
            balance,
            "USD",
            status,
            open_date,
            None,
        ))
        assigned += 1

    execute_values(
        cur,
        "INSERT INTO accounts (customer_id, branch_id, account_number, account_type, balance, currency, status, open_date, close_date) VALUES %s RETURNING account_id, account_type, balance",
        rows,
        page_size=len(rows) + 1,
    )
    results = [(r[0], r[1], float(r[2])) for r in cur.fetchall()]
    print_progress("accounts", len(results))
    return results


# ============================================================
# 5. 交易记录
# ============================================================
def generate_transactions(cur, account_list: list[tuple[int, str, float]]):
    """
    为每个账户生成交易记录，保证 balance_after 正确。
    """
    txn_types = ["deposit", "withdrawal", "transfer_in", "transfer_out", "fee", "interest", "payment"]
    channels = ["branch", "online", "mobile", "atm", "card", "auto"]
    channel_weights = [0.10, 0.30, 0.25, 0.15, 0.15, 0.05]

    # 每个账户的交易数量
    total_accounts = len(account_list)
    base_per_account = NUM_TRANSACTIONS // total_accounts
    remainder = NUM_TRANSACTIONS % total_accounts

    # 为每个账户计算交易类型权重（根据账户类型调整）
    def get_txn_weights(acct_type: str) -> list[float]:
        if acct_type in ("savings", "checking"):
            return [0.25, 0.25, 0.15, 0.15, 0.10, 0.05, 0.05]
        elif acct_type == "credit":
            return [0.05, 0.05, 0.10, 0.10, 0.10, 0.05, 0.55]  # payment 多
        else:
            return [0.20, 0.15, 0.15, 0.15, 0.15, 0.10, 0.10]

    all_rows = []
    txn_count = 0

    desc_map = {
        "deposit": lambda: f"{random.choice(['Cash deposit', 'Check deposit', 'Direct deposit', 'Mobile deposit', 'ACH deposit'])}",
        "withdrawal": lambda: f"{random.choice(['ATM withdrawal', 'Branch withdrawal', 'Check payment', 'Debit card purchase'])}",
        "transfer_in": lambda: f"Transfer from {random.choice(['external account', 'savings', 'checking', 'investment account'])}",
        "transfer_out": lambda: f"Transfer to {random.choice(['external account', 'savings', 'checking', 'investment account'])}",
        "fee": lambda: f"{random.choice(['Monthly maintenance fee', 'Overdraft fee', 'ATM fee', 'Wire transfer fee', 'Late payment fee'])}",
        "interest": lambda: f"Interest payment - {random.choice(['monthly', 'quarterly', 'annual'])}",
        "payment": lambda: f"Payment to {fake.company()[:50]}",
    }

    for idx, (acct_id, acct_type, current_balance) in enumerate(account_list):
        num_txns = base_per_account + (1 if idx < remainder else 0)
        if num_txns <= 0:
            continue

        weights = get_txn_weights(acct_type)

        # 生成交易时间（账户开户后到现在）
        start = fake.date_time_between(start_date="-5y", end_date="-1y")
        end = fake.date_time_between(start_date="-1y", end_date="now")
        txn_times = sorted([
            start + (end - start) * random.random()
            for _ in range(num_txns)
        ])

        target_balance = Decimal(str(current_balance))

        # 策略：从 0 开始生成交易，最后一笔调整为差值使余额匹配
        # 用 Decimal 避免浮点误差
        running = Decimal("0.00")
        amounts = []  # 带符号的 Decimal
        types_list = []

        for i in range(num_txns):
            # 最后一笔作为调整项
            if i == num_txns - 1 and num_txns > 1:
                # 让最后一笔把余额调整到目标值
                diff = float(target_balance - running)
                if abs(diff) < 0.01:
                    diff = 0.0
                ttype = random.choices(txn_types, weights=weights)[0]
                # 根据差值方向调整类型
                if diff >= 0:
                    ttype = random.choice(["deposit", "transfer_in", "interest"])
                else:
                    ttype = random.choice(["withdrawal", "transfer_out", "fee", "payment"])
                amt = Decimal(str(round(abs(diff), 2)))
                signed_amt = amt if diff >= 0 else -amt
            else:
                ttype = random.choices(txn_types, weights=weights)[0]
                if ttype in ("deposit", "transfer_in", "interest"):
                    if ttype == "interest":
                        amt = Decimal(str(round(random.uniform(1, 500), 2)))
                    else:
                        amt = Decimal(str(round(random.uniform(10, 5000), 2)))
                    signed_amt = amt
                elif ttype in ("withdrawal", "transfer_out", "fee", "payment"):
                    if ttype == "fee":
                        amt = Decimal(str(round(random.uniform(5, 100), 2)))
                    else:
                        amt = Decimal(str(round(random.uniform(10, 5000), 2)))
                    signed_amt = -amt
                else:
                    val = round(random.uniform(-5000, 5000), 2)
                    amt = Decimal(str(abs(val)))
                    signed_amt = Decimal(str(val))

            types_list.append(ttype)
            amounts.append(signed_amt)
            running += signed_amt

        # 确保最终余额精确等于 target_balance（处理舍入误差）
        final_diff = target_balance - running
        if abs(final_diff) > Decimal("0.001"):
            amounts[-1] += final_diff
            # 更新最后一笔的类型
            if amounts[-1] >= 0:
                types_list[-1] = "deposit" if types_list[-1] in ("deposit", "transfer_in", "interest") else types_list[-1]
            else:
                types_list[-1] = "withdrawal" if types_list[-1] in ("withdrawal", "transfer_out", "fee", "payment") else types_list[-1]
            running = target_balance

        # 生成记录（重新计算 running 确保精确）
        running = Decimal("0.00")
        for i in range(num_txns):
            running += amounts[i]
            running = running.quantize(Decimal("0.01"))
            all_rows.append((
                acct_id,
                types_list[i],
                float(abs(amounts[i])),
                float(running),
                desc_map[types_list[i]](),
                txn_times[i],
                random.choices(channels, weights=channel_weights)[0],
            ))
            txn_count += 1

    # 批量插入（分批次避免单次过大）
    batch_size = 10000
    for i in range(0, len(all_rows), batch_size):
        batch = all_rows[i:i + batch_size]
        execute_values(
            cur,
            "INSERT INTO transactions (account_id, txn_type, amount, balance_after, description, txn_time, channel) VALUES %s",
            batch,
        )

    print_progress("transactions", txn_count)
    return txn_count


# ============================================================
# 6. 贷款
# ============================================================
def generate_loans(cur, customer_ids: list[int], account_list: list[tuple[int, str, float]]) -> list[tuple[int, int, Decimal, str]]:
    """返回 [(loan_id, customer_id, monthly_payment, status), ...]"""
    loan_types = ["personal", "auto", "mortgage", "business", "student", "home_equity"]
    type_weights = [0.25, 0.20, 0.20, 0.10, 0.15, 0.10]

    amount_ranges = {
        "personal": (1000, 50000),
        "auto": (5000, 60000),
        "mortgage": (100000, 800000),
        "business": (10000, 500000),
        "student": (5000, 120000),
        "home_equity": (10000, 150000),
    }
    rate_ranges = {
        "personal": (6.0, 18.0),
        "auto": (3.0, 10.0),
        "mortgage": (2.5, 7.0),
        "business": (5.0, 15.0),
        "student": (3.0, 8.0),
        "home_equity": (3.5, 9.0),
    }
    term_options = {
        "personal": [12, 24, 36, 48, 60, 72],
        "auto": [24, 36, 48, 60, 72, 84],
        "mortgage": [180, 240, 300, 360],
        "business": [12, 24, 36, 60, 120],
        "student": [60, 120, 180, 240, 300],
        "home_equity": [60, 120, 180, 240],
    }
    statuses = ["active", "active", "active", "active", "paid_off", "defaulted", "pending"]
    status_weights = [0.45, 0.15, 0.10, 0.10, 0.10, 0.05, 0.05]

    # 选一些有 checking/savings 账户的客户关联贷款
    checking_accounts = [a for a in account_list if a[1] in ("checking", "savings")]

    rows = []
    for _ in range(NUM_LOANS):
        cust_id = random.choice(customer_ids)
        ltype = random.choices(loan_types, weights=type_weights)[0]
        low, high = amount_ranges[ltype]
        amount = round(random.uniform(low, high), 2)
        rate_low, rate_high = rate_ranges[ltype]
        rate = round(random.uniform(rate_low, rate_high), 3)
        term = random.choice(term_options[ltype])

        # 月供计算（等额本息）
        monthly_rate = rate / 100 / 12
        if monthly_rate > 0:
            monthly_payment = amount * (monthly_rate * (1 + monthly_rate) ** term) / ((1 + monthly_rate) ** term - 1)
        else:
            monthly_payment = amount / term
        monthly_payment = round(monthly_payment, 2)

        start_date = fake.date_between(start_date="-8y", end_date="-1m")
        end_date = start_date + timedelta(days=term * 30)
        status = random.choices(statuses, weights=status_weights)[0]

        # 30% 的贷款关联到一个账户
        acct_id = random.choice(checking_accounts)[0] if random.random() < 0.3 else None

        rows.append((
            cust_id,
            acct_id,
            ltype,
            amount,
            rate,
            term,
            monthly_payment,
            start_date,
            end_date,
            status,
        ))

    execute_values(
        cur,
        "INSERT INTO loans (customer_id, account_id, loan_type, amount, interest_rate, term_months, monthly_payment, start_date, end_date, status) VALUES %s RETURNING loan_id, customer_id, monthly_payment, status",
        rows,
        page_size=len(rows) + 1,
    )
    results = [(r[0], r[1], r[2], r[3]) for r in cur.fetchall()]
    print_progress("loans", len(results))
    return results


# ============================================================
# 7. 贷款还款记录
# ============================================================
def generate_loan_payments(cur, loan_list: list[tuple[int, int, Decimal, str]]):
    payment_methods = ["auto_debit", "manual", "transfer", "check", "cash"]
    method_weights = [0.45, 0.25, 0.15, 0.10, 0.05]

    all_rows = []
    total_payments = 0

    # 先获取所有贷款的 start_date，避免循环中逐笔查询
    cur.execute("SELECT loan_id, start_date, term_months, status FROM loans")
    loan_info = {row[0]: (row[1], row[2], row[3]) for row in cur.fetchall()}

    # 给每笔贷款生成还款记录
    for loan_id, cust_id, monthly_payment, status in loan_list:
        if status == "pending" or status == "rejected":
            continue

        start_date, term_months, _ = loan_info.get(loan_id, (None, None, None))
        if start_date is None:
            continue

        # 已还期数（目标平均 12-13 期/笔，总数 ~15000）
        if status == "active":
            # 已还 3-36 期（大部分）
            num_paid = random.randint(3, 36)
        elif status == "paid_off":
            # 已还清：用完整期限，但上限 60 期避免太多
            num_paid = min(term_months, random.randint(24, 60))
        elif status == "defaulted":
            # 违约：还了一部分后断供
            num_paid = random.randint(3, 24)
        else:
            num_paid = 0

        if total_payments + num_paid > NUM_LOAN_PAYMENTS:
            num_paid = max(0, NUM_LOAN_PAYMENTS - total_payments)
        if num_paid <= 0:
            continue

        for mo in range(1, num_paid + 1):
            pay_date = start_date + timedelta(days=mo * 30)

            # 本金和利息分配（简化：早期利息多，后期本金多）
            ratio = min(1.0, mo / max(1, num_paid))
            principal_part = round(float(monthly_payment) * (0.3 + 0.5 * ratio), 2)
            interest_part = round(float(monthly_payment) - principal_part, 2)

            # 状态：大部分已还，少量逾期或未还
            if status == "defaulted" and mo == num_paid:
                pay_status = "missed"
            elif random.random() < 0.05:
                pay_status = "late"
            else:
                pay_status = "paid"

            all_rows.append((
                loan_id,
                pay_date,
                float(monthly_payment),
                principal_part,
                interest_part,
                random.choices(payment_methods, weights=method_weights)[0],
                pay_status,
            ))
            total_payments += 1

        if total_payments >= NUM_LOAN_PAYMENTS:
            break

    # 批量插入
    batch_size = 5000
    for i in range(0, len(all_rows), batch_size):
        batch = all_rows[i:i + batch_size]
        execute_values(
            cur,
            "INSERT INTO loan_payments (loan_id, payment_date, amount, principal_part, interest_part, payment_method, status) VALUES %s",
            batch,
        )

    print_progress("loan_payments", total_payments)


# ============================================================
# 8. 信用卡
# ============================================================
def generate_credit_cards(cur, customer_ids: list[int], account_list: list[tuple[int, str, float]]):
    card_types = ["visa", "mastercard", "amex", "discover"]
    card_weights = [0.45, 0.35, 0.12, 0.08]

    credit_limits = [500, 1000, 2000, 5000, 10000, 15000, 20000, 30000, 50000]
    limit_weights = [0.05, 0.10, 0.15, 0.20, 0.15, 0.12, 0.10, 0.08, 0.05]

    statuses = ["active", "active", "active", "active", "blocked", "expired", "cancelled"]

    # 找 credit 类型账户
    credit_accounts = [a for a in account_list if a[1] == "credit"]

    rows = []
    for i in range(NUM_CREDIT_CARDS):
        cust_id = random.choice(customer_ids)
        ctype = random.choices(card_types, weights=card_weights)[0]
        limit = random.choices(credit_limits, weights=limit_weights)[0]
        balance = round(random.uniform(0, limit * 0.9), 2)
        min_pay = round(max(25, balance * 0.03), 2)
        status = random.choice(statuses)

        issued = fake.date_between(start_date="-6y", end_date="-1y")
        expiry = issued + timedelta(days=365 * random.randint(3, 5))
        due_date = fake.date_between(start_date="-10d", end_date="+20d")

        # 卡号脱敏
        last4 = f"{random.randint(1000, 9999)}"
        card_num = f"XXXX-XXXX-XXXX-{last4}"

        # 关联到 credit 账户（如果有）
        acct_id = None
        if credit_accounts and random.random() < 0.6:
            acct_id = random.choice(credit_accounts)[0]

        rows.append((
            cust_id,
            acct_id,
            card_num,
            ctype,
            limit,
            balance,
            min_pay,
            due_date if status == "active" else None,
            status,
            issued,
            expiry,
        ))

    execute_values(
        cur,
        "INSERT INTO credit_cards (customer_id, account_id, card_number, card_type, credit_limit, current_balance, min_payment, payment_due_date, status, issued_date, expiry_date) VALUES %s",
        rows,
    )
    print_progress("credit_cards", len(rows))


# ============================================================
# 9. 投资组合
# ============================================================
def generate_portfolios(cur, customer_ids: list[int], account_list: list[tuple[int, str, float]]):
    portfolio_types = ["retirement", "brokerage", "robo_advisor", "ira", "401k"]
    type_weights = [0.25, 0.20, 0.20, 0.15, 0.20]

    risk_levels = ["low", "medium", "high", "conservative", "aggressive"]
    risk_weights = [0.15, 0.40, 0.15, 0.20, 0.10]

    value_ranges = {
        "retirement": (10000, 500000),
        "brokerage": (5000, 300000),
        "robo_advisor": (1000, 100000),
        "ira": (5000, 250000),
        "401k": (10000, 400000),
    }

    # 找 investment 类型账户
    inv_accounts = [a for a in account_list if a[1] == "investment"]

    rows = []
    for _ in range(NUM_PORTFOLIOS):
        cust_id = random.choice(customer_ids)
        ptype = random.choices(portfolio_types, weights=type_weights)[0]
        low, high = value_ranges[ptype]
        value = round(random.uniform(low, high), 2)
        risk = random.choices(risk_levels, weights=risk_weights)[0]

        acct_id = None
        if inv_accounts and random.random() < 0.7:
            acct_id = random.choice(inv_accounts)[0]

        rows.append((
            cust_id,
            acct_id,
            ptype,
            value,
            risk,
            fake.date_time_between(start_date="-8y", end_date="-3m"),
        ))

    execute_values(
        cur,
        "INSERT INTO investment_portfolios (customer_id, account_id, portfolio_type, total_value, risk_level, created_at) VALUES %s",
        rows,
    )
    print_progress("investment_portfolios", len(rows))


# ============================================================
# 主流程
# ============================================================
def main():
    print("=" * 60)
    print("金融测试数据库数据生成")
    print(f"目标数据量: ~{NUM_TRANSACTIONS + NUM_CUSTOMERS + NUM_ACCOUNTS + NUM_LOANS + NUM_LOAN_PAYMENTS + NUM_CREDIT_CARDS + NUM_PORTFOLIOS + NUM_BRANCHES + NUM_EMPLOYEES:,} 行")
    print("=" * 60)

    conn = get_conn()
    cur = conn.cursor()

    try:
        print("\n[1/9] 生成分支机构数据...")
        branch_ids = generate_branches(cur)
        conn.commit()

        print("\n[2/9] 生成员工数据...")
        generate_employees(cur, branch_ids)
        conn.commit()

        print("\n[3/9] 生成客户数据...")
        customer_ids = generate_customers(cur)
        conn.commit()

        print("\n[4/9] 生成账户数据...")
        account_list = generate_accounts(cur, customer_ids, branch_ids)
        conn.commit()

        print("\n[5/9] 生成交易记录数据...")
        generate_transactions(cur, account_list)
        conn.commit()

        print("\n[6/9] 生成贷款数据...")
        loan_list = generate_loans(cur, customer_ids, account_list)
        conn.commit()

        print("\n[7/9] 生成贷款还款记录...")
        generate_loan_payments(cur, loan_list)
        conn.commit()

        print("\n[8/9] 生成信用卡数据...")
        generate_credit_cards(cur, customer_ids, account_list)
        conn.commit()

        print("\n[9/9] 生成投资组合数据...")
        generate_portfolios(cur, customer_ids, account_list)
        conn.commit()

        # ============================================================
        # 验证
        # ============================================================
        print("\n" + "=" * 60)
        print("数据生成完成！验证统计：")
        print("=" * 60)

        tables = [
            "branches", "employees", "customers", "accounts",
            "transactions", "loans", "loan_payments", "credit_cards",
            "investment_portfolios",
        ]
        total = 0
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            count = cur.fetchone()[0]
            total += count
            print(f"  {t:25s} {count:>10,} 行")

        print(f"\n  {'总计':25s} {total:>10,} 行")

        # 几个抽样验证
        print("\n--- 抽样验证 ---")

        cur.execute("""
            SELECT a.account_id, a.balance, t.balance_after
            FROM accounts a
            JOIN transactions t ON t.account_id = a.account_id
            WHERE a.status = 'active' AND a.account_type IN ('savings','checking')
            ORDER BY t.txn_time DESC
            LIMIT 5
        """)
        mismatches = 0
        for acct_id, acc_bal, last_bal in cur.fetchall():
            if abs(float(acc_bal) - float(last_bal)) > 0.02:
                mismatches += 1
        print(f"  交易余额一致性抽查: {'通过' if mismatches == 0 else f'{mismatches} 个不匹配'}")

        cur.execute("SELECT COUNT(*) FROM customers WHERE email LIKE '%@%'")
        print(f"  有效邮箱客户数: {cur.fetchone()[0]:,}")

        cur.execute("SELECT SUM(balance) FROM accounts WHERE status = 'active'")
        total_balance = cur.fetchone()[0]
        print(f"  活跃账户总余额: ${total_balance:,.2f}")

        cur.execute("SELECT SUM(amount) FROM loans WHERE status = 'active'")
        total_loans = cur.fetchone()[0]
        print(f"  活跃贷款总额: ${total_loans:,.2f}")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ 错误: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
