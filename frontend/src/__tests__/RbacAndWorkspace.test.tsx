import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "@/components/layout/AppShell";
import EstimatorWorkspacePage from "@/app/estimator/page";
import { canAccessRoute, getCapabilities, getDefaultRoute } from "@/lib/rbac";
import type { UserProfile, UserRole } from "@/types/api";

const replaceMock = vi.fn();
let currentPathname = "/estimator";
let mockUser: UserProfile | null = null;

vi.mock("next/navigation", () => ({
  usePathname: () => currentPathname,
  useRouter: () => ({ push: vi.fn(), replace: replaceMock }),
}));

vi.mock("@/services/api-client/client", () => ({
  apiRequest: vi.fn().mockResolvedValue({ count: 0, results: [] }),
  uploadProjectZipWithProgress: vi.fn(),
}));

function makeUser(role: UserRole): UserProfile {
  return {
    id: `uid-${role}`,
    email: `${role}@vortexen.com`,
    full_name: `Test ${role}`,
    job_title: role,
    is_admin: role === "admin",
    primary_role: role,
    memberships: [{ organization_id: "org-1", organization_name: "Vortexen", role }],
    mfa_enabled: false,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
  };
}

vi.mock("@/hooks/useProjectContext", () => ({
  useProjectContext: () => ({
    user: mockUser,
    role: mockUser?.primary_role ?? null,
    capabilities: getCapabilities(mockUser),
    organizations: [{ id: "org-1", name: "Vortexen", slug: "vortexen", is_active: true, my_role: mockUser?.primary_role ?? null, created_at: "" }],
    projects: [
      {
        id: "proj-1",
        organization: "org-1",
        organization_name: "Vortexen",
        name: "Tower Firestop",
        native_guid: "{1}",
        description: "",
        notes: "",
        project_type: "",
        measurement_system: "Metric",
        excel_workbook_connected: false,
        xml_encoding: "UTF-8",
        native_timestamp_raw: "",
        current_version: null,
        object_count: 10,
        page_count: 2,
        created_at: "",
        updated_at: "",
      },
    ],
    selectedProjectId: "proj-1",
    selectedProject: {
      id: "proj-1",
      organization: "org-1",
      organization_name: "Vortexen",
      name: "Tower Firestop",
      native_guid: "{1}",
      description: "",
      notes: "",
      project_type: "",
      measurement_system: "Metric",
      excel_workbook_connected: false,
      xml_encoding: "UTF-8",
      native_timestamp_raw: "",
      current_version: null,
      object_count: 10,
      page_count: 2,
      created_at: "",
      updated_at: "",
    },
    setSelectedProjectId: vi.fn(),
    loading: false,
    refreshContext: vi.fn(),
    clearSession: vi.fn(),
  }),
}));

describe("Three-Role RBAC Navigation, Route Guards & Estimator Workspace", () => {
  beforeEach(() => {
    replaceMock.mockReset();
    currentPathname = "/estimator";
  });

  it("maps default routes and allowed paths strictly by role", () => {
    const admin = makeUser("admin");
    const estimator = makeUser("estimator");
    const readonlyUser = makeUser("user");

    expect(getDefaultRoute(admin)).toBe("/dashboard");
    expect(getDefaultRoute(estimator)).toBe("/estimator");
    expect(getDefaultRoute(readonlyUser)).toBe("/estimator");

    expect(canAccessRoute(admin, "/users")).toBe(true);
    expect(canAccessRoute(admin, "/estimation")).toBe(true);
    expect(canAccessRoute(estimator, "/estimator")).toBe(true);
    expect(canAccessRoute(estimator, "/users")).toBe(false);
    expect(canAccessRoute(estimator, "/estimation")).toBe(false);
    expect(canAccessRoute(readonlyUser, "/estimator")).toBe(true);
    expect(canAccessRoute(readonlyUser, "/dashboard")).toBe(false);
  });

  it("Admin sees full navigation including Users, Estimation & Estimator Workspace", () => {
    mockUser = makeUser("admin");
    currentPathname = "/dashboard";
    render(
      <AppShell title="Dashboard">
        <div>Admin Content</div>
      </AppShell>
    );
    expect(screen.getByText("Estimator Workspace")).toBeInTheDocument();
    expect(screen.getByText("Users (Admin)")).toBeInTheDocument();
    expect(screen.getByText("Audit Trail")).toBeInTheDocument();
    expect(screen.getByText("Estimation & Quote")).toBeInTheDocument();
    expect(screen.getByText("Admin Content")).toBeInTheDocument();
  });

  it("Estimator sees ONLY Estimator Workspace nav, can upload, sees zero export/delete/edit controls, and redirects off Admin routes", async () => {
    mockUser = makeUser("estimator");
    currentPathname = "/estimator";
    render(<EstimatorWorkspacePage />);
    expect(screen.getByText("Estimator Workspace")).toBeInTheDocument();
    expect(screen.queryByText("Users (Admin)")).toBeNull();
    expect(screen.queryByText("Audit Trail")).toBeNull();
    expect(screen.queryByText("Estimation & Quote")).toBeNull();
    expect(screen.getByRole("button", { name: /Upload & Process File/i })).toBeInTheDocument();
    expect(screen.queryByText(/Export Excel/i)).toBeNull();
    expect(screen.queryByText(/PDF Quotation/i)).toBeNull();

    // Direct navigation to restricted route triggers redirect without rendering restricted children
    currentPathname = "/users";
    render(
      <AppShell title="Users">
        <div>Secret Admin Data</div>
      </AppShell>
    );
    expect(screen.queryByText("Secret Admin Data")).toBeNull();
    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/estimator");
    });
  });

  it("User (Read-Only) sees ONLY Estimator Workspace, zero upload controls, zero export controls, and redirects off restricted routes", async () => {
    mockUser = makeUser("user");
    currentPathname = "/estimator";
    render(<EstimatorWorkspacePage />);
    expect(screen.getByText(/Read-Only User Access/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Upload & Process File/i })).toBeNull();
    expect(screen.queryByLabelText(/Upload project source file/i)).toBeNull();
    expect(screen.queryByText(/Export Excel/i)).toBeNull();
    expect(screen.queryByText("Users (Admin)")).toBeNull();

    currentPathname = "/estimation";
    render(
      <AppShell title="Estimation">
        <div>Commercial Quotes</div>
      </AppShell>
    );
    expect(screen.queryByText("Commercial Quotes")).toBeNull();
    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/estimator");
    });
  });
});
