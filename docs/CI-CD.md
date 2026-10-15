# CI/CD: GitHub Actions to Azure

Our workflow is `.github/workflows/deploy.yml`.

| When | What runs |
|---|---|
| A pull request to `main` | The tests |
| A merge to `main`, or **Run workflow** on the Actions tab | The tests, then Bicep (infrastructure), then the app deployment |

GitHub signs in to Azure with **OIDC**: a managed identity in our resource group trusts our repository's `main` branch. No Azure password or key is stored in GitHub.

## One-time setup (Azure portal and GitHub website)

Done by the subscription owner (Clement).

### 1. Register the App Service provider
Portal → **Subscriptions** → *Azure for Students* → **Resource providers** → search `Microsoft.Web` → **Register** (skip if it already says *Registered*).

### 2. Create the resource group (skip if it exists)
Portal → **Resource groups** → **Create**
- Name: `caa900-stockwise-rg`
- Region: **Canada Central**
- Tags: `project = caa900`, `team = stockwise`, `env = dev`

### 3. Create the managed identity
Portal → search **Managed Identities** → **Create**
- Resource group: `caa900-stockwise-rg`
- Region: Canada Central
- Name: `caa900-stockwise-github`
- Tags: same as above

### 4. Let GitHub use it (federated credential)
Open the identity → **Settings → Federated credentials → Add credential**
- Scenario: **GitHub Actions deploying Azure resources**
- Organization: `Emes101`
- Repository: `Capstone-Project-CAA900NCE`
- Entity: **Branch**, Branch: `main`
- Name: `github-main`

### 5. Give it access to the resource group only
Portal → **Resource groups** → `caa900-stockwise-rg` → **Access control (IAM)** → **Add → Add role assignment**
- Role: **Contributor** → Next
- Assign access to: **Managed identity** → **Select members** → `caa900-stockwise-github`
- **Review + assign**

Least privilege: the identity can change only this resource group, not the rest of the subscription.

### 6. Copy three IDs
- **Client ID**: the identity's **Overview** page
- **Tenant ID** and **Subscription ID**: Portal → **Subscriptions** → *Azure for Students* → Overview (Tenant: search **Microsoft Entra ID** → Overview → *Tenant ID*)

### 7. Add GitHub secrets
GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**

| Name | Value |
|---|---|
| `AZURE_CLIENT_ID` | Client ID from step 6 |
| `AZURE_TENANT_ID` | Tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Subscription ID |
| `FLASK_SECRET_KEY` | A long random value: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `OWNER_ACCESS_CODE` | The owner dashboard code |

### 8. Run it
Merge the pull request that adds the workflow, or open **Actions → Test and deploy → Run workflow**. When it finishes, the run's **Summary** shows the live customer and owner links.

## Troubleshooting

| Error in the log | Fix |
|---|---|
| `AADSTS70021` / no matching federated identity | Step 4 must say organization `Emes101`, repository `Capstone-Project-CAA900NCE`, branch `main`, exactly |
| `AuthorizationFailed` | Step 5: the identity needs **Contributor** on the resource group |
| `ResourceGroupNotFound` | Step 2: create `caa900-stockwise-rg` first |
| `MissingSubscriptionRegistration` | Step 1: register `Microsoft.Web` |
| Region or quota error | Recreate the resource group in another region (e.g. Canada East) |

## Evidence for the reports
- Screenshot of a green run on the **Actions** tab, with the live URL in the Summary
- Screenshot of the federated credential and the IAM role assignment
- Resource group → **Deployments** → `github-run-N` (proves Bicep created the resources)
