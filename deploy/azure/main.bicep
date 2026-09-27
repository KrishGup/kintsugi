// Kintsugi on Azure Container Apps — the whole stack in one deployment.
//
//   resource group
//   ├─ Log Analytics workspace           container logs (kin serve, uvicorn, OpenSCAD)
//   ├─ Storage account + Azure Files     /data: sessions, the settings file, previews
//   ├─ Container Registry (Basic)        the image, built with `az acr build`
//   ├─ User-assigned managed identity    pulls the image, reads the Key Vault secret
//   ├─ Key Vault (RBAC)                  OPENAI_API_KEY — never in a file on the share
//   ├─ Container Apps environment        with the file share attached as a storage
//   └─ Container App "kintsugi"          1 replica, 2 vCPU / 4 GiB, HTTPS ingress → :8000, /data mounted
//        └─ authConfigs/current          Easy Auth (Microsoft Entra / GitHub / Google) when authMode == 'easyauth'
//
// `deployApp=false` provisions everything but the app (so the registry exists before the first `az acr build`);
// `deployApp=true` with `image` set adds the app. deploy.sh runs both phases; docs/DEPLOY-AZURE.md explains every knob.

targetScope = 'resourceGroup'

// ---- naming & sizing ----------------------------------------------------------------------------------------------

@description('Base name for every resource. Lower-case letters, digits and hyphens; the app FQDN starts with it.')
@minLength(3)
@maxLength(20)
param name string = 'kintsugi'

@description('Region for everything (Container Apps, Files and Key Vault all exist in the same region).')
param location string = resourceGroup().location

@description('Deploy the Container App (needs `image`). false = infrastructure only, so the registry exists before the first build.')
param deployApp bool = false

@description('Full image reference, e.g. kintsugiacr123.azurecr.io/kintsugi:2026-10-01. Required when deployApp is true.')
param image string = ''

@description('vCPU for the one replica. OpenSCAD compiles and mesh checks are CPU-bound; 2 keeps previews snappy.')
@allowed(['1.0', '1.5', '2.0', '3.0', '4.0'])
param cpu string = '2.0'

@description('Memory for the one replica. Pair with cpu: 1.0→2Gi, 2.0→4Gi, 4.0→8Gi.')
@allowed(['2Gi', '3Gi', '4Gi', '6Gi', '8Gi'])
param memory string = '4Gi'

@description('Quota of the Azure Files share in GiB (sessions with photos and sheets run 20–80 MB each).')
@minValue(1)
@maxValue(5120)
param shareQuotaGb int = 100

@description('Tags stamped on every resource.')
param tags object = {
  app: 'kintsugi'
}

// ---- model ---------------------------------------------------------------------------------------------------------

@secure()
@description('OpenAI API key. Stored in Key Vault; the app reads it through its managed identity. Leave empty to paste it in the UI later (then set settingsLock=false).')
param openaiApiKey string = ''

@description('Optional OPENAI_BASE_URL (Azure OpenAI OpenAI-compatible endpoint or a gateway). Empty = api.openai.com.')
param openaiBaseUrl string = ''

@description('Provider the server starts with: openai (needs the key) or fake (scripted demo, no key, no cost).')
@allowed(['openai', 'fake'])
param provider string = 'openai'

param designerModel string = 'gpt-6-astra'
param criticModel string = 'gpt-6-astra'
param visionModel string = 'gpt-6-astra'

@allowed(['low', 'medium', 'high', 'max'])
param reasoningEffort string = 'high'

@description('Make the Settings dialog read-only (provider, key and models come only from this deployment). Recommended when a key is supplied.')
param settingsLock bool = true

// ---- who may use it ----------------------------------------------------------------------------------------------

@description('none = open to anyone who can reach the URL (dev only); token = one shared access code; easyauth = platform sign-in, sessions per user.')
@allowed(['none', 'token', 'easyauth'])
param authMode string = 'easyauth'

@secure()
@description('token mode: the shared access code (`openssl rand -hex 24`).')
param accessToken string = ''

@secure()
@description('Cookie-signing secret for token mode (defaults to the access code).')
param secretKey string = ''

@description('easyauth mode: comma-separated user ids (emails for Entra/Google, logins for GitHub; lower-case) who see every session and may change settings.')
param adminUsers string = ''

@description('easyauth mode: which sign-in the gate links to.')
@allowed(['aad', 'github', 'google'])
param easyauthProvider string = 'aad'

@description('Microsoft Entra app registration (client) id for Easy Auth. Empty = Entra sign-in not configured yet.')
param entraClientId string = ''

@secure()
param entraClientSecret string = ''

@description('Tenant that issues Entra sign-ins. "common" allows any Microsoft account; a tenant id restricts to that organisation.')
param entraTenantId string = tenant().tenantId

@description('Extra Entra object ids (users/groups) — informational; restrict sign-in with "assignment required" on the enterprise app instead.')
param entraAllowedAudiences array = []

param githubClientId string = ''
@secure()
param githubClientSecret string = ''

param googleClientId string = ''
@secure()
param googleClientSecret string = ''

// ---- storage behaviour ---------------------------------------------------------------------------------------------

@description('Keep a git history inside every session folder. Works on Azure Files (nobrl mount) but each commit costs a few hundred ms; set false if runs feel slow.')
param sessionGit bool = true

@description('Largest session archive the import endpoint accepts, MB.')
param maxImportMb int = 500

@description('The most one design run may spend on model calls, USD (0 = no cap). Set it on anything shared.')
param maxCostUsd string = '5'

@description('Heavy calls (run, iterate, export, photos, import…) per client per minute; 0 = off. A public demo box wants ~30.')
param ratePerMin int = 0

// ---- derived names -------------------------------------------------------------------------------------------------

var suffix = uniqueString(resourceGroup().id)
var plain = replace(name, '-', '')
var storageName = take('${plain}${suffix}', 24)
var acrName = take('${plain}acr${suffix}', 50)
var kvName = take('${name}-kv-${suffix}', 24)
var shareName = 'kintsugi-data'
var storageLinkName = 'kintsugi-data'
var openaiSecretName = 'openai-api-key'

var useKeyVaultKey = openaiApiKey != ''
var lockSettings = settingsLock && (useKeyVaultKey || provider == 'fake')

// role definition ids (built-in)
var roleAcrPull = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
var roleKvSecretsUser = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')

// ---- observability -------------------------------------------------------------------------------------------------

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
  }
}

// ---- storage: /data ------------------------------------------------------------------------------------------------

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource files 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    shareDeleteRetentionPolicy: { enabled: true, days: 14 }
  }
}

resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: files
  name: shareName
  properties: {
    shareQuota: shareQuotaGb
    enabledProtocols: 'SMB'
    accessTier: 'TransactionOptimized'
  }
}

// ---- registry ------------------------------------------------------------------------------------------------------

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: acrName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

// ---- identity ------------------------------------------------------------------------------------------------------

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${name}-id'
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, identity.id, roleAcrPull)
  scope: acr
  properties: {
    roleDefinitionId: roleAcrPull
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---- secrets -------------------------------------------------------------------------------------------------------

resource kv 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: kvName
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 30
    publicNetworkAccess: 'Enabled'
  }
}

resource kvSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = if (useKeyVaultKey) {
  parent: kv
  name: openaiSecretName
  properties: {
    value: openaiApiKey
    contentType: 'text/plain'
  }
}

resource kvRead 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(kv.id, identity.id, roleKvSecretsUser)
  scope: kv
  properties: {
    roleDefinitionId: roleKvSecretsUser
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---- container apps environment ------------------------------------------------------------------------------------

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

resource envStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: storageLinkName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: share.name
      accessMode: 'ReadWrite'
    }
  }
}

// ---- the app -------------------------------------------------------------------------------------------------------

module app 'app.bicep' = if (deployApp) {
  name: '${name}-app'
  params: {
    name: name
    location: location
    tags: tags
    image: image
    cpu: cpu
    memory: memory
    environmentId: env.id
    storageLinkName: envStorage.name
    identityId: identity.id
    registryServer: acr.properties.loginServer
    keyVaultSecretUri: useKeyVaultKey ? '${kv.properties.vaultUri}secrets/${openaiSecretName}' : ''
    openaiBaseUrl: openaiBaseUrl
    provider: provider
    designerModel: designerModel
    criticModel: criticModel
    visionModel: visionModel
    reasoningEffort: reasoningEffort
    settingsLock: lockSettings
    authMode: authMode
    accessToken: accessToken
    secretKey: secretKey
    adminUsers: adminUsers
    easyauthProvider: easyauthProvider
    entraClientId: entraClientId
    entraClientSecret: entraClientSecret
    entraTenantId: entraTenantId
    entraAllowedAudiences: entraAllowedAudiences
    githubClientId: githubClientId
    githubClientSecret: githubClientSecret
    googleClientId: googleClientId
    googleClientSecret: googleClientSecret
    sessionGit: sessionGit
    maxImportMb: maxImportMb
    maxCostUsd: maxCostUsd
    ratePerMin: ratePerMin
  }
  dependsOn: [
    acrPull
    kvRead
  ]
}

// ---- outputs -------------------------------------------------------------------------------------------------------

output resourceGroupName string = resourceGroup().name
output registryName string = acr.name
output registryLoginServer string = acr.properties.loginServer
output storageAccountName string = storage.name
output fileShareName string = share.name
output keyVaultName string = kv.name
output identityName string = identity.name
output identityClientId string = identity.properties.clientId
output environmentName string = env.name
output logAnalyticsWorkspaceId string = logs.id
output appName string = deployApp ? '${name}' : ''
output fqdn string = deployApp ? app!.outputs.fqdn : ''
output url string = deployApp ? 'https://${app!.outputs.fqdn}' : ''
output entraRedirectUri string = deployApp ? 'https://${app!.outputs.fqdn}/.auth/login/aad/callback' : ''
output githubRedirectUri string = deployApp ? 'https://${app!.outputs.fqdn}/.auth/login/github/callback' : ''
output googleRedirectUri string = deployApp ? 'https://${app!.outputs.fqdn}/.auth/login/google/callback' : ''
