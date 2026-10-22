// StockWise Solutions infrastructure.
// - App Service plan (Linux) and web app that run our Flask app.
// - Connects the app to our database: an Azure Cosmos DB for MongoDB account.
//   The database account was created in the Azure portal, because Azure for
//   Students only allows Cosmos DB in certain regions; this file refers to it by
//   name and passes its connection string to the app.
// Values for our team are in infra/main.bicepparam.

@description('Region for the App Service plan and web app. Must be a region our Azure for Students policy allows.')
param location string = resourceGroup().location

@description('Pricing tier. F1 is free. Switch to B1 only for demos that need more CPU.')
@allowed([
  'F1'
  'B1'
])
param skuName string = 'F1'

@description('App Service plan name.')
param planName string = 'caa900-stockwise-plan'

@description('Web app name (must be unique across Azure).')
param webAppName string = 'caa900-stockwise-app-${uniqueString(resourceGroup().id)}'

@description('Name of our Cosmos DB for MongoDB account in this resource group. Leave empty to run the app without a database (sample data in memory).')
param cosmosAccountName string = ''

@description('MongoDB database name inside the Cosmos DB account.')
param databaseName string = 'stockwise'

// Tags on every resource so we can track cost and find our resources.
var tags = {
  project: 'caa900'
  team: 'stockwise'
  env: 'dev'
}

var useDatabase = !empty(cosmosAccountName)

// ---------- Database (already exists; referenced by name) ----------

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' existing = if (useDatabase) {
  name: useDatabase ? cosmosAccountName : 'none'
}

var baseSettings = [
  {
    // Tells App Service to install requirements.txt when we deploy.
    name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
    value: 'true'
  }
]

// The connection string goes straight from Cosmos DB into the app's settings.
// It never appears in our code, GitHub or the pipeline log.
var databaseSettings = useDatabase ? [
  {
    name: 'MONGODB_URI'
    value: cosmos!.listConnectionStrings().connectionStrings[0].connectionString
  }
  {
    name: 'MONGODB_DB'
    value: databaseName
  }
] : []

// ---------- Web app ----------

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: planName
  location: location
  tags: tags
  kind: 'linux'
  sku: {
    name: skuName
  }
  properties: {
    reserved: true // required for Linux plans
  }
}

resource webApp 'Microsoft.Web/sites@2023-12-01' = {
  name: webAppName
  location: location
  tags: tags
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true // redirect all HTTP traffic to HTTPS
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'gunicorn --bind=0.0.0.0 --timeout 600 app:app'
      alwaysOn: skuName != 'F1' // the free tier does not support Always On
      ftpsState: 'Disabled' // no FTP uploads; we deploy from code only
      minTlsVersion: '1.2'
      appSettings: concat(baseSettings, databaseSettings)
    }
  }
}

output webAppName string = webApp.name
output url string = 'https://${webApp.properties.defaultHostName}'
output usesDatabase bool = useDatabase
