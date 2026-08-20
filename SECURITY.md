# Security Policy

## Supported Versions

Only the latest release receives security fixes.

## Reporting a Vulnerability

Please report vulnerabilities privately via GitHub's
[private vulnerability reporting](https://github.com/andreasthell/ha-cw/security/advisories/new)
— do **not** open a public issue for security problems.

You can expect an initial response within a week. Please include steps to
reproduce and the affected version.

## Scope & Known Limitations

- This integration authenticates against the CheckWatt / EnergyInBalance
  cloud API with the user's email and password. Home Assistant stores config
  entry credentials unencrypted in its `.storage` directory — protect access
  to your HA instance and its backups accordingly. This is standard for HA
  integrations; the API offers no OAuth or API-key alternative.
- The API used is unofficial (reverse-engineered) and operated by
  CheckWatt AB. Vulnerabilities in the API itself should be reported to
  CheckWatt, not here.
- News items are fetched from a public, unauthenticated endpoint; no
  credentials or tokens are ever sent to it.
