-- ============================================================
-- 金融测试数据库 Schema (PostgreSQL)
-- 零售银行核心业务：分支机构、客户、账户、交易、贷款、信用卡、投资
-- ============================================================

-- 启用 pgcrypto 扩展（用于生成 UUID 等，可选）
-- CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================
-- 1. 银行分支机构
-- ============================================================
CREATE TABLE IF NOT EXISTS branches (
    branch_id       SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL,
    city            VARCHAR(50) NOT NULL,
    address         VARCHAR(200),
    phone           VARCHAR(20),
    established_at  DATE NOT NULL
);

COMMENT ON TABLE  branches IS '银行分支机构';
COMMENT ON COLUMN branches.name IS '网点名称';
COMMENT ON COLUMN branches.city IS '所在城市';

-- ============================================================
-- 2. 员工
-- ============================================================
CREATE TABLE IF NOT EXISTS employees (
    emp_id      SERIAL PRIMARY KEY,
    branch_id   INTEGER NOT NULL REFERENCES branches(branch_id),
    first_name  VARCHAR(50) NOT NULL,
    last_name   VARCHAR(50) NOT NULL,
    position    VARCHAR(30) NOT NULL CHECK (position IN ('manager', 'teller', 'loan_officer', 'financial_advisor', 'clerk')),
    email       VARCHAR(100) UNIQUE,
    phone       VARCHAR(20),
    hire_date   DATE NOT NULL,
    salary      NUMERIC(10, 2) NOT NULL
);

COMMENT ON TABLE  employees IS '银行员工';
COMMENT ON COLUMN employees.position IS '职位: manager/teller/loan_officer/financial_advisor/clerk';

CREATE INDEX IF NOT EXISTS idx_employees_branch ON employees(branch_id);
CREATE INDEX IF NOT EXISTS idx_employees_position ON employees(position);

-- ============================================================
-- 3. 客户
-- ============================================================
CREATE TABLE IF NOT EXISTS customers (
    customer_id   SERIAL PRIMARY KEY,
    first_name    VARCHAR(50) NOT NULL,
    last_name     VARCHAR(50) NOT NULL,
    email         VARCHAR(100) UNIQUE,
    phone         VARCHAR(20),
    ssn           VARCHAR(11),
    address       VARCHAR(200),
    city          VARCHAR(50),
    state         VARCHAR(2),
    zip_code      VARCHAR(10),
    date_of_birth DATE NOT NULL,
    occupation    VARCHAR(50),
    annual_income NUMERIC(12, 2),
    risk_score    INTEGER CHECK (risk_score BETWEEN 300 AND 850),
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE  customers IS '银行客户';
COMMENT ON COLUMN customers.ssn IS '社会安全号码（脱敏格式 xxx-xx-xxxx）';
COMMENT ON COLUMN customers.risk_score IS '信用评分 300-850';

CREATE INDEX IF NOT EXISTS idx_customers_city ON customers(city);
CREATE INDEX IF NOT EXISTS idx_customers_last_name ON customers(last_name);
CREATE INDEX IF NOT EXISTS idx_customers_risk_score ON customers(risk_score);

-- ============================================================
-- 4. 银行账户
-- ============================================================
CREATE TABLE IF NOT EXISTS accounts (
    account_id     SERIAL PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    branch_id      INTEGER NOT NULL REFERENCES branches(branch_id),
    account_number VARCHAR(20) UNIQUE NOT NULL,
    account_type   VARCHAR(20) NOT NULL CHECK (account_type IN ('savings', 'checking', 'credit', 'mortgage', 'investment')),
    balance        NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    currency       VARCHAR(3) NOT NULL DEFAULT 'USD',
    status         VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'frozen', 'closed')),
    open_date      DATE NOT NULL,
    close_date     DATE
);

COMMENT ON TABLE  accounts IS '银行账户';
COMMENT ON COLUMN accounts.account_type IS '账户类型: savings/checking/credit/mortgage/investment';
COMMENT ON COLUMN accounts.status IS '账户状态: active/frozen/closed';

CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts(customer_id);
CREATE INDEX IF NOT EXISTS idx_accounts_branch ON accounts(branch_id);
CREATE INDEX IF NOT EXISTS idx_accounts_type ON accounts(account_type);
CREATE INDEX IF NOT EXISTS idx_accounts_status ON accounts(status);

-- ============================================================
-- 5. 交易记录
-- ============================================================
CREATE TABLE IF NOT EXISTS transactions (
    txn_id        BIGSERIAL PRIMARY KEY,
    account_id    INTEGER NOT NULL REFERENCES accounts(account_id),
    txn_type      VARCHAR(15) NOT NULL CHECK (txn_type IN ('deposit', 'withdrawal', 'transfer_in', 'transfer_out', 'fee', 'interest', 'payment')),
    amount        NUMERIC(15, 2) NOT NULL,
    balance_after NUMERIC(15, 2) NOT NULL,
    description   VARCHAR(200),
    txn_time      TIMESTAMP NOT NULL,
    channel       VARCHAR(15) NOT NULL CHECK (channel IN ('branch', 'online', 'mobile', 'atm', 'card', 'auto'))
);

COMMENT ON TABLE  transactions IS '账户交易记录';
COMMENT ON COLUMN transactions.txn_type IS '交易类型: deposit/withdrawal/transfer_in/transfer_out/fee/interest/payment';
COMMENT ON COLUMN transactions.channel IS '交易渠道: branch/online/mobile/atm/card/auto';
COMMENT ON COLUMN transactions.balance_after IS '交易后账户余额';

CREATE INDEX IF NOT EXISTS idx_transactions_account ON transactions(account_id);
CREATE INDEX IF NOT EXISTS idx_transactions_time ON transactions(txn_time);
CREATE INDEX IF NOT EXISTS idx_transactions_type ON transactions(txn_type);
CREATE INDEX IF NOT EXISTS idx_transactions_account_time ON transactions(account_id, txn_time);

-- ============================================================
-- 6. 贷款
-- ============================================================
CREATE TABLE IF NOT EXISTS loans (
    loan_id        SERIAL PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    account_id     INTEGER REFERENCES accounts(account_id),
    loan_type      VARCHAR(20) NOT NULL CHECK (loan_type IN ('personal', 'auto', 'mortgage', 'business', 'student', 'home_equity')),
    amount         NUMERIC(15, 2) NOT NULL,
    interest_rate  NUMERIC(5, 3) NOT NULL,
    term_months    INTEGER NOT NULL,
    monthly_payment NUMERIC(12, 2) NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    status         VARCHAR(15) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paid_off', 'defaulted', 'pending', 'rejected'))
);

COMMENT ON TABLE  loans IS '贷款';
COMMENT ON COLUMN loans.loan_type IS '贷款类型: personal/auto/mortgage/business/student/home_equity';
COMMENT ON COLUMN loans.status IS '贷款状态: active/paid_off/defaulted/pending/rejected';

CREATE INDEX IF NOT EXISTS idx_loans_customer ON loans(customer_id);
CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status);
CREATE INDEX IF NOT EXISTS idx_loans_type ON loans(loan_type);
CREATE INDEX IF NOT EXISTS idx_loans_start_date ON loans(start_date);

-- ============================================================
-- 7. 贷款还款记录
-- ============================================================
CREATE TABLE IF NOT EXISTS loan_payments (
    payment_id     BIGSERIAL PRIMARY KEY,
    loan_id        INTEGER NOT NULL REFERENCES loans(loan_id),
    payment_date   DATE NOT NULL,
    amount         NUMERIC(12, 2) NOT NULL,
    principal_part NUMERIC(12, 2) NOT NULL,
    interest_part  NUMERIC(12, 2) NOT NULL,
    payment_method VARCHAR(15) NOT NULL CHECK (payment_method IN ('auto_debit', 'manual', 'transfer', 'check', 'cash')),
    status         VARCHAR(10) NOT NULL DEFAULT 'paid' CHECK (status IN ('paid', 'late', 'missed', 'pending'))
);

COMMENT ON TABLE  loan_payments IS '贷款还款记录';
COMMENT ON COLUMN loan_payments.status IS '还款状态: paid/late/missed/pending';

CREATE INDEX IF NOT EXISTS idx_loan_payments_loan ON loan_payments(loan_id);
CREATE INDEX IF NOT EXISTS idx_loan_payments_date ON loan_payments(payment_date);
CREATE INDEX IF NOT EXISTS idx_loan_payments_status ON loan_payments(status);

-- ============================================================
-- 8. 信用卡
-- ============================================================
CREATE TABLE IF NOT EXISTS credit_cards (
    card_id         SERIAL PRIMARY KEY,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    account_id      INTEGER REFERENCES accounts(account_id),
    card_number     VARCHAR(19) NOT NULL,
    card_type       VARCHAR(15) NOT NULL CHECK (card_type IN ('visa', 'mastercard', 'amex', 'discover')),
    credit_limit    NUMERIC(12, 2) NOT NULL,
    current_balance NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    min_payment     NUMERIC(10, 2),
    payment_due_date DATE,
    status          VARCHAR(10) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'blocked', 'expired', 'cancelled')),
    issued_date     DATE NOT NULL,
    expiry_date     DATE NOT NULL
);

COMMENT ON TABLE  credit_cards IS '信用卡';
COMMENT ON COLUMN credit_cards.card_number IS '卡号（脱敏: XXXX-XXXX-XXXX-1234）';

CREATE INDEX IF NOT EXISTS idx_credit_cards_customer ON credit_cards(customer_id);
CREATE INDEX IF NOT EXISTS idx_credit_cards_status ON credit_cards(status);
CREATE INDEX IF NOT EXISTS idx_credit_cards_type ON credit_cards(card_type);

-- ============================================================
-- 9. 投资组合
-- ============================================================
CREATE TABLE IF NOT EXISTS investment_portfolios (
    portfolio_id   SERIAL PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    account_id     INTEGER REFERENCES accounts(account_id),
    portfolio_type VARCHAR(20) NOT NULL CHECK (portfolio_type IN ('retirement', 'brokerage', 'robo_advisor', 'ira', '401k')),
    total_value    NUMERIC(15, 2) NOT NULL DEFAULT 0.00,
    risk_level     VARCHAR(15) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'conservative', 'aggressive')),
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE  investment_portfolios IS '投资组合';
COMMENT ON COLUMN investment_portfolios.portfolio_type IS '组合类型: retirement/brokerage/robo_advisor/ira/401k';
COMMENT ON COLUMN investment_portfolios.risk_level IS '风险等级: low/medium/high/conservative/aggressive';

CREATE INDEX IF NOT EXISTS idx_portfolios_customer ON investment_portfolios(customer_id);
CREATE INDEX IF NOT EXISTS idx_portfolios_type ON investment_portfolios(portfolio_type);
CREATE INDEX IF NOT EXISTS idx_portfolios_risk ON investment_portfolios(risk_level);
