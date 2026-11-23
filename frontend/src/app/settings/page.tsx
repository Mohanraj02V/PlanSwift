"use client";

import React, { useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest } from "@/services/api-client/client";

export default function SettingsPage() {
  const { user, refreshContext } = useProjectContext();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [statusMsg, setStatusMsg] = useState("");

  const handlePasswordChange = async (e: React.FormEvent) => {
    e.preventDefault();
    setStatusMsg("");
    try {
      await apiRequest("/auth/change-password/", {
        method: "POST",
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      setCurrentPassword("");
      setNewPassword("");
      setStatusMsg("Password updated successfully.");
      await refreshContext();
    } catch (err) {
      setStatusMsg(err instanceof Error ? err.message : "Failed to update password.");
    }
  };

  return (
    <AppShell title="Settings & Security">
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4 text-sm">
          <h2 className="font-semibold text-slate-900">Account Profile</h2>
          <dl className="mt-3 space-y-2 text-xs">
            <div>
              <dt className="text-slate-500">Email</dt>
              <dd className="font-mono font-semibold">{user?.email || "Not signed in"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">Full Name</dt>
              <dd>{user?.full_name || "—"}</dd>
            </div>
            <div>
              <dt className="text-slate-500">MFA Ready</dt>
              <dd>{user?.mfa_enabled ? "Enabled" : "Disabled (Ready)"}</dd>
            </div>
          </dl>
        </div>

        <form onSubmit={handlePasswordChange} className="space-y-3 rounded-lg border border-slate-200 bg-white p-4">
          <h2 className="text-sm font-semibold text-slate-900">Change Password</h2>
          {statusMsg && <div className="rounded bg-slate-100 p-2 text-xs">{statusMsg}</div>}
          <input
            type="password"
            placeholder="Current Password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <input
            type="password"
            placeholder="New Password (min 10 chars)"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            className="w-full rounded border border-slate-300 px-3 py-1.5 text-sm"
          />
          <button type="submit" className="rounded bg-blue-600 px-4 py-1.5 text-xs font-semibold text-white">
            Update Password
          </button>
        </form>
      </div>
    </AppShell>
  );
}
