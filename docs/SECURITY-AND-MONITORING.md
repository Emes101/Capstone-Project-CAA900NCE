# Sign-in, Key Vault and monitoring: what to do (starter v8)

v8 replaces Entra External ID with a **simple email-and-password sign-in built into our app**. It needs no tenant, no app registration and no portal sign-in setup.

| Feature | How it works |
|---|---|
| Customer sign-up and sign-in | `/signup` and `/login`. Accounts are saved in a new `users` collection in our Cosmos DB, with the password stored only as a salted hash. |
| Owner | One account, created automatically from two GitHub secrets: `OWNER_EMAIL` and `OWNER_PASSWORD`. It has the **owner** role. |
| Protection | After sign-in, the browser holds a signed session cookie (the token). Owner pages and the owner API check it for the owner role. Not signed in: pages go to `/login` and the API returns 401. A customer gets 403. |
| Key Vault | The database connection string, owner password and session key are Key Vault references. Only the web app's identity can read them. |
| Monitoring | Application Insights with live metrics, and an email alert when there are more than 5 server errors in 5 minutes. |

**Do the steps in order and check each one before moving on.** The total time is about 45 minutes.

---

## Step 1. Azure preparation (Clement, 10 min)

### 1a. Register the services (skip if you already did this for v7)

Portal → **Cloud Shell** (`>_` at the top) → **Bash**. Paste:

```bash
for ns in Microsoft.KeyVault Microsoft.Insights Microsoft.OperationalInsights Microsoft.AlertsManagement; do
  az provider register --namespace "$ns" --output none
  echo "$ns: $(az provider show --namespace "$ns" --query registrationState --output tsv)"
done
```

Run it again after 2 minutes. Every line must say `Registered`.

### 1b. Create the `users` collection

Portal → **Azure Cosmos DB** → `caa900-stockwise-db-ha` → **Data Explorer** → **New Collection**:

- Database: **Use existing** → `stockwise`
- Collection id: `users`
- Sharding: **Unsharded**
- Throughput, if asked: **Manual, 400 RU/s**

Click **OK**.

> **Cost check:** the free tier covers 1,000 RU/s in total. `products` (400) plus `users` (400) is 800, so it stays free. If Azure does not ask for throughput, your database shares its throughput, which is also free.

### 1c. If you switched on Authentication for v7, switch it off

Portal → **stockwise-ebapp** → **Authentication**. If a **Microsoft** identity provider is listed, click **Remove authentication** (or delete the provider) and confirm. If the page says no provider is set up, skip this step.

If you created the `StockWise Customers` tenant, you can leave it. We no longer use it.

---

## Step 2. GitHub secrets (Clement, 5 min)

GitHub → repository → **Settings → Secrets and variables → Actions → New repository secret**:

| Name | Value |
|---|---|
| `OWNER_EMAIL` | The email Michael (the owner) signs in with. For the demo, use a team email. |
| `OWNER_PASSWORD` | A strong password of 12 or more characters. To make one on a Mac: `python3 -c "import secrets; print(secrets.token_urlsafe(12))"` |
| `ALERT_EMAIL` | The email for alerts (skip if you added it for v7) |

Check that `FLASK_SECRET_KEY` is already in the list. If it is missing, sign-in stops working after every restart.

You can delete `OWNER_ACCESS_CODE` and `AUTH_CLIENT_SECRET` (if it exists). v8 does not use them.

**Do not share the owner password in the report.** Give it to the instructor privately if they ask.

---

## Step 3. Put the v8 code in GitHub (Halimat, 15 min)

Unzip `stockwise-starter-v8.zip` into **Downloads**. In Terminal, paste these lines **one at a time**:

```bash
cd ~/Capstone-Project-CAA900NCE
git checkout main
git pull
git checkout -b feature/simple-sign-in
cp -R ~/Downloads/stockwise-starter-v8/app ~/Downloads/stockwise-starter-v8/infra ~/Downloads/stockwise-starter-v8/tests ~/Downloads/stockwise-starter-v8/docs ~/Downloads/stockwise-starter-v8/scripts .
cp ~/Downloads/stockwise-starter-v8/.github/workflows/deploy.yml .github/workflows/deploy.yml
git rm app/templates/owner_login.html
git status
```

- `git rm` removes the old access-code page. If it says the file does not exist, that is fine.
- `git status` should show `accounts.py`, `login.html`, `signup.html`, `forbidden.html` and `test_accounts.py` as new, and `app.py`, `main.bicep`, `main.bicepparam` and `deploy.yml` as changed.

Run the tests:

```bash
source .venv/bin/activate
pip install -r app/requirements.txt pytest mongomock
python3 -m pytest
```

You should see **47 passed**. Then:

```bash
git add .
git commit -m "Simple email sign-in with owner role; Key Vault and monitoring"
git push -u origin feature/simple-sign-in
```

On GitHub: **Compare & pull request → Create pull request** → wait for the green test check → Clement reviews and clicks **Merge pull request**. Then watch the **Actions** tab until the run is green, about 5 to 8 minutes.

**Optional: try it on your laptop first.** Run `cd app && python3 app.py`, then open http://localhost:5001. The local owner is `owner@stockwise.test` with password `owner-pass-123`; this account exists only on your laptop.

---

## Step 4. Check that everything works (both, 15 min)

Use the live URL: https://stockwise-ebapp-d5amh9exhbe5ebh0.canadacentral-01.azurewebsites.net

**Sign-in**

1. Click **Sign up** and create a customer account. The top bar now says **Signed in as …**.
2. Open `/owner`. You see **"This area is for the store owner"** (403).
3. Click **Sign out**. Then click **Sign in** and use `OWNER_EMAIL` and `OWNER_PASSWORD`. You go straight to the **Owner dashboard**. Record a sale.
4. Open `/api/me` to see your account as JSON, with no password.
5. In Terminal, check that the owner API refuses a request with no token:

```bash
curl -i https://stockwise-ebapp-d5amh9exhbe5ebh0.canadacentral-01.azurewebsites.net/api/owner/low-stock
```

You should see `HTTP/1.1 401` and `"Sign in first."`.

**Database**

6. Cosmos DB → **Data Explorer** → `stockwise` → `users` → **Documents**. You see the owner and your customer account, each with a `password_hash` that starts with `scrypt:` and no password.

**Key Vault**

7. **stockwise-ebapp → Environment variables**: `MONGODB_URI`, `OWNER_PASSWORD` and `FLASK_SECRET_KEY` show **Key vault Reference** with a green tick. `OWNER_EMAIL` is a normal setting.
8. **Key vault (sw-kv-…) → Access policies**: only `stockwise-ebapp`, with Get and List on secrets. On the **Secrets** page, Azure says you are not authorized to view them. That is correct, because only the app can read them.

**Monitoring**

9. **stockwise-insights → Live metrics**: click around the site and watch the requests appear.
10. Sign in as the owner, open `/owner/test-error`, and refresh **10 times**. Within about 10 minutes you get the **"Fired: … stockwise-5xx-errors"** email. A **Resolved** email follows later.

---

## Step 5. Screenshots for the report

Every screenshot must show the URL bar or the resource name. Hide secret values.

1. The sign-up page, then the customer view showing **Signed in as …**
2. A customer opening `/owner`: the 403 page
3. The owner dashboard after a sale, showing the owner's name in the top bar
4. `/api/products` and `/api/me` as JSON
5. Terminal: `curl -i …/api/owner/low-stock` returning 401
6. Data Explorer: the `users` documents, showing hashed passwords
7. Environment variables with green Key vault References
8. Key Vault access policies
9. Live metrics, and the Fired alert email
10. The resource group (all resources and tags), Deployments → `github-run-N`, and the green Actions run

---

## Troubleshooting

| What you see | Fix |
|---|---|
| `MissingSubscriptionRegistration` in the Actions log | Do step 1a again until every line says `Registered`, then re-run the workflow. |
| `VaultAlreadyExists` or `name is already in use` | Add `param keyVaultName = 'sw-kv-stockwise-ha2'` to `infra/main.bicepparam`, then push. |
| The owner cannot sign in on Azure | Check that `OWNER_EMAIL` and `OWNER_PASSWORD` are set in GitHub exactly, then **Actions → Run workflow**. The owner account is created or updated each time the app starts. |
| "An account with this email already exists" when the owner signs up | The owner does not sign up. Use **Sign in** with the owner email and password. |
| Signed out after every restart | `FLASK_SECRET_KEY` is missing in GitHub. Add it and re-run the workflow. |
| Red cross on a Key vault Reference | Wait 2 minutes and restart the web app. Check that **Access policies** lists `stockwise-ebapp`. |
| **Application Error** page | stockwise-ebapp → **Log stream**. Send us the last 20 lines. |
| Clicking **Sign in** shows a Microsoft page | Authentication from v7 is still switched on. Do step 1c. |
| Tests fail on your laptop with `No module named mongomock` | Run `pip install pytest mongomock`, then try again. |
