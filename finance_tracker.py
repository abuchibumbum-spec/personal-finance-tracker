#!/usr/bin/env python3
"""A small dependency-free personal finance tracker.

Import bank-style CSV files, categorize transactions with simple rules,
store everything in SQLite, and generate spending summaries or an HTML report.
"""

from __future__ import annotations

import argparse
import csv
import html
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


APP_DIR = Path(__file__).resolve().parent
DEFAULT_DB = APP_DIR / "finance.db"
DEFAULT_RULES = APP_DIR / "category_rules.csv"
DEFAULT_REPORT = APP_DIR / "finance_report.html"


@dataclass(frozen=True)
class Transaction:
    date: str
    description: str
    amount: float
    category: str
    account: str


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT NOT NULL,
            account TEXT NOT NULL DEFAULT '',
            source_file TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(date, description, amount, account)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_date ON transactions(date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_transactions_category ON transactions(category)"
    )
    return conn


def ensure_default_rules(path: Path = DEFAULT_RULES) -> None:
    if path.exists():
        return

    rows = [
        ("keyword", "category"),
        ("grocery", "Groceries"),
        ("market", "Groceries"),
        ("restaurant", "Dining"),
        ("cafe", "Dining"),
        ("coffee", "Dining"),
        ("rent", "Housing"),
        ("mortgage", "Housing"),
        ("electric", "Utilities"),
        ("water", "Utilities"),
        ("internet", "Utilities"),
        ("phone", "Utilities"),
        ("gas", "Transportation"),
        ("uber", "Transportation"),
        ("lyft", "Transportation"),
        ("payroll", "Income"),
        ("salary", "Income"),
        ("transfer", "Transfer"),
        ("pharmacy", "Health"),
        ("doctor", "Health"),
        ("insurance", "Insurance"),
        ("amazon", "Shopping"),
        ("target", "Shopping"),
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(rows)


def load_rules(path: Path = DEFAULT_RULES) -> list[tuple[str, str]]:
    ensure_default_rules(path)
    with path.open(newline="", encoding="utf-8-sig") as file:
        return [
            (row["keyword"].strip().lower(), row["category"].strip())
            for row in csv.DictReader(file)
            if row.get("keyword") and row.get("category")
        ]


def categorize(description: str, rules: Iterable[tuple[str, str]]) -> str:
    text = description.lower()
    for keyword, category in rules:
        if keyword in text:
            return category
    return "Uncategorized"


def parse_amount(row: dict[str, str]) -> float:
    if row.get("amount"):
        return float(row["amount"].replace(",", "").replace("$", ""))

    debit = row.get("debit", "").replace(",", "").replace("$", "")
    credit = row.get("credit", "").replace(",", "").replace("$", "")
    if debit:
        return -abs(float(debit))
    if credit:
        return abs(float(credit))
    raise ValueError("CSV row needs amount, or debit/credit columns")


def normalize_date(value: str) -> str:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            pass
    raise ValueError(f"Unsupported date format: {value}")


def read_transactions(csv_path: Path, account: str, rules: list[tuple[str, str]]) -> list[Transaction]:
    transactions: list[Transaction] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as file:
        reader = csv.DictReader(file)
        normalized_fields = {name.lower().strip(): name for name in reader.fieldnames or []}

        for raw_row in reader:
            row = {
                normalized_key: raw_row[original_key].strip()
                for normalized_key, original_key in normalized_fields.items()
            }
            description = row.get("description") or row.get("memo") or row.get("name")
            if not description:
                raise ValueError("CSV needs a description, memo, or name column")

            amount = parse_amount(row)
            transactions.append(
                Transaction(
                    date=normalize_date(row["date"]),
                    description=description,
                    amount=amount,
                    category=row.get("category") or categorize(description, rules),
                    account=account,
                )
            )
    return transactions


def import_csv(csv_path: Path, account: str, db_path: Path = DEFAULT_DB) -> tuple[int, int]:
    rules = load_rules()
    transactions = read_transactions(csv_path, account, rules)
    conn = connect(db_path)
    inserted = 0
    skipped = 0
    with conn:
        for tx in transactions:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO transactions
                    (date, description, amount, category, account, source_file)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (tx.date, tx.description, tx.amount, tx.category, tx.account, csv_path.name),
            )
            if cursor.rowcount:
                inserted += 1
            else:
                skipped += 1
    conn.close()
    return inserted, skipped


def month_clause(month: str | None) -> tuple[str, tuple[str, ...]]:
    if not month:
        return "", ()
    return "WHERE substr(date, 1, 7) = ?", (month,)


def summary(db_path: Path = DEFAULT_DB, month: str | None = None) -> str:
    conn = connect(db_path)
    where, params = month_clause(month)
    rows = conn.execute(
        f"""
        SELECT category,
               ROUND(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 2) AS spent,
               ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2) AS income,
               COUNT(*) AS count
        FROM transactions
        {where}
        GROUP BY category
        ORDER BY spent DESC, income DESC
        """,
        params,
    ).fetchall()
    totals = conn.execute(
        f"""
        SELECT ROUND(SUM(CASE WHEN amount < 0 THEN -amount ELSE 0 END), 2),
               ROUND(SUM(CASE WHEN amount > 0 THEN amount ELSE 0 END), 2)
        FROM transactions
        {where}
        """,
        params,
    ).fetchone()
    conn.close()

    title = f"Summary for {month}" if month else "All-time summary"
    lines = [title, "=" * len(title)]
    income = totals[1] or 0
    spent = totals[0] or 0
    lines.append(f"Income: ${income:,.2f}")
    lines.append(f"Spending: ${spent:,.2f}")
    lines.append(f"Net: ${income - spent:,.2f}")
    lines.append("")
    lines.append(f"{'Category':<18} {'Spent':>12} {'Income':>12} {'Count':>7}")
    lines.append("-" * 53)
    for category, spent_value, income_value, count in rows:
        lines.append(
            f"{category:<18} ${spent_value or 0:>11,.2f} ${income_value or 0:>11,.2f} {count:>7}"
        )
    return "\n".join(lines)


def fetch_report_data(db_path: Path, month: str | None) -> tuple[list[sqlite3.Row], dict[str, float]]:
    conn = connect(db_path)
    conn.row_factory = sqlite3.Row
    where, params = month_clause(month)
    rows = conn.execute(
        f"""
        SELECT date, description, amount, category, account
        FROM transactions
        {where}
        ORDER BY date DESC, id DESC
        """,
        params,
    ).fetchall()
    totals = {
        "income": sum(row["amount"] for row in rows if row["amount"] > 0),
        "spent": sum(-row["amount"] for row in rows if row["amount"] < 0),
    }
    conn.close()
    return rows, totals


def category_spending(rows: Iterable[sqlite3.Row]) -> dict[str, float]:
    spending: dict[str, float] = defaultdict(float)
    for row in rows:
        if row["amount"] < 0:
            spending[row["category"]] += -row["amount"]
    return dict(sorted(spending.items(), key=lambda item: item[1], reverse=True))


def render_report(output_path: Path = DEFAULT_REPORT, db_path: Path = DEFAULT_DB, month: str | None = None) -> None:
    rows, totals = fetch_report_data(db_path, month)
    spending = category_spending(rows)
    max_spend = max(spending.values(), default=1)
    net = totals["income"] - totals["spent"]
    title = f"Finance Report - {month}" if month else "Finance Report"

    category_rows = "\n".join(
        f"""
        <div class="bar-row">
          <div class="bar-label">{html.escape(category)}</div>
          <div class="bar-track"><div class="bar-fill" style="width: {amount / max_spend * 100:.1f}%"></div></div>
          <div class="bar-value">${amount:,.2f}</div>
        </div>
        """
        for category, amount in spending.items()
    )
    transaction_rows = "\n".join(
        f"""
        <tr>
          <td>{html.escape(row['date'])}</td>
          <td>{html.escape(row['description'])}</td>
          <td>{html.escape(row['category'])}</td>
          <td>{html.escape(row['account'])}</td>
          <td class="amount {'income' if row['amount'] > 0 else 'expense'}">${row['amount']:,.2f}</td>
        </tr>
        """
        for row in rows
    )

    output_path.write_text(
        f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #1e2528;
      --muted: #657175;
      --line: #d8e0df;
      --paper: #f7f8f5;
      --panel: #ffffff;
      --accent: #1f7a6b;
      --accent-2: #315f93;
      --danger: #a04747;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      background: var(--paper);
      color: var(--ink);
    }}
    main {{
      width: min(1120px, calc(100% - 32px));
      margin: 32px auto;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      gap: 16px;
      align-items: end;
      border-bottom: 1px solid var(--line);
      padding-bottom: 18px;
    }}
    h1 {{
      margin: 0;
      font-size: 32px;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin-top: 6px;
      color: var(--muted);
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 12px;
      margin: 22px 0;
    }}
    .metric {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
    }}
    .metric span {{
      color: var(--muted);
      display: block;
      font-size: 13px;
      margin-bottom: 8px;
    }}
    .metric strong {{
      font-size: 24px;
      letter-spacing: 0;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 18px;
      margin-top: 16px;
    }}
    h2 {{
      margin: 0 0 14px;
      font-size: 18px;
      letter-spacing: 0;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: 150px 1fr 110px;
      gap: 12px;
      align-items: center;
      min-height: 32px;
    }}
    .bar-label, .bar-value {{ font-size: 14px; }}
    .bar-value {{ text-align: right; color: var(--muted); }}
    .bar-track {{
      height: 12px;
      background: #e9eeec;
      border-radius: 999px;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      border-radius: 999px;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      text-align: left;
      padding: 11px 8px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    th {{ color: var(--muted); font-weight: 700; }}
    .amount {{ text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }}
    .income {{ color: var(--accent); }}
    .expense {{ color: var(--danger); }}
    @media (max-width: 760px) {{
      header, .metrics {{ display: block; }}
      .metric {{ margin-top: 12px; }}
      .bar-row {{
        grid-template-columns: 1fr;
        gap: 6px;
        margin-bottom: 14px;
      }}
      .bar-value {{ text-align: left; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{html.escape(title)}</h1>
        <div class="subtitle">{len(rows)} transactions tracked</div>
      </div>
      <div class="subtitle">Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
    </header>

    <div class="metrics">
      <div class="metric"><span>Income</span><strong>${totals['income']:,.2f}</strong></div>
      <div class="metric"><span>Spending</span><strong>${totals['spent']:,.2f}</strong></div>
      <div class="metric"><span>Net</span><strong>${net:,.2f}</strong></div>
    </div>

    <section>
      <h2>Spending by Category</h2>
      {category_rows or '<p class="subtitle">No spending yet.</p>'}
    </section>

    <section>
      <h2>Transactions</h2>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Description</th>
            <th>Category</th>
            <th>Account</th>
            <th class="amount">Amount</th>
          </tr>
        </thead>
        <tbody>{transaction_rows}</tbody>
      </table>
    </section>
  </main>
</body>
</html>
""",
        encoding="utf-8",
    )


def create_sample(path: Path) -> None:
    rows = [
        ("date", "description", "amount", "account"),
        ("2026-06-01", "Payroll Deposit", "3200.00", "Checking"),
        ("2026-06-02", "Downtown Grocery Market", "-82.45", "Checking"),
        ("2026-06-03", "Rent Payment", "-1450.00", "Checking"),
        ("2026-06-04", "Coffee House", "-6.75", "Credit Card"),
        ("2026-06-05", "Electric Utility", "-94.30", "Checking"),
        ("2026-06-07", "Amazon Marketplace", "-43.19", "Credit Card"),
        ("2026-06-10", "Restaurant", "-58.20", "Credit Card"),
        ("2026-06-12", "Gas Station", "-39.50", "Credit Card"),
        ("2026-06-15", "Payroll Deposit", "3200.00", "Checking"),
        ("2026-06-18", "Internet Provider", "-72.99", "Checking"),
        ("2026-06-20", "Pharmacy", "-18.40", "Credit Card"),
        ("2026-06-24", "Target Store", "-112.10", "Credit Card"),
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as file:
        csv.writer(file).writerows(rows)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Track personal finances from CSV files.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    sample = subparsers.add_parser("sample", help="Create a sample transactions CSV.")
    sample.add_argument("--output", type=Path, default=APP_DIR / "sample_transactions.csv")

    import_cmd = subparsers.add_parser("import", help="Import a transaction CSV.")
    import_cmd.add_argument("csv_path", type=Path)
    import_cmd.add_argument("--account", default="Default")
    import_cmd.add_argument("--db", type=Path, default=DEFAULT_DB)

    summary_cmd = subparsers.add_parser("summary", help="Print an income/spending summary.")
    summary_cmd.add_argument("--month", help="Filter to YYYY-MM")
    summary_cmd.add_argument("--db", type=Path, default=DEFAULT_DB)

    report = subparsers.add_parser("report", help="Generate an HTML finance report.")
    report.add_argument("--month", help="Filter to YYYY-MM")
    report.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    report.add_argument("--db", type=Path, default=DEFAULT_DB)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "sample":
        create_sample(args.output)
        print(f"Sample CSV created: {args.output}")
    elif args.command == "import":
        inserted, skipped = import_csv(args.csv_path, args.account, args.db)
        print(f"Imported {inserted} transactions. Skipped {skipped} duplicates.")
    elif args.command == "summary":
        print(summary(args.db, args.month))
    elif args.command == "report":
        render_report(args.output, args.db, args.month)
        print(f"Report created: {args.output}")
    else:
        parser.error("Unknown command")


if __name__ == "__main__":
    main()
