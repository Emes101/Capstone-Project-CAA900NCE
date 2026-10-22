# StockWise Solutions: Build Guide (Progress Submission 2)

This guide explains how we build, test and deploy the first version of StockWise. By the end, our website will be live on Azure App Service with the **customer view** and the **owner view**, which is what Progress Submission 2 (due October 5) requires.

At this stage the app uses **sample data** kept in memory. The Azure SQL database, owner sign-in and email alerts are added in Progress Submission 3 and 4.

---

## 1. What is in the project

```
.
├── app/                      The web application (this folder is what we deploy)
│   ├── app.py                Web pages and API routes (Flask)
│   ├── inventory.py          Stock rules: status, sales, restocks, never below zero
│   ├── requirements.txt      Python packages Azure installs for us
│   ├── data/
│   │   └── sample_products.json   12 sample products (synthetic data)
│   ├── templates/            HTML pages
│   │   ├── base.html         Shared layout: header, menu, messages, footer
│   │   ├── customer.html     Customer view: search and units in stock
│   │   ├── owner_login.html  Owner access code page
│   │   └── owner.html        Owner view: totals, reorder list, sell and restock
│   └── static/
│       └── style.css         Page styling
├── infra/
│   └── main.bicep            Azure resources as code: App Service plan + web app
├── scripts/
│   ├── deploy.ps1            One-command deploy for Windows PowerShell
│   └── deploy.sh             One-command deploy for macOS, Linux or Git Bash
├── tests/
│   ├── test_inventory.py     Automated tests for the stock rules
│   └── test_owner_access.py  Automated tests for the owner access code
├── docs/
│   └── BUILD-GUIDE.md        This guide
└── .gitignore                Keeps secrets, virtual environments and zips out of Git
```

### What each part does

| File | What it does | Why it matters for marking |
|---|---|---|
| `app/inventory.py` | Holds the business rules. A sale can never take stock below zero, and a lock makes sure two sales of the last item cannot both succeed. | Shows we solved the pain point properly, not just drew pages. |
| `app/app.py` | Connects web addresses to pages: `/` (customer), `/owner` (owner), `/api/products`, `/api/health`. | The API is the start of our backend for Submission 3. |
| `customer.html` | Customers search and see the **number of units in stock** and a status (In stock / Low stock / Out of stock). | Suppliers and reorder levels stay owner-only. |
| `owner_login.html` | The owner enters an access code before the dashboard opens. Selling and restocking are blocked without it. | A simple access control until Entra External ID sign-in in Submission 3. |
| `owner.html` | Michael sees totals, a reorder list with suppliers, and can record sales and restocks. | Our owner view for Submission 2. |
| `infra/main.bicep` | Creates the App Service plan and web app from code, with tags, HTTPS only, TLS 1.2 and FTP turned off. | Infrastructure as code, named and tagged resources, secure defaults. |
| `tests/` | Seventeen automated tests: stock rules and the owner access code. | Evidence of quality; later run automatically by GitHub Actions. |

No secrets are stored in the code. The one secret the app uses (`FLASK_SECRET_KEY`) is read from an App Service setting.

---

## 2. Install the tools (once per laptop)

Both team members need these:

| Tool | Get it from | Check it works |
|---|---|---|
| Visual Studio Code | code.visualstudio.com | Opens normally |
| Git | git-scm.com | `git --version` |
| Python 3.12 | python.org (tick **Add Python to PATH** on Windows) | `python --version` |
| Azure CLI | learn.microsoft.com/cli/azure/install-azure-cli | `az --version` |
| Bicep | Run `az bicep install` | `az bicep version` |

Useful VS Code extensions: **Python**, **Bicep** and **Azure App Service**.

---

## 3. Add the code to our repository

We never push straight to `main`. Every change goes through a pull request.

```bash
git clone https://github.com/Emes101/Capstone-Project-CAA900NCE.git
cd Capstone-Project-CAA900NCE
git checkout -b feature/starter-app
```

Copy the starter files into the repository folder (keep our existing `README.md`), then:

```bash
git add .
git commit -m "Add starter Flask app, Bicep template and tests"
git push -u origin feature/starter-app
```

On GitHub, open a pull request. The other member reviews it and clicks **Merge**.

Suggested split, so both of us have commits:

- **Halimat:** customer and owner pages (`templates/`, `static/`), sample data.
- **Clement:** `infra/main.bicep`, `scripts/`, deployment to Azure.

---

## 4. Run the app on your laptop

**Windows (PowerShell):**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r app/requirements.txt pytest mongomock
cd app
python app.py
```

**macOS or Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r app/requirements.txt pytest mongomock
cd app
python app.py
```

Open **http://127.0.0.1:5001** (customer view) and **http://127.0.0.1:5001/owner** (owner view). The owner view asks for the access code; on a laptop it is **ACS730**. Try selling more than the stock left: the app refuses and shows a message. Press **Ctrl+C** to stop.

> On a Mac, use `python3` until the virtual environment is active, and use port 5001: port 5000 is taken by AirPlay Receiver.

> If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then try again.

---

## 5. Run the tests

From the repository root (with the virtual environment active):

```bash
pytest
```

You should see **23 passed**. Take a screenshot; it is useful evidence for the report.

---

## 6. Deploy to Azure

Clement does this, because he owns the subscription.

**Step 1. Sign in and pick the subscription.**

```bash
az login
az account set --subscription "Azure for Students"
az account show --output table
```

**Step 2. Run the deploy script from the repository root.**

Windows:

```powershell
.\scripts\deploy.ps1
```

macOS, Linux or Git Bash:

```bash
bash scripts/deploy.sh
```

The script:

1. creates the resource group `caa900-stockwise-rg` in Canada Central (skipped if it exists);
2. creates the App Service plan and web app from `infra/main.bicep`;
3. packages the `app` folder into `app.zip`;
4. uploads it, and Azure installs the packages from `requirements.txt`.

At the end it prints our two public links. The first start can take two to three minutes.

**Step 3. Add the secret key and the owner access code (once).** Never commit these values.

```bash
az webapp config appsettings set --resource-group caa900-stockwise-rg \
  --name <web app name printed by the script> \
  --settings FLASK_SECRET_KEY=<a long random value> OWNER_ACCESS_CODE=<the owner code>
```

To generate a random value: `python -c "import secrets; print(secrets.token_hex(32))"`

---

## 7. Evidence for Progress Submission 2

Take these screenshots, each showing the URL bar or the resource name:

1. The **customer view** at the public URL.
2. The **owner view** at the public URL.
3. The **resource group** in the Azure portal, showing the App Service plan and web app with their tags.
4. The **deployment** in the portal (Resource group → Deployments → `main`), which proves the resources came from Bicep.
5. The **pull request** on GitHub, showing one member's change reviewed by the other.
6. The **test run** showing 10 passed.

---

## 8. Protect our credit

- The plan uses the **F1 (free)** tier, so it costs nothing while we only have the website.
- In Submission 3 we change `skuName` to **B1**, because the free tier cannot connect to a private database. B1 is billed while it exists, so we will remove it when we are not working.
- To remove everything in the resource group (it can be recreated with the script):

```bash
az group delete --name caa900-stockwise-rg --yes
```

- Take a screenshot of the remaining credit at **microsoftazuresponsorships.com/balance** each week for the cost log.

---

## 9. If something goes wrong

| Problem | What to do |
|---|---|
| The site shows a default Azure page or "Application Error" | Wait two minutes and refresh. Then check the logs: `az webapp log tail --resource-group caa900-stockwise-rg --name <app name>` |
| `RequestDisallowedByAzure` or a region error | Azure for Students may limit regions. Change `canadacentral` in the deploy script to an allowed region (for example `canadaeast` or `eastus`) and run it again. |
| The free (F1) plan is refused | Change `skuName` in `infra/main.bicep` to `B1`, deploy, and delete the group when not in use. |
| `az` or `python` is not recognised | Close and reopen the terminal after installing, or reinstall with "Add to PATH" ticked. |
| `ModuleNotFoundError: flask` | Activate the virtual environment and run `pip install -r app/requirements.txt` again. |

---

## 10. What comes next (Progress Submission 3, due October 19)

| Task | Owner |
|---|---|
| Azure SQL Database (serverless) behind a private endpoint; switch plan to B1 with VNet integration | Clement |
| Replace the sample JSON with database tables (`inventory.py` keeps the same methods) | Clement |
| Owner and customer sign-in with Entra External ID; protect `/owner` | Halimat |
| GitHub Actions workflow: run tests, then deploy on every merge to `main` | Clement |
| Key Vault for secrets, read by the web app's managed identity | Both |
