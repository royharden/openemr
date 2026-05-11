/**
 * OIDC configuration test fixtures.
 * Used in auth.test.ts for the logout-with-revocation test case.
 */

/** OIDC config that DOES advertise a revocation_endpoint — used to test the conditional revocation path. */
export const OIDC_CONFIG_RESPONSE_WITH_REVOCATION = {
  issuer: 'https://localhost:9300/oauth2/default',
  authorization_endpoint: 'https://localhost:9300/oauth2/default/authorize',
  token_endpoint: 'https://localhost:9300/oauth2/default/token',
  jwks_uri: 'https://localhost:9300/oauth2/default/jwks',
  introspection_endpoint: 'https://localhost:9300/oauth2/default/introspect',
  end_session_endpoint: 'https://localhost:9300/oauth2/default/logout',
  revocation_endpoint: 'https://localhost:9300/oauth2/default/revoke',
  response_types_supported: ['code'],
  subject_types_supported: ['public'],
  id_token_signing_alg_values_supported: ['RS256'],
  scopes_supported: ['openid', 'fhirUser', 'offline_access'],
  token_endpoint_auth_methods_supported: ['client_secret_basic', 'private_key_jwt'],
  claims_supported: ['sub', 'iss', 'fhirUser'],
}
