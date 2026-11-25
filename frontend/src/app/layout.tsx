import React from "react";
import type { Metadata } from "next";
import { ProjectProvider } from "@/hooks/useProjectContext";
import "./globals.css";

export const metadata: Metadata = {
  title: "Vortexen Estimator — PlanSwift, DXF & IFC Engineering Platform",
  description:
    "Official Vortexen Engineering Workspace for PlanSwift, DXF, and IFC extraction, quantity verification, and commercial quotations.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-[#f8fafc] text-[#0f172a] antialiased">
        <ProjectProvider>{children}</ProjectProvider>
      </body>
    </html>
  );
}
