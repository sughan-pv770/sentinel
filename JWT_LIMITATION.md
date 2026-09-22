# JWT Signature Verification Limitation

In this Hackathon MVP, we rely on the `x-identity-id` header for identity assertion because a full Identity Provider (IdP) integration was out of scope. 
In production, SentinelX would strictly require a valid JWT `Authorization: Bearer <token>`, and verify its signature using the IdP's public keys (JWKS) before proceeding to feature extraction.

Basic replay protection via `x-nonce` has been implemented in both the live gateway and simulator endpoints.
