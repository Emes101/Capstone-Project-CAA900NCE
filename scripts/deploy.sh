#!/usr/bin/env bash
# Deploys StockWise to Azure from macOS, Linux or Git Bash.
# Run from the repository root after: az login
# Usage: bash scripts/deploy.sh
set -euo pipefail

RESOURCE_GROUP="caa900-stockwise-rg"
LOCATION="canadacentral"

echo "1/4 Creating the resource group (skipped if it exists)..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" \
  --tags project=caa900 team=stockwise env=dev --output none

echo "2/4 Creating the App Service plan and web app from infra/main.bicep..."
APP=$(az deployment group create --resource-group "$RESOURCE_GROUP" \
  --template-file infra/main.bicep \
  --query properties.outputs.webAppName.value --output tsv)

echo "3/4 Packaging the app folder..."
rm -f app.zip
(cd app && python -m zipfile -c ../app.zip .)

echo "4/4 Uploading the code to $APP (this takes a few minutes)..."
az webapp deploy --resource-group "$RESOURCE_GROUP" --name "$APP" --src-path app.zip --type zip --output none

HOST=$(az webapp show --resource-group "$RESOURCE_GROUP" --name "$APP" --query defaultHostName --output tsv)
echo
echo "Done. Customer view: https://$HOST/"
echo "      Owner view:    https://$HOST/owner"
