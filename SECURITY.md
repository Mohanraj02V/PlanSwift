# SECURITY.md — Application, Authentication, RBAC & Ingestion Controls

## 1. Authentication & Session Security
- **HttpOnly JWT Cookies + CSRF**: `CookieAwareJWTAuthentication` (`backend/apps/accounts/authentication.py`) issues `vortexen_access` (30m) and `vortexen_refresh` (7d) as `HttpOnly`, `SameSite=Lax`, `Secure` (in production) cookies and never stores long-lived JWTs in browser `localStorage` or JSON login payloads. Unsafe HTTP methods authenticated by cookie require a valid `X-CSRFToken` matching `csrftoken`.
- **Rotation & Immediate Revocation**: SimpleJWT rotates and blacklists refresh tokens (`ROTATE_REFRESH_TOKENS=True`, `BLACKLIST_AFTER_ROTATION=True`). `accounts.User.token_version` increments automatically on role updates, account deactivation, password resets, and password changes, invalidating active JWT cookies immediately.
- **No Public Registration**: `POST /api/v1/auth/register/` is disabled (`403 Forbidden` + audited `auth.register_blocked`). Accounts are created exclusively by active Organization Admins.
- **Throttling & Generic Errors**: Login (`auth_login`: `10/minute` DRF + `10r/m` Nginx) and refresh (`auth_refresh`: `30/minute` DRF + `30r/m` Nginx) are rate-limited. Failed logins log `auth.login_failed` and return `"Invalid email or password."` without user enumeration.
- **Password Policy**: Minimum 10 characters with Django similarity, common-password, and numeric-only validators plus optional `must_change_password` flag.

## 2. Organization-Controlled Three-Role RBAC
- **Roles**: Strictly `admin`, `estimator`, and `user` on `OrganizationMember`. Legacy roles were safely migrated (`owner->admin`, `reviewer/viewer/estimation_only->user`, `connector_agent->deactivated user`).
- **Admin Privilege Derivation**: `is_admin(user)` checks active `OrganizationMember(role="admin")` (with `is_superuser` reserved strictly for break-glass infrastructure maintenance). `is_staff=True` alone does NOT grant organization Admin access.
- **Last-Admin Protection**: Admins cannot demote or deactivate the sole remaining active Admin in any organization (`400 Bad Request`).
- **Centralized Enforcement**: `RolePolicyPermission` + per-viewset checks (`IsAdminOnly`, `IsEstimatorOrAdmin`, `IsOrgMember`) scope querysets by `get_user_org_ids()` / `get_user_admin_org_ids()`, blocking cross-tenant reads/writes (`403`/`404`) and logging denied attempts (`auth.permission_denied`).

## 3. File Upload, Archive & Parser Hardening
- **Upload-Only Ingestion**: `POST /api/v1/project-sources/` is disabled (`405`). Files upload strictly via `POST /api/v1/project-sources/upload/` into an isolated private `EXTRACTION_WORK_DIR/uploads` volume. Internal `source_path` values are never exposed in API responses.
- **Archive & XML Protection**: `archive_parser.py` and `xml_parser.py` block Zip Slip (`..`, drive letters, NUL bytes), Unix symlinks, nested executables/archives, excessive entries (`>10,000`), excessive uncompressed size (`>5 GiB`), zip bombs (`>100x` ratio), and XXE/DTD attacks (`resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False`).
- **CAD & BIM Resource Bounds**: File sizes (`512 MiB` DXF, `1 GiB` IFC/ZIP), entity count (`500,000`), block recursion (`32`), XREF external file isolation, and bounded IFC 3D geometry iterator threads/timeout prevent memory or CPU exhaustion.
- **Zero `eval()`**: Formulas and PascalScript strings are parsed lexically without dynamic execution.

## 4. Infrastructure & HTTP Security Headers
- `production.py` fails fast unless `SECRET_KEY` (`>=50` chars, non-default), explicit `ALLOWED_HOSTS` (no `*`), `CORS_ALLOWED_ORIGINS`, and `CSRF_TRUSTED_ORIGINS` are configured.
- `SecurityHeadersMiddleware` + `nginx/nginx.conf` enforce `Strict-Transport-Security`, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Permissions-Policy`, `Cross-Origin-Opener-Policy: same-origin`, and block public `/api/docs/` and `/api/schema/`.
- **Immutable Audit Trail**: `AuditLog` rejects updates and deletions (`ImmutableAuditError`), recording logins, permission denials, user administration, file uploads (user, filename, UTC date/time), extractions, and exports.
