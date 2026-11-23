"use client";

import React, { createContext, useCallback, useContext, useEffect, useState } from "react";
import { apiRequest } from "@/services/api-client/client";
import { getAccessToken } from "@/services/authentication/auth";
import type { Organization, PaginatedResponse, Project, UserProfile } from "@/types/api";

interface ProjectContextValue {
  user: UserProfile | null;
  organizations: Organization[];
  projects: Project[];
  selectedProjectId: string;
  selectedProject: Project | null;
  setSelectedProjectId: (id: string) => void;
  loading: boolean;
  refreshContext: () => Promise<void>;
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

  const refreshContext = useCallback(async () => {
    if (!getAccessToken()) {
      setUser(null);
      setOrganizations([]);
      setProjects([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const [me, orgResp, projResp] = await Promise.all([
        apiRequest<UserProfile>("/auth/me/"),
        apiRequest<PaginatedResponse<Organization>>("/organizations/"),
        apiRequest<PaginatedResponse<Project>>("/projects/"),
      ]);
      setUser(me);
      setOrganizations(orgResp.results || []);
      const projList = projResp.results || [];
      setProjects(projList);
      const saved = typeof window !== "undefined" ? window.localStorage.getItem("vortexen_selected_project") : null;
      if (saved && projList.some((p) => p.id === saved)) {
        setSelectedProjectIdState(saved);
      } else if (projList.length > 0) {
        setSelectedProjectIdState(projList[0].id);
      }
    } catch {
      // Unauthenticated or expired session handled gracefully
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshContext();
  }, [refreshContext]);

  const selectedProject = projects.find((p) => p.id === selectedProjectId) ?? null;

  return (
    <ProjectContext.Provider
      value={{
        user,
        organizations,
        projects,
        selectedProjectId,
        selectedProject,
        setSelectedProjectId,
        loading,
        refreshContext,
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
