# Personal Finance Tracker

A dependency-free Python tool for tracking personal finances. Import bank-style CSV files, automatically categorize transactions with keyword rules, store everything in SQLite, and generate clean spending summaries or HTML reports — no external libraries required.

## Features

- **CSV import** — works with standard bank export formats (supports both single `amount` columns and separate `debit`/`credit` columns)
- **Automatic categorization** — keyword-based rules sort transactions into categories like Groceries, Dining, Housing, Utilities, and more
- **SQLite storage** — all transactions are stored locally, with duplicate detection on import
- **Text summaries** — quick income/spending breakdowns by category, filterable by month
- **HTML reports** — a polished, responsive report with spending bar charts and a full transaction table
- **Zero dependencies** — built entirely with the Python standard library

## Getting Started

### Requirements
- Python 3.10+

### Installation
Clone the repo and you're ready to go — no `pip install` needed:

```bash
git clone https://github.com/abuchibumbum-spec/personal-finance-tracker.git
cd personal-finance-tracker
```

## Usage

### 1. Generate sample data (optional)
```bash
python finance_tracker.py sample
```
Creates `sample_transactions.csv` with example transactions you can test the tool with.

### 2. Import transactions
```bash
python finance_tracker.py import sample_transactions.csv --account Checking
```
Add `--account` to label which account the transactions belong to. Run this for each CSV file you want to import — duplicates are automatically skipped.

### 3. View a summary
```bash
python finance_tracker.py summary
python finance_tracker.py summary --month 2026-06
```
Prints income, spending, net total, and a per-category breakdown to the terminal.

### 4. Generate an HTML report
```bash
python finance_tracker.py report
python finance_tracker.py report --month 2026-06
```
Creates `finance_report.html` — a visual report with category spending bars and a full transaction table. Open it in any browser.

## Customizing Categories

Edit `category_rules.csv` to change how transactions get categorized. Each row maps a keyword to a category:

```csv
keyword,category
grocery,Groceries
rent,Housing
```

Any transaction description containing the keyword (case-insensitive) gets matched to that category. Unmatched transactions fall into `Uncategorized`.

## CSV Format

Your bank CSV needs at minimum: a date column, a description (or `memo`/`name`) column, and either an `amount` column or separate `debit`/`credit` columns. Dates support `YYYY-MM-DD`, `MM/DD/YYYY`, `MM/DD/YY`, and `DD/MM/YYYY` formats.

## License

Feel free to use and adapt this project.
