# Database: Azure Cosmos DB for MongoDB

## What we use
- **Service:** Azure Cosmos DB for MongoDB (RU-based), **free tier** (1000 RU/s and 25 GB free per subscription).
- **Database:** `stockwise` · **Collection:** `products` (one document per product, unique index on `sku`).
- **Created in:** the Azure portal, in a region our Azure for Students policy allows. `infra/main.bicep` refers to the account by name (set in `infra/main.bicepparam`) and passes its connection string to the app.
- **Cost:** $0 on the free tier (or a few cents a month on serverless if the free tier was already used).

## How the app uses it
| Where the app runs | `MONGODB_URI` setting | Storage |
|---|---|---|
| On Azure | Set by Bicep from the Cosmos DB account | Cosmos DB: changes are saved |
| On a laptop | Not set | Sample file in memory: resets on restart |

- `app/mongo_inventory.py` has the same methods as `app/inventory.py`, so the pages did not change.
- **Stock never goes below zero:** a sale is one atomic update that only succeeds when `stock >= quantity`, so two sales of the last item cannot both succeed.
- On first start, the app loads the 12 sample products if the collection is empty.
- `/api/health` shows `"storage": "database"` on Azure, which proves the app is using Cosmos DB.

## Security
- The connection string goes straight from Cosmos DB into the App Service settings in Bicep. It is never in our code, GitHub secrets or the pipeline log.
- TLS 1.2 minimum. Customers only reach the database through the app.
- Next step (Submission 4): move the connection string into Key Vault and restrict the database firewall to the app's outbound IP addresses.

## One-time setup
1. Portal → **Azure Cosmos DB** → Create → **Azure Cosmos DB for MongoDB** → **Request unit (RU)**: workload type *Learning*, resource group `caa900-stockwise-rg`, an allowed region, Availability Zones *Disable*, Free Tier Discount *Apply*.
2. **Data Explorer → New Collection**: database `stockwise`, collection `products`, *Unsharded*, 400 RU/s manual (skip throughput on serverless).
3. Put the account name, web app name, plan name and region in `infra/main.bicepparam`.

## Evidence for Submission 3
1. Resource group → the Cosmos DB account `caa900-stockwise-db-...` with its tags.
2. Cosmos DB → **Data Explorer** → `stockwise` → `products`: the product documents.
3. Record a sale on the live owner dashboard, refresh Data Explorer, and show the `stock` value changed (a record saved in the database).
4. Restart the web app, open the owner dashboard: the change is still there.
5. `https://<app>.azurewebsites.net/api/health` showing `"storage": "database"`.
