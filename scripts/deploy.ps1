# Deploys StockWise to Azure from Windows PowerShell.
# Run from the repository root after: az login
# Usage: .\scripts\deploy.ps1

$ErrorActionPreference = "Stop"
$ResourceGroup = "caa900_stockwiseRG"
$Location = "canadacentral"

Write-Host "1/4 Creating the resource group (skipped if it exists)..."
az group create --name $ResourceGroup --location $Location `
  --tags project=caa900 team=stockwise env=dev --output none

Write-Host "2/4 Creating the App Service plan and web app from infra/main.bicep..."
$App = az deployment group create --resource-group $ResourceGroup `
  --parameters infra/main.bicepparam `
  --query properties.outputs.webAppName.value --output tsv

Write-Host "3/4 Packaging the app folder..."
if (Test-Path app.zip) { Remove-Item app.zip }
# Python builds the zip so file paths use "/" (Compress-Archive can break them on Linux).
Push-Location app
python -m zipfile -c ..\app.zip .
Pop-Location

Write-Host "4/4 Uploading the code to $App (this takes a few minutes)..."
az webapp deploy --resource-group $ResourceGroup --name $App --src-path app.zip --type zip --output none

$HostName = az webapp show --resource-group $ResourceGroup --name $App --query defaultHostName --output tsv
Write-Host ""
Write-Host "Done. Customer view: https://$HostName/"
Write-Host "      Owner view:    https://$HostName/owner"
