import React from "react";
import type { Metadata } from "next";
import { ProjectProvider } from "@/hooks/useProjectContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vortexen Estimator — PlanSwift Native Project Intelligence",
  description:
    "PlanSwift Native Project Extraction, Canonical Digital Project Model, and Provenance-Aware AI Estimation Platform",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <ProjectProvider>{children}</ProjectProvider>
      </body>
    </html>
  );
}
