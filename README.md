# StockWise Solutions

## CAA900 Capstone Project

## Team Members

- Clement Okonkwo (GitHub: Emes101)
- Halimat Oluwatosin Aminu (GitHub: Halimatcd)

## OPC Persona

Michael Chen is the owner of a small retail store that sells electronics, mobile accessories, and office supplies.

### What They Sell

- Electronics
- Mobile accessories
- Office supplies
- Computer peripherals

### How They Work Today

The business currently tracks inventory, sales, and stock levels using spreadsheets and manual record-keeping. Employees manually update inventory counts, which often leads to stock discrepancies and delays.

## Pain Point

"I never know exactly what products are running low until customers ask for them. Managing inventory manually takes too much time and causes costly mistakes."

## User Roles

### Owner

Manages inventory, suppliers, products, sales, and reporting.

### Employee

Updates stock levels, records sales, and checks product availability.

## Solution

Develop a cloud-based inventory management system that enables small businesses to track products, monitor stock levels, manage inventory, and generate reports through a centralized online dashboard.

## Success Measure

- Reduce inventory tracking errors by at least 50%.
- Provide real-time visibility into stock levels.
- Reduce the time required to locate inventory information.

## Platform

Microsoft Azure

## Repository

Capstone Project - CAA900NCE

## How to run the app

### What you need
- Python 3.11 or 3.12
- Git
- Azure CLI (only to deploy)

### 1. Get the code
```bash
git clone https://github.com/Emes101/Capstone-Project-CAA900NCE.git
cd Capstone-Project-CAA900NCE
```

### 2. Set up Python (first time only)

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt pytest
```

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r app/requirements.txt pytest
```

Each time you open a new terminal, turn the environment on again (`source .venv/bin/activate` or `.venv\Scripts\Activate.ps1`). The prompt shows `(.venv)` when it is on.

### 3. Run the tests
```bash
python -m pytest
```
All 17 tests should pass.

### 4. Start the app
```bash
cd app
python -m flask --app app run --port 5001 --debug
```

| Page | Address | Who uses it |
|---|---|---|
| Customer view | http://127.0.0.1:5001/ | Customers check what is in stock |
| Owner dashboard | http://127.0.0.1:5001/owner | Michael records sales and restocks (access code required) |

Press **Ctrl+C** to stop the app.

> **Note:** The app uses sample data kept in memory, so stock changes reset when the app restarts. A database is added in Progress Submission 3.

### 5. Deploy to Azure (subscription owner only)
```bash
az login
az account set --subscription "Azure for Students"
bash scripts/deploy.sh        # Windows: .\scripts\deploy.ps1
```
The script creates the resource group `caa900-stockwise-rg`, deploys the infrastructure from `infra/main.bicep`, uploads the app and prints the public links.

Then set the two app settings once (never commit these values):
```bash
az webapp config appsettings set -g caa900-stockwise-rg -n <web app name> \
  --settings FLASK_SECRET_KEY=<long random value> OWNER_ACCESS_CODE=<owner code>
```

See [docs/BUILD-GUIDE.md](docs/BUILD-GUIDE.md) for full details and troubleshooting.
