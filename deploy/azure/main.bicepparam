// Example parameters for a manual `az deployment group create --parameters main.bicepparam`.
// deploy.sh writes its own parameter file; this one is for people who prefer to drive bicep by hand.
// Secrets come from the environment: OPENAI_API_KEY, KIN_ACCESS_TOKEN, ENTRA_CLIENT_SECRET.
using './main.bicep'

param name = 'kintsugi'
param location = 'eastus2'

// phase 1: deployApp=false; phase 2: deployApp=true with the image you built (az acr build)
param deployApp = true
param image = '<registry>.azurecr.io/kintsugi:latest'

param cpu = '2.0'
param memory = '4Gi'
param shareQuotaGb = 100

param provider = 'openai'
param openaiApiKey = readEnvironmentVariable('OPENAI_API_KEY', '')
param openaiBaseUrl = readEnvironmentVariable('OPENAI_BASE_URL', '')
param designerModel = 'gpt-6-astra'
param criticModel = 'gpt-6-astra'
param visionModel = 'gpt-6-astra'
param reasoningEffort = 'high'
param settingsLock = true

param authMode = 'easyauth'
param accessToken = readEnvironmentVariable('KIN_ACCESS_TOKEN', '')
param adminUsers = readEnvironmentVariable('KIN_ADMIN_USERS', '')
param easyauthProvider = 'aad'
param entraClientId = readEnvironmentVariable('ENTRA_CLIENT_ID', '')
param entraClientSecret = readEnvironmentVariable('ENTRA_CLIENT_SECRET', '')
// param entraTenantId = 'common'   // any Microsoft account instead of one tenant

param sessionGit = true
param maxImportMb = 500
