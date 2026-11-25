import type { UserCapabilities, UserProfile, UserRole } from "@/types/api";

export function getEffectiveRole(user: UserProfile | null): UserRole | null {
  if (!user) return null;
  if (user.is_admin || user.is_superuser || user.primary_role === "admin") {
    return "admin";
  }
  if (user.primary_role === "estimator") {
    return "estimator";
  }
  if (user.primary_role === "user") {
    return "user";
  }
  const roles = (user.memberships || []).map((m) => m.role);
  if (roles.includes("admin")) return "admin";
  if (roles.includes("estimator")) return "estimator";
  if (roles.includes("user")) return "user";
  return null;
}

export function getCapabilities(user: UserProfile | null): UserCapabilities {
  const role = getEffectiveRole(user);
  const serverCaps = user?.capabilities;
  const isAdmin = role === "admin";
  const isEstimator = role === "estimator";
  const isMember = isAdmin || isEstimator || role === "user";

  return {
    can_view_estimator_workspace: serverCaps?.can_view_estimator_workspace ?? isMember,
    can_upload_source: serverCaps?.can_upload_source ?? (isAdmin || isEstimator),
    can_start_extraction: serverCaps?.can_start_extraction ?? (isAdmin || isEstimator),
    can_view_extraction_results: serverCaps?.can_view_extraction_results ?? isMember,
    can_manage_projects: serverCaps?.can_manage_projects ?? isAdmin,
    can_edit_project: serverCaps?.can_edit_project ?? isAdmin,
    can_delete_project: serverCaps?.can_delete_project ?? isAdmin,
    can_export: serverCaps?.can_export ?? isAdmin,
    can_manage_users: serverCaps?.can_manage_users ?? isAdmin,
    can_view_audit: serverCaps?.can_view_audit ?? isAdmin,
    can_access_admin_modules: serverCaps?.can_access_admin_modules ?? isAdmin,
  };
}

export function getDefaultRoute(user: UserProfile | null): string {
  const role = getEffectiveRole(user);
  if (!role) return "/login";
  if (role === "admin") return "/dashboard";
  return "/estimator";
}

export function canAccessRoute(user: UserProfile | null, pathname: string): boolean {
  const role = getEffectiveRole(user);
  if (!role) return pathname === "/login";
  if (role === "admin") return true;
  return pathname === "/estimator" || pathname.startsWith("/estimator/");
}

export function getRoleLabel(role: UserRole | null): string {
  if (role === "admin") return "Admin";
  if (role === "estimator") return "Estimator";
  if (role === "user") return "User (Read-Only)";
  return "Guest";
}
