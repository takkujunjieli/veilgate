# Security

VeilGate is a pre-production project. The phase-one guarantee is policy-enforced CSV
field publication under the assumptions in `docs/threat-model.md`.

Do not include credentials, customer files, raw traces, or private paths in public
issues. Until a private reporting channel is configured, contact the repository
owner through an existing private channel and use synthetic reproductions.

Security-sensitive changes require regression tests and review of the authorization
and publication boundaries. No independent audit or compliance certification has
been performed. See `docs/release-checklist.md` before deployment.
