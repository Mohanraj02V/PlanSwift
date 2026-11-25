"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { getCapabilities, getEffectiveRole } from "@/lib/rbac";
import { apiRequest } from "@/services/api-client/client";
import type {
  Organization,
  PaginatedResponse,
  Project,
  UserCapabilities,
  UserProfile,
  UserRole,
} from "@/types/api";

interface ProjectContextValue {
  user: UserProfile | null;
  role: UserRole | null;
  capabilities: UserCapabilities;
  organizations: Organization[];
  projects: Project[];
  selectedProjectId: string;
  selectedProject: Project | null;
  setSelectedProjectId: (id: string) => void;
  loading: boolean;
  refreshContext: () => Promise<void>;
  clearSession: () => void;
}

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProjectId, setSelectedProjectIdState] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);

  const setSelectedProjectId = (id: string) => {
    setSelectedProjectIdState(id);
    if (typeof window !== "undefined") {
      window.localStorage.setItem("vortexen_selected_project", id);
    }
  };

  const clearSession = useCallback(() => {
    setUser(null);
    setOrganizations([]);
    setProjects([]);
    setSelectedProjectIdState("");
  }, []);

  const refreshContext = useCallback(async () => {
    setLoading(true);
    try {
      const me = await apiRequest<UserProfile>("/auth/me/");
      setUser(me);
      const [orgResp, projResp] = await Promise.all([
        apiRequest<PaginatedResponse<Organization>>("/organizations/"),
        apiRequest<PaginatedResponse<Project>>("/projects/"),
      ]);
      setOrganizations(orgResp.results || []);
      const projList = projResp.results || [];
      setProjects(projList);
      const saved = typeof window !== "undefined" ? window.localStorage.getItem("vortexen_selected_project") : null;
      if (saved && projList.some((p) => p.id === saved)) {
        setSelectedProjectIdState(saved);
      } else if (projList.length > 0) {
        setSelectedProjectIdState(projList[0].id);
      } else {
        setSelectedProjectIdState("");
      }
    } catch {
      setUser(null);
      setOrganizations([]);
      setProjects([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshContext();
  }, [refreshContext]);

  const role = getEffectiveRole(user);
  const capabilities = getCapabilities(user);
  const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null;

  return (
    <ProjectContext.Provider
      value={{
        user,
        role,
        capabilities,
        organizations,
        projects,
        selectedProjectId,
        selectedProject,
        setSelectedProjectId,
        loading,
        refreshContext,
        clearSession,
      }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProjectContext() {
  const ctx = useContext(ProjectContext);
  if (!ctx) {
    throw new Error("useProjectContext must be used inside ProjectProvider");
  }
  return ctx;
}
