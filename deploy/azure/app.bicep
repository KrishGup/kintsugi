// The Kintsugi Container App: one always-on replica with /data on Azure Files, secrets from Key Vault, optional Easy Auth.
// Deployed by main.bicep (deployApp=true); every parameter is documented there.

targetScope = 'resourceGroup'

param name string
param location string
param tags object
param image string
param cpu string
param memory string
param environmentId string
param storageLinkName string
param identityId string
param registryServer string
param keyVaultSecretUri string
param openaiBaseUrl string
param provider string
param designerModel string
param criticModel string
param visionModel string
param reasoningEffort string
param settingsLock bool
param authMode string
@secure()
param accessToken string
@secure()
param secretKey string
param adminUsers string
param easyauthProvider string
param entraClientId string
@secure()
param entraClientSecret string
param entraTenantId string
param entraAllowedAudiences array
param githubClientId string
@secure()
param githubClientSecret string
param googleClientId string
@secure()
param googleClientSecret string
param sessionGit bool
param maxImportMb int
param maxCostUsd string
param ratePerMin int

// ---- secrets: only the ones this configuration needs ----------------------------------------------------------------

var secretOpenai = keyVaultSecretUri != '' ? [
  {
    name: 'openai-api-key'
    keyVaultUrl: keyVaultSecretUri
    identity: identityId
  }
] : []
var secretToken = authMode == 'token' && accessToken != '' ? [
  {
    name: 'access-token'
    value: accessToken
  }
] : []
var secretSigning = secretKey != '' ? [
  {
    name: 'secret-key'
    value: secretKey
  }
] : []
var secretEntra = entraClientSecret != '' ? [
  {
    name: 'entra-client-secret'
    value: entraClientSecret
  }
] : []
var secretGithub = githubClientSecret != '' ? [
  {
    name: 'github-client-secret'
    value: githubClientSecret
  }
] : []
var secretGoogle = googleClientSecret != '' ? [
  {
    name: 'google-client-secret'
    value: googleClientSecret
  }
] : []
var secrets = concat(secretOpenai, secretToken, secretSigning, secretEntra, secretGithub, secretGoogle)

// ---- environment variables -----------------------------------------------------------------------------------------

var envBase = [
  { name: 'KIN_DATA_DIR', value: '/data' }
  { name: 'KIN_SESSIONS_DIR', value: '/data/sessions' }
  { name: 'KIN_ENV_FILE', value: '/data/.env' }
  { name: 'KIN_HOST', value: '0.0.0.0' }
  { name: 'KIN_PORT', value: '8000' }
  { name: 'KIN_PROXY_HEADERS', value: '1' }
  { name: 'KIN_COOKIE_SECURE', value: '1' }
  { name: 'KIN_PROVIDER', value: provider }
  { name: 'KIN_DESIGNER_MODEL', value: designerModel }
  { name: 'KIN_CRITIC_MODEL', value: criticModel }
  { name: 'KIN_VISION_MODEL', value: visionModel }
  { name: 'KIN_REASONING_EFFORT', value: reasoningEffort }
  { name: 'KIN_SETTINGS_LOCK', value: settingsLock ? '1' : '0' }
  { name: 'KIN_SESSION_GIT', value: sessionGit ? '1' : '0' }
  { name: 'KIN_MAX_IMPORT_MB', value: string(maxImportMb) }
  { name: 'KIN_MAX_COST_USD', value: maxCostUsd }
  { name: 'KIN_RATE_PER_MIN', value: string(ratePerMin) }
  { name: 'KIN_AUTH', value: authMode }
  { name: 'KIN_ADMIN_USERS', value: adminUsers }
  { name: 'KIN_EASYAUTH_PROVIDER', value: easyauthProvider }
  { name: 'KIN_OPENAI_TIMEOUT_S', value: '900' }
  { name: 'KIN_OPENAI_RETRIES', value: '6' }
  { name: 'PYTHONUNBUFFERED', value: '1' }
]
var envOpenai = keyVaultSecretUri != '' ? [ { name: 'OPENAI_API_KEY', secretRef: 'openai-api-key' } ] : []
var envBaseUrl = openaiBaseUrl != '' ? [ { name: 'OPENAI_BASE_URL', value: openaiBaseUrl } ] : []
var envToken = authMode == 'token' && accessToken != '' ? [ { name: 'KIN_ACCESS_TOKEN', secretRef: 'access-token' } ] : []
var envSigning = secretKey != '' ? [ { name: 'KIN_SECRET_KEY', secretRef: 'secret-key' } ] : []
var envVars = concat(envBase, envOpenai, envBaseUrl, envToken, envSigning)

// ---- the app -------------------------------------------------------------------------------------------------------

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identityId}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
        // one replica, one process: every request must reach the same container (runs and previews live in memory)
        stickySessions: { affinity: 'sticky' }
        traffic: [
          { latestRevision: true, weight: 100 }
        ]
      }
      registries: [
        {
          server: registryServer
          identity: identityId
        }
      ]
      secrets: secrets
    }
    template: {
      containers: [
        {
          name: 'kintsugi'
          image: image
          resources: {
            cpu: json(cpu)
            memory: memory
          }
          env: envVars
          volumeMounts: [
            {
              volumeName: 'data'
              mountPath: '/data'
            }
          ]
          probes: [
            {
              // the process is up in a few seconds; the first pull of a 900 MB image is what takes time (before this runs)
              type: 'Startup'
              httpGet: { path: '/api/health', port: 8000, scheme: 'HTTP' }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 10
              timeoutSeconds: 5
            }
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000, scheme: 'HTTP' }
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 8000, scheme: 'HTTP' }
              periodSeconds: 10
              failureThreshold: 3
              timeoutSeconds: 5
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'data'
          storageType: 'AzureFile'
          storageName: storageLinkName
          // nobrl: byte-range locks off (git + SQLite-style writes on SMB); mfsymlinks: git-friendly symlinks
          mountOptions: 'dir_mode=0777,file_mode=0777,uid=0,gid=0,mfsymlinks,nobrl,cache=strict,actimeo=1'
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 1
      }
    }
  }
}

// ---- Easy Auth -----------------------------------------------------------------------------------------------------
// The platform authenticates; the app still serves its shell and static assets to everyone and answers 401 (JSON) on
// /api/* without a signed-in principal — that is what draws the sign-in gate. So: AllowAnonymous here, enforcement in
// kintsugi/server/auth.py. Identity arrives in X-MS-CLIENT-PRINCIPAL-* headers.

var idpEntra = entraClientId != '' ? {
  azureActiveDirectory: {
    enabled: true
    registration: {
      clientId: entraClientId
      clientSecretSettingName: 'entra-client-secret'
      openIdIssuer: '${environment().authentication.loginEndpoint}${entraTenantId}/v2.0'
    }
    login: {
      loginParameters: [ 'scope=openid profile email' ]
    }
    validation: {
      allowedAudiences: concat([ entraClientId, 'api://${entraClientId}' ], entraAllowedAudiences)
    }
  }
} : {}
var idpGithub = githubClientId != '' ? {
  gitHub: {
    enabled: true
    registration: {
      clientId: githubClientId
      clientSecretSettingName: 'github-client-secret'
    }
    login: {
      scopes: [ 'read:user', 'user:email' ]
    }
  }
} : {}
var idpGoogle = googleClientId != '' ? {
  google: {
    enabled: true
    registration: {
      clientId: googleClientId
      clientSecretSettingName: 'google-client-secret'
    }
    login: {
      scopes: [ 'openid', 'profile', 'email' ]
    }
  }
} : {}
var identityProviders = union(idpEntra, idpGithub, idpGoogle)
var redirectProvider = easyauthProvider == 'aad' ? 'azureActiveDirectory' : easyauthProvider == 'github' ? 'gitHub' : 'google'

resource authConfig 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (authMode == 'easyauth' && !empty(identityProviders)) {
  parent: app
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'AllowAnonymous'
      redirectToProvider: redirectProvider
    }
    httpSettings: {
      requireHttps: true
      forwardProxy: { convention: 'Standard' }
      routes: { apiPrefix: '/.auth' }
    }
    login: {
      preserveUrlFragmentsForLogins: true
      cookieExpiration: { convention: 'FixedTime', timeToExpiration: '08:00:00' }
      allowedExternalRedirectUrls: []
    }
    identityProviders: identityProviders
  }
}

output fqdn string = app.properties.configuration.ingress.fqdn
output appId string = app.id
output latestRevision string = app.properties.latestRevisionName
