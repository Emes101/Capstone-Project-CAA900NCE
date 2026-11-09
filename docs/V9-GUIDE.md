# StockWise v9: reservations, low-stock email, backup and restore, YOLO shelf scan

## What v9 adds

| Feature | Where | What it does |
|---|---|---|
| **Reservations** | `/shop`, `/reservations`, owner dashboard | A signed-in customer reserves 1 to 5 units for pickup. The units leave stock at once, so two customers can never get the last item. The customer can cancel while it waits. The owner marks it **Picked up** (units stay sold) or **Cancel** (units go back). API: `POST/GET /api/reservations`, `GET /api/owner/reservations`. |
| **Low-stock email** (optional) | `app/notify.py` | When a sale or reservation brings an item to its reorder level (or to zero), the owner gets one email through Azure Communication Services. Without it, the alert goes to the app log and the dashboard shows **Low-stock email alerts: off**. |
| **Backup and restore** | `scripts/backup_restore.py` | Saves products and users to a JSON file, compares a backup with the database, and restores products. |
| **YOLO shelf scan** | `scripts/yolo/shelf_scan.py` | Counts mice and keyboards in a shelf photo and compares the count with the app's stock. Runs on a laptop. |

Reservations are stored inside each product document, so **no new Cosmos DB collection is needed and the cost does not change**. There are 113 automated tests.

Do the parts in order: **A** puts the code on GitHub, **B** deploys it to Azure, and **C** checks it. **D**, **E** and **F** are the extra tasks for the report.

---

## A. Put v9 on GitHub (Halimat, 15 minutes)

Unzip `stockwise-starter-v9.zip` into **Downloads**. In Terminal, paste these **one line at a time**:

```bash
cd ~/Capstone-Project-CAA900NCE
git checkout main
git pull
git checkout -b feature/v9-reservations
cp -R ~/Downloads/stockwise-starter-v9/app ~/Downloads/stockwise-starter-v9/infra ~/Downloads/stockwise-starter-v9/tests ~/Downloads/stockwise-starter-v9/docs ~/Downloads/stockwise-starter-v9/scripts .
cp ~/Downloads/stockwise-starter-v9/.github/workflows/deploy.yml .github/workflows/deploy.yml
cp ~/Downloads/stockwise-starter-v9/.gitignore .gitignore
source .venv/bin/activate
pip install -r app/requirements.txt pytest mongomock
python3 -m pytest
```

You must see **113 passed**. If anything fails, stop and send the output.

```bash
git add .
git commit -m "v9: reservations, low-stock email, backup and restore, YOLO shelf scan"
git -c credential.helper= push -u origin feature/v9-reservations
```

- **Username:** `Halimatcd`. **Password:** your GitHub token (starts with `ghp_`, needs the **repo** and **workflow** ticks).
- On GitHub: **Compare & pull request** → **Create pull request** → wait for the green **test** check → **Merge pull request**.

> If `git pull` on main says your v8 branch was never merged, merge the v8 pull request first, then start again from `git checkout main`.

---

## B. Deploy to Azure

Choose **one** of the two options.

### Option 1: GitHub Actions deploys it for you

This works when these GitHub secrets exist (repo → **Settings → Secrets and variables → Actions**): `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`, `OWNER_EMAIL`, `OWNER_PASSWORD`, `FLASK_SECRET_KEY`, `ALERT_EMAIL`.

- Use the **same** owner email and password you typed in Cloud Shell before, or the owner's password changes.
- **Merging the pull request starts the deployment.** Watch the **Actions** tab until the run is green (8 to 10 minutes).

### Option 2: Azure Cloud Shell (Bash), as before

1. Delete the old zips first, so Cloud Shell does not rename the new one:
   ```bash
   rm -rf ~/stockwise-starter-v8* ~/stockwise-starter-v9*
   ```
2. Cloud Shell toolbar → **Manage files → Upload** → `stockwise-starter-v9.zip`.
3. Paste one line at a time:
   ```bash
   cd ~ && unzip -q stockwise-starter-v9.zip && cd stockwise-starter-v9
   az account set --subscription "Azure for Students"
   bash scripts/deploy.sh
   ```
4. Answer the questions:
   - **Owner email and password:** the same as before.
   - **Session key:** press Enter.
   - **Alert email:** as before.
   - **Low-stock email:** press **Enter** to skip, or see Part D.
5. Wait about 12 minutes. If the upload fails three times, the script prints the deployment log. Send it to us.

---

## C. Check it works (both, 10 minutes)

Live site: https://stockwise-ebapp-d5amh9exhbe5ebh0.canadacentral-01.azurewebsites.net

1. `/api/health` shows `"storage": "database"`.
2. Sign in as a customer, or create one. Each product in stock has **Qty** and **Reserve for pickup**.
3. Reserve **2 × HD webcam**. You land on **My reservations** with status **Waiting for pickup**, and the webcam stock drops by 2.
4. Sign out. Sign in at `/owner/login`. The dashboard shows **1 Waiting for pickup** and the reservation in a table.
5. Click **Picked up**. The reservation disappears from the list, and the stock stays lower.
6. Reserve again as the customer, then **Cancel** it on **My reservations**. The stock goes back up.

**Screenshots for the report:** the shop with **Reserve** buttons; **My reservations**; and the owner dashboard with **Reservations waiting for pickup**.

---

## D. Low-stock email (optional, Clement, 20 minutes)

Skip this if you have no Communication Services resource. The app works without it.

1. Portal → search **Communication Services** → open yours (or **Create** one in `caa900_stockwiseRG`; Data location: **Canada**).
2. **Email → Domains → Connect domain**. Connect an **Azure managed domain** from your **Email Communication Services** resource. If you have none, create one, then **Provision domains → Add a free Azure subdomain**.
3. Copy two values:
   - **Communication Services → Settings → Keys → Primary connection string**
   - **Email Communication Services → Provision domains → (your domain) → MailFrom addresses**, for example `DoNotReply@1a2b3c….azurecomm.net`
4. Pass them in:
   - **Option 1 (GitHub):** add the secrets `ACS_CONNECTION_STRING` and `ACS_SENDER_ADDRESS` (and, if you like, `LOW_STOCK_EMAIL_TO`), then **Actions → Test and deploy → Run workflow**.
   - **Option 2 (Cloud Shell):** run `bash scripts/deploy.sh` again and paste them when asked.
5. Check: the owner dashboard says **Low-stock email alerts: on**. As the owner, find a product that is still **In stock** and sell enough to bring it down to its **Reorder at** number (for example, USB-C charger: 18 in stock, reorder at 6, so sell 12). Within a minute, the owner email gets **"Low stock: … (6 left)"**. Check junk mail too.

The connection string goes into Key Vault, like the other secrets.

---

## E. Backup and restore test (Clement, 15 minutes, Cloud Shell)

This proves we can get data back after a mistake.

```bash
cd ~/stockwise-starter-v9
pip install --user -q pymongo
export MONGODB_URI=$(az cosmosdb keys list -g caa900_stockwiseRG -n caa900-stockwise-db-ha --type connection-strings --query "connectionStrings[0].connectionString" -o tsv)
python3 scripts/backup_restore.py backup
```

It prints `Backup saved: backups/stockwise-2026….json` with the number of products and users. Use the file name it prints in the next steps.

1. On the live owner dashboard, **sell 1 Wireless mouse** (this is our "mistake").
2. Compare the backup with the database:
   ```bash
   python3 scripts/backup_restore.py verify backups/stockwise-XXXXXXXX-XXXXXX.json
   ```
   It says `1 product(s) differ from the backup: CP-4001`.
3. Restore:
   ```bash
   python3 scripts/backup_restore.py restore backups/stockwise-XXXXXXXX-XXXXXX.json --yes
   ```
   It ends with `Check: the products now match the backup.` Refresh the dashboard: the mice are back to their old number.
4. **Screenshots for the report:** the three outputs above, and the dashboard before and after.
5. Clean up, because the file holds customer emails and password hashes:
   ```bash
   rm -rf backups && unset MONGODB_URI
   ```

**Notes**
- Restore does not touch user accounts unless you add `--include-users`.
- Restore overwrites live data, so in real use, take a fresh backup first.
- Azure also keeps its own automatic Cosmos DB backups (every 4 hours, 2 copies). Our script adds a backup that we control and can test ourselves.

---

## F. YOLO shelf scan (both, 30 minutes, on the Mac)

```bash
cd ~/Capstone-Project-CAA900NCE
python3 -m venv .venv-yolo
source .venv-yolo/bin/activate
pip install -r scripts/yolo/requirements.txt
```

The install is large (about 1 GB, mostly PyTorch), so do it on good Wi-Fi.

1. Take a clear photo of a desk or shelf with **computer mice and keyboards** on it, from the front with good light. Save it as `~/Desktop/shelf.jpg`.
2. Run:
   ```bash
   python3 scripts/yolo/shelf_scan.py ~/Desktop/shelf.jpg
   ```
   The first run downloads the model (6 MB). You will see a table like this:
   ```
   Object       Seen  Product                    App stock  Note
   keyboard        1  Mechanical keyboard                3  Check: 2 not on this shelf
   mouse           2  Wireless mouse                    12  Check: 10 not on this shelf
   ```
   It also saves `scan-results/shelf-scanned.jpg`, the photo with boxes drawn around each object.
3. If it misses objects, try `--confidence 0.25`. For fewer false boxes, try `0.5`.
4. **Screenshots for the report:** the Terminal table, and the photo with the boxes.
5. Run `deactivate` when you are done.

**Limits to state in the report:** the ready-made model knows 80 everyday objects. Only some are our products (mouse, keyboard). Recognising every product would need our own training photos. That is future work.

---

## Troubleshooting

| What you see | Fix |
|---|---|
| Tests fail with `No module named azure.communication` | `pip install -r app/requirements.txt`, then run the tests again. |
| Actions: `Invalid username or token` on push | Use a new classic token with **repo** and **workflow**, and push with `git -c credential.helper= push …`. |
| Owner cannot sign in after the GitHub deployment | The GitHub `OWNER_PASSWORD` secret differs from the one used in Cloud Shell. Set it to the password you want, then **Run workflow**. |
| **Reserve** button missing | You are signed in as the owner (owners record sales instead), or the item is out of stock. |
| Dashboard says email **off** after Part D | Both `ACS_CONNECTION_STRING` and `ACS_SENDER_ADDRESS` must be set. Re-run the deployment. |
| No email arrives | Check junk mail. In **stockwise-ebapp → Log stream**, look for `Low-stock email failed`. The sender must be the exact **MailFrom** address. |
| Backup: `ServerSelectionTimeoutError` | Cosmos DB → **Networking** must allow public access, or add Cloud Shell's IP. Then run it again. |
| YOLO: `pip` fails on the Mac | Use Python 3.10 to 3.13 (`python3 --version`). If needed, install Python 3.12 from python.org and create the venv with `python3.12 -m venv .venv-yolo`. |
