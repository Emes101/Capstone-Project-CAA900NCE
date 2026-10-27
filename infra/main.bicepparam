using 'main.bicep'

// Our team's resource names. Secret values are NOT here: they come from
// GitHub secrets as environment variables when the workflow runs.

param location = 'canadacentral'
param skuName = 'B1'   // switch to 'F1' (free) when we are not demoing
param planName = 'ASP-caa900stockwiseRG-af4e'
param webAppName = 'stockwise-ebapp'
param cosmosAccountName = 'caa900-stockwise-db-ha'
param databaseName = 'stockwise'

// Read from GitHub secrets (empty if a secret is not set yet).
param ownerEmail = readEnvironmentVariable('OWNER_EMAIL', '')
param ownerPassword = readEnvironmentVariable('OWNER_PASSWORD', '')
param flaskSecretKey = readEnvironmentVariable('FLASK_SECRET_KEY', '')
param alertEmail = readEnvironmentVariable('ALERT_EMAIL', '')
