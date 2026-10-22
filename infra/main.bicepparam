using 'main.bicep'

// Our team's Azure resources (names copied from the Azure portal).
param location = 'canadacentral'
param skuName = 'F1'
param planName = 'ASP-caa900stockwiseRG-af4e'
param webAppName = 'stockwise-ebapp'
param cosmosAccountName = 'caa900-stockwise-db-ha'
param databaseName = 'stockwise'
