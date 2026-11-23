# SECURITY.md — Application, Ingestion & Multi-Tenant Security Controls

## 1. Authentication & Session Security
- **JWT + Refresh Rotation**: `djangorestframework-simplejwt` configured with 30-minute access tokens, 7-day refresh tokens, `ROTATE_REFRESH_TOKENS=True`, and `BLACKLIST_AFTER_ROTATION=True`.
- **Logout Revocation**: `POST /api/v1/auth/logout/` blacklists the supplied refresh token and logs an immutable `auth.logout` audit event.
- **Password Policy**: Django validators enforce minimum length >= 10, similarity, common-password, and numeric-only rejection.
- **MFA-Ready Schema**: `accounts.User` includes `mfa_enabled` and `mfa_secret_ref`.

## 2. Authorization & Multi-Tenant Isolation
- **RBAC Roles**: `owner`, `admin`, `estimator`, `reviewer`, `viewer`, `connector_agent` via `OrganizationMember`.
- **Queryset + Object Scoping**: Every tenant endpoint filters by `get_user_org_ids(request.user)` AND enforces `IsOrgMember`, `IsOrgEditor`, `IsOrgReviewerOrEditor`, or `IsOrgAdminOrOwner` at object level (`404`/`403` on cross-tenant access).
- **Immutable Audit Logs**: `AuditLog.save()` (non-adding) and `AuditLog.delete()` raise `ImmutableAuditError`.

## 3. Archive & XML Hardening (`extraction_engine/parsers/`)
- **Allowed Source Roots**: `ALLOWED_SOURCE_ROOTS` restricts local filesystem ingestion paths so arbitrary host files cannot be probed via API.
- **Zip Slip & Symlinks**: `validate_archive_member_path` rejects `..`, leading `/`, Windows drive letters, and NUL bytes; `_is_zip_symlink` rejects Unix symlinks.
- **ZIP Bomb & Executable Limits**: Rejects archives exceeding `max_archive_entries` (`10,000`), `max_uncompressed_bytes` (`5 GiB`), `max_compression_ratio` (`100x` above 10 MB), nested archive extensions, or `.exe`/`.dll`/`.bat`/`.ps1` files.
- **XXE / DTD Prohibition**: `xml_parser.py` uses `lxml.etree.iterparse(..., resolve_entities=False, no_network=True, load_dtd=False)`; `geometry_parser.py` uses `defusedxml.ElementTree.fromstring`.
- **Zero `eval()`**: PlanSwift formulas and PascalScript `Expression="-1"` blocks are lexed statically and never executed.

## 4. Windows COM Connector Security
- Optional `CONNECTOR_SHARED_TOKEN` (`X-Connector-Token`) + JWT authentication + `X-Payload-SHA256` integrity digest + `CONNECTOR_REQUIRE_TLS` enforcement in staging/production.
- Secret keys, DB URLs, and AI credentials are strictly loaded from environment variables (never hardcoded).
