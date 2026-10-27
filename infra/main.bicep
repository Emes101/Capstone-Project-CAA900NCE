// StockWise Solutions infrastructure (v8).
// - App Service plan (Linux) and web app that run our Flask app.
// - Key Vault that holds every secret. The web app reads them with its own
//   managed identity through Key Vault references, so no secret value is
//   stored in app settings, in code or in GitHub logs.
// - Log Analytics + Application Insights for logs and errors, and one alert
//   that emails us when the site returns server errors (HTTP 5xx).
// - Connects the app to our existing Azure Cosmos DB for MongoDB account
//   (created in the portal because Azure for Students limits its regions).
// Names for our team are in infra/main.bicepparam. Secret values come from
// GitHub secrets as environment variables (see .github/workflows/deploy.yml).

@description('Region for the plan, web app, Key Vault and monitoring.')
param location string = resourceGroup().location

@description('Pricing tier. F1 is free. B1 for demos that need more CPU.')
@allowed([
  'F1'
  'B1'
])
param skuName string = 'F1'

@description('App Service plan name.')
param planName string

@description('Web app name.')
param webAppName string

@description('Name of our Cosmos DB for MongoDB account in this resource group. Empty = sample data in memory.')
param cosmosAccountName string = ''

@description('MongoDB database name inside the Cosmos DB account.')
param databaseName string = 'stockwise'

@description('Key Vault name (3-24 letters, numbers and hyphens, unique across Azure).')
param keyVaultName string = 'sw-kv-${uniqueString(resourceGroup().id)}'

@description('Email the owner signs in with. Not a secret, but kept out of the repository.')
param ownerEmail string = ''

@description('Owner password. Stored in Key Vault; the app keeps only a hash in the database.')
@secure()
param ownerPassword string = ''

@description('Key that signs the session cookie.')
@secure()
param flaskSecretKey string = ''

@description('Email address that receives the 5xx error alert. Empty = no alert.')
param alertEmail string = ''

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

// ---------- Monitoring ----------

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'stockwise-logs'
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: 1 // hard cap so logs can never use much credit
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'stockwise-insights'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
  }
}

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
  identity: {
    type: 'SystemAssigned' // the app's own identity, used to read Key Vault
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true // redirect all HTTP traffic to HTTPS
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: 'gunicorn --bind=0.0.0.0 --timeout 600 app:app'
      alwaysOn: skuName != 'F1' // the free tier does not support Always On
      ftpsState: 'Disabled' // no FTP uploads; we deploy from code only
      minTlsVersion: '1.2'
    }
  }
}

// ---------- Key Vault and secrets ----------
// Access policies (not Azure RBAC) because our GitHub identity has Contributor,
// which cannot create role assignments. Only the web app can read secrets.

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: false
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    accessPolicies: [
      {
        tenantId: subscription().tenantId
        objectId: webApp.identity.principalId
        permissions: {
          secrets: [
            'get'
            'list'
          ]
        }
      }
    ]
  }
}

resource mongoSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (useDatabase) {
  parent: vault
  name: 'mongodb-uri'
  properties: {
    value: cosmos!.listConnectionStrings().connectionStrings[0].connectionString
  }
}

resource ownerPasswordSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(ownerPassword)) {
  parent: vault
  name: 'owner-password'
  properties: {
    value: ownerPassword
  }
}

resource flaskKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (!empty(flaskSecretKey)) {
  parent: vault
  name: 'flask-secret-key'
  properties: {
    value: flaskSecretKey
  }
}

// ---------- App settings ----------
// This list replaces ALL app settings on every deployment, so every setting
// the app needs must be here.

var baseSettings = {
  SCM_DO_BUILD_DURING_DEPLOYMENT: 'true' // install requirements.txt on deploy
  APPLICATIONINSIGHTS_CONNECTION_STRING: appInsights.properties.ConnectionString
  OTEL_SERVICE_NAME: 'stockwise-web'
}

var databaseSettings = useDatabase ? {
  MONGODB_URI: '@Microsoft.KeyVault(SecretUri=${mongoSecret!.properties.secretUri})'
  MONGODB_DB: databaseName
} : {}

var ownerSettings = !empty(ownerPassword) ? {
  OWNER_EMAIL: ownerEmail
  OWNER_PASSWORD: '@Microsoft.KeyVault(SecretUri=${ownerPasswordSecret!.properties.secretUri})'
} : {}

var flaskKeySettings = !empty(flaskSecretKey) ? {
  FLASK_SECRET_KEY: '@Microsoft.KeyVault(SecretUri=${flaskKeySecret!.properties.secretUri})'
} : {}

resource appSettings 'Microsoft.Web/sites/config@2023-12-01' = {
  parent: webApp
  name: 'appsettings'
  // Each Key Vault reference above makes this wait for the vault and its
  // access policy, so the app can read the secrets as soon as it restarts.
  properties: union(baseSettings, databaseSettings, ownerSettings, flaskKeySettings)
}

// ---------- Alert: email when the site returns server errors ----------

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (!empty(alertEmail)) {
  name: 'stockwise-alert-email'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'stockwise'
    enabled: true
    emailReceivers: [
      {
        name: 'team-email'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource errorAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = if (!empty(alertEmail)) {
  name: 'stockwise-5xx-errors'
  location: 'global'
  tags: tags
  properties: {
    description: 'More than 5 server errors (HTTP 5xx) in 5 minutes on the StockWise web app.'
    severity: 2
    enabled: true
    scopes: [
      webApp.id
    ]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          name: 'Http5xx'
          criterionType: 'StaticThresholdCriterion'
          metricNamespace: 'Microsoft.Web/sites'
          metricName: 'Http5xx'
          operator: 'GreaterThan'
          threshold: 5
          timeAggregation: 'Total'
        }
      ]
    }
    actions: [
      {
        actionGroupId: actionGroup.id
      }
    ]
  }
}

output webAppName string = webApp.name
output url string = 'https://${webApp.properties.defaultHostName}'
output keyVaultName string = vault.name
output usesDatabase bool = useDatabase
