// StockWise Solutions: infrastructure for Progress Submission 2.
// Creates an App Service plan (Linux) and a web app that runs our Flask app.
// Deploy into the resource group caa900-stockwise-rg (see scripts/deploy.ps1 or deploy.sh).

@description('Azure region. Defaults to the resource group region (Canada Central).')
param location string = resourceGroup().location

@description('Pricing tier. F1 is free (good for Submission 2). Switch to B1 when we add the private database in Submission 3, because F1 cannot join a virtual network.')
@allowed([
  'F1'
  'B1'
])
param skuName string = 'F1'

@description('Web app name. Must be unique across Azure, so a short code from the resource group ID is added.')
param webAppName string = 'caa900-stockwise-app-${uniqueString(resourceGroup().id)}'

// Tags on every resource so we can track cost and find our resources.
var tags = {
  project: 'caa900'
  team: 'stockwise'
  env: 'dev'
}

resource plan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'caa900-stockwise-plan'
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
      appSettings: [
        {
          // Tells App Service to install requirements.txt when we deploy.
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ]
    }
  }
}

output webAppName string = webApp.name
output url string = 'https://${webApp.properties.defaultHostName}'
