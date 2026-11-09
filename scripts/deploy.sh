#!/usr/bin/env bash
# Deploys StockWise (v9) from Azure Cloud Shell (Bash), or from macOS/Linux after `az login`.
# It does the same as our GitHub Actions workflow: Bicep first, then the app code.
#
# Usage, from the project folder:   bash scripts/deploy.sh
#
# It asks for the secrets (the password is hidden while you type) and never saves
# them to a file. Bicep stores them in Key Vault.
set -euo pipefail

RESOURCE_GROUP="caa900_stockwiseRG"
COSMOS_ACCOUNT="caa900-stockwise-db-ha"
DATABASE="stockwise"

cd "$(dirname "$0")/.."

if [ ! -f infra/main.bicepparam ] || [ ! -d app ]; then
  echo "Run this from the project folder (the one with app/ and infra/)."
  exit 1
fi

echo "Signed in to Azure as: $(az account show --query user.name --output tsv)"
echo "Subscription:           $(az account show --query name --output tsv)"
echo

# ---------- Secrets (asked once, kept only in this shell) ----------
if [ -z "${OWNER_EMAIL:-}" ]; then
  read -r -p "Owner email (Michael signs in with this): " OWNER_EMAIL
fi
if [ -z "${OWNER_PASSWORD:-}" ]; then
  read -r -s -p "Owner password, 12+ characters (hidden): " OWNER_PASSWORD
  echo
fi
if [ "${#OWNER_PASSWORD}" -lt 12 ]; then
  echo "The owner password must have at least 12 characters. Nothing was deployed."
  exit 1
fi
if [ -z "${FLASK_SECRET_KEY:-}" ]; then
  read -r -s -p "Session key (press Enter to make a new one): " FLASK_SECRET_KEY
  echo
  if [ -z "$FLASK_SECRET_KEY" ]; then
    FLASK_SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
  fi
fi
if [ -z "${ALERT_EMAIL:-}" ]; then
  read -r -p "Email for error alerts (press Enter to skip the alert): " ALERT_EMAIL
fi
if [ -z "${ACS_CONNECTION_STRING+x}" ]; then
  echo
  echo "Low-stock email (optional): needs an Azure Communication Services resource with an email domain."
  read -r -s -p "  Communication Services connection string (hidden; press Enter to skip): " ACS_CONNECTION_STRING
  echo
fi
if [ -n "$ACS_CONNECTION_STRING" ] && [ -z "${ACS_SENDER_ADDRESS:-}" ]; then
  read -r -p "  Sender (MailFrom) address, e.g. DoNotReply@xxxx.azurecomm.net: " ACS_SENDER_ADDRESS
fi
if [ -n "$ACS_CONNECTION_STRING" ] && [ -z "${LOW_STOCK_EMAIL_TO:-}" ]; then
  read -r -p "  Send low-stock emails to (press Enter for the owner email): " LOW_STOCK_EMAIL_TO
fi
ACS_SENDER_ADDRESS="${ACS_SENDER_ADDRESS:-}"
LOW_STOCK_EMAIL_TO="${LOW_STOCK_EMAIL_TO:-}"
# infra/main.bicepparam reads these values.
export OWNER_EMAIL OWNER_PASSWORD FLASK_SECRET_KEY ALERT_EMAIL ACS_CONNECTION_STRING ACS_SENDER_ADDRESS LOW_STOCK_EMAIL_TO

# ---------- 1. Azure services used by Key Vault and monitoring ----------
echo
echo "1/5 Checking that Key Vault and monitoring are switched on for the subscription..."
for ns in Microsoft.KeyVault Microsoft.Insights Microsoft.OperationalInsights Microsoft.AlertsManagement; do
  state=$(az provider show --namespace "$ns" --query registrationState --output tsv 2>/dev/null || echo "Unknown")
  if [ "$state" != "Registered" ]; then
    echo "    Registering $ns ..."
    az provider register --namespace "$ns" --wait --output none \
      || echo "    Could not register $ns. Ask Clement (subscription owner) to run this script once."
  fi
done

# ---------- 2. users collection in Cosmos DB ----------
echo "2/5 Checking the 'users' collection in Cosmos DB..."
if az cosmosdb mongodb collection show --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" \
     --database-name "$DATABASE" --name users --output none 2>/dev/null; then
  echo "    It already exists."
elif az cosmosdb mongodb database throughput show --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" \
     --name "$DATABASE" --output none 2>/dev/null; then
  echo "    Creating it (shares the database throughput, no extra cost)..."
  az cosmosdb mongodb collection create --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" \
    --database-name "$DATABASE" --name users --output none
else
  echo "    Creating it with 400 RU/s (products 400 + users 400 = within the 1,000 RU/s free tier)..."
  az cosmosdb mongodb collection create --resource-group "$RESOURCE_GROUP" --account-name "$COSMOS_ACCOUNT" \
    --database-name "$DATABASE" --name users --throughput 400 --output none
fi

# ---------- 3. Infrastructure (Bicep) ----------
echo "3/5 Deploying the infrastructure from infra/main.bicep (2 to 5 minutes)..."
APP=$(az deployment group create \
  --resource-group "$RESOURCE_GROUP" \
  --name "cloudshell-$(date +%Y%m%d-%H%M%S)" \
  --parameters infra/main.bicepparam \
  --query properties.outputs.webAppName.value --output tsv)

# ---------- 4. Package the app ----------
echo "4/5 Packaging the app folder..."
rm -f app.zip
(cd app && python3 -m zipfile -c ../app.zip .)

# ---------- 5. Upload the code ----------
# Bicep has just changed the app settings, so the app and its deployment service
# (Kudu) restart. Wait for them, and retry if Kudu answers 502 while it starts.
echo "5/5 Uploading the code to $APP (3 to 6 minutes; Azure installs the packages)..."
echo "    Waiting 90 seconds for the app to restart after the settings change..."
sleep 90
uploaded=no
for attempt in 1 2 3; do
  if az webapp deploy --resource-group "$RESOURCE_GROUP" --name "$APP" --src-path app.zip --type zip --output none; then
    uploaded=yes
    break
  fi
  echo "    Upload attempt $attempt failed (usually Kudu still starting). Restarting the app and trying again in 2 minutes..."
  az webapp restart --resource-group "$RESOURCE_GROUP" --name "$APP" --output none || true
  sleep 120
done
rm -f app.zip
if [ "$uploaded" != "yes" ]; then
  echo "The code upload failed 3 times. Send this output to the team:"
  az webapp log deployment show --resource-group "$RESOURCE_GROUP" --name "$APP" --query "[-15:].message" --output tsv || true
  exit 1
fi

HOST=$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$APP" --query defaultHostName --output tsv)
echo
echo "Done."
echo "  Landing page:  https://$HOST/"
echo "  Shop:          https://$HOST/shop        (customers sign in first)"
echo "  Owner sign-in: https://$HOST/owner/login (bookmark this for Michael)"
echo
echo "Health check:"
curl -s --max-time 60 "https://$HOST/api/health" || echo "  The app is still starting. Open the health page in a minute: https://$HOST/api/health"
echo
