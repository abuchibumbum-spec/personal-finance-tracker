# Personal Finance Tracker

A dependency-free Python tracker for importing bank CSVs, categorizing transactions, and generating spending summaries.

## CSV Format

Use columns like:

```csv
date,description,amount,account
2026-06-01,Payroll Deposit,3200.00,Checking
2026-06-02,Downtown Grocery Market,-82.45,Checking
```

The importer also understands `memo` or `name` instead of `description`, and `debit` / `credit` columns instead of `amount`.

## Commands

Create sample data:

```bash
python finance_tracker.py sample
```

Import a CSV:

```bash
python finance_tracker.py import sample_transactions.csv --account Checking
```

Print a summary:

```bash
python finance_tracker.py summary
python finance_tracker.py summary --month 2026-06
```

Generate an HTML report:

```bash
python finance_tracker.py report --output finance_report.html
```

## Categories

Categories are assigned from `category_rules.csv`. Edit that file to add your own keyword rules.
