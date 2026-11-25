"use client";

import React, { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/AppShell";
import { ProvenanceBadge } from "@/components/provenance-badge/ProvenanceBadge";
import { useProjectContext } from "@/hooks/useProjectContext";
import { apiRequest, downloadEstimationDocument } from "@/services/api-client/client";
import type { EstimationResultRow, EstimationSession, PaginatedResponse, QuotationMetadata } from "@/types/api";

function linesToText(val?: string[] | string): string {
  if (Array.isArray(val)) return val.join("\n");
  return val || "";
}

function textToLines(val: string): string[] {
  return val
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function EstimationPage() {
  const { capabilities, selectedProjectId } = useProjectContext();
  const [sessions, setSessions] = useState<EstimationSession[]>([]);
  const [rows, setRows] = useState<EstimationResultRow[]>([]);
  const [quoteMeta, setQuoteMeta] = useState<QuotationMetadata>({});
  const [showQuotationForm, setShowQuotationForm] = useState(true);
  const [saving, setSaving] = useState(false);
  const [downloading, setDownloading] = useState<"excel" | "pdf" | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const syncFromSession = (sess: EstimationSession | undefined) => {
    if (!sess) {
      setRows([]);
      setQuoteMeta({});
      return;
    }
    setRows((sess.results || []).filter((r) => (r.native_class || "").trim().toLowerCase() !== "folder"));
    setQuoteMeta(sess.quotation_defaults || {});
  };

  const loadSessions = () => {
    const q = selectedProjectId ? `?project=${selectedProjectId}` : "";
    apiRequest<PaginatedResponse<EstimationSession>>(`/estimation/sessions/${q}`)
      .then((res) => {
        const list = res.results || [];
        setSessions(list);
        syncFromSession(list[0]);
      })
      .catch(() => {});
  };

  useEffect(() => {
    loadSessions();
  }, [selectedProjectId]);

  const active = sessions[0];

  const handleGenerate = async () => {
    if (!selectedProjectId) return;
    setError("");
    setMessage("");
    try {
      await apiRequest("/estimation/sessions/", {
        method: "POST",
        body: JSON.stringify({ project: selectedProjectId }),
      });
      setMessage("Generated deterministic takeoff rollup.");
      loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate estimation.");
    }
  };

  const handleApprove = async (id: string) => {
    setError("");
    setMessage("");
    try {
      await apiRequest(`/estimation/sessions/${id}/approve/`, { method: "POST" });
      setMessage("Estimation approved.");
      loadSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Approval failed.");
    }
  };

  const updateRowField = (rowId: string, field: "unit_cost" | "quantity" | "object_name", rawVal: string) => {
    setRows((prev) =>
      prev.map((r) => {
        if (r.id !== rowId) return r;
        const next = { ...r };
        if (field === "object_name") next.object_name = rawVal;
        else if (field === "quantity") {
          const q = Number(rawVal);
          next.quantity = Number.isFinite(q) ? q : 0;
        } else if (field === "unit_cost") {
          next.unit_cost = rawVal === "" ? null : Number(rawVal);
        }
        const qty = Number(next.quantity || 0);
        const rate = Number(next.unit_cost ?? 0);
        next.total_cost = Number((qty * rate).toFixed(2));
        return next;
      })
    );
  };

  const handleSaveQuotation = async () => {
    if (!active) return;
    setSaving(true);
    setError("");
    setMessage("");
    try {
      const updated = await apiRequest<EstimationSession>(`/estimation/sessions/${active.id}/update-quotation/`, {
        method: "PATCH",
        body: JSON.stringify({
          quotation: quoteMeta,
          items: rows.map((r) => ({
            id: r.id,
            object_name: r.object_name,
            quantity: r.quantity,
            unit: r.unit,
            unit_cost: r.unit_cost,
          })),
        }),
      });
      syncFromSession(updated);
      setMessage("Saved unit rates and Vortexen quotation template details.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save quotation changes.");
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = async (kind: "excel" | "pdf") => {
    if (!active) return;
    setDownloading(kind);
    setError("");
    setMessage("");
    try {
      await apiRequest(`/estimation/sessions/${active.id}/update-quotation/`, {
        method: "PATCH",
        body: JSON.stringify({
          quotation: quoteMeta,
          items: rows.map((r) => ({
            id: r.id,
            object_name: r.object_name,
            quantity: r.quantity,
            unit: r.unit,
            unit_cost: r.unit_cost,
          })),
        }),
      });
      const blob = await downloadEstimationDocument(active.id, kind, quoteMeta as Record<string, unknown>);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = kind === "excel" ? `Vortexen_BOQ_${active.id}.xlsx` : `Vortexen_Quotation_${active.id}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setMessage(kind === "excel" ? "Downloaded Excel BOQ workbook (.xlsx)." : "Downloaded Vortexen PDF Quotation (.pdf).");
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to export ${kind.toUpperCase()}.`);
    } finally {
      setDownloading(null);
    }
  };

  const currency = quoteMeta.currency || "AED";
  const vatPct = Number(quoteMeta.vat_percent ?? 5);
  const subtotal = rows.reduce((acc, r) => {
    const t = r.total_cost != null ? Number(r.total_cost) : Number(r.quantity || 0) * Number(r.unit_cost || 0);
    return acc + (Number.isFinite(t) ? t : 0);
  }, 0);
  const vatAmt = subtotal * (vatPct / 100);
  const grandTotal = subtotal + vatAmt;

  return (
    <AppShell title="Estimation, Excel Export & Vortexen PDF Quotation">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={handleGenerate}
            className="rounded-lg bg-[#0052cc] px-4 py-2 text-xs font-semibold text-white hover:bg-[#003d99]"
          >
            Generate Deterministic Takeoff Rollup
          </button>
          {active && (
            <button
              type="button"
              onClick={() => setShowQuotationForm((v) => !v)}
              className="rounded border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
            >
              {showQuotationForm ? "Hide Quotation Template" : "Customize Quotation Template"}
            </button>
          )}
        </div>

        {active && (
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={saving}
              onClick={handleSaveQuotation}
              className="rounded border border-blue-600 bg-white px-3 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-50 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Save Rates & Details"}
            </button>
            <button
              type="button"
              disabled={downloading !== null}
              onClick={() => handleDownload("excel")}
              className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
            >
              {downloading === "excel" ? "Exporting..." : "Export Excel (.xlsx)"}
            </button>
            <button
              type="button"
              disabled={downloading !== null}
              onClick={() => handleDownload("pdf")}
              className="rounded bg-indigo-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {downloading === "pdf" ? "Generating PDF..." : "Download Vortexen PDF Quotation"}
            </button>
            {capabilities.can_access_admin_modules && active.status !== "approved" && (
              <button
                type="button"
                onClick={() => handleApprove(active.id)}
                className="rounded border border-emerald-600 px-3 py-1.5 text-xs font-semibold text-emerald-700 hover:bg-emerald-50"
              >
                Approve ({active.name})
              </button>
            )}
          </div>
        )}
      </div>

      {error && <div className="mb-4 rounded bg-rose-50 p-3 text-xs text-rose-700">{error}</div>}
      {message && <div className="mb-4 rounded bg-emerald-50 p-3 text-xs text-emerald-800">{message}</div>}

      {active ? (
        <div className="space-y-5">
          {showQuotationForm && (
            <div className="space-y-4 rounded-lg border border-slate-200 bg-white p-4">
              <div className="flex items-center justify-between">
                <h2 className="text-sm font-semibold text-slate-900">
                  Dynamic Vortexen Commercial Quotation Template
                </h2>
                <span className="font-mono text-[11px] text-slate-500">
                  Ref: {quoteMeta.reference || "VDIS/FM/..."}
                </span>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Date</label>
                  <input
                    type="text"
                    value={quoteMeta.date || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, date: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Reference</label>
                  <input
                    type="text"
                    value={quoteMeta.reference || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, reference: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">To (Client Company)</label>
                  <input
                    type="text"
                    value={quoteMeta.to_client || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, to_client: e.target.value })}
                    placeholder="M/s. Jones Engineering"
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Project Contact Person</label>
                  <input
                    type="text"
                    value={quoteMeta.contact_person || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, contact_person: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Contact Number</label>
                  <input
                    type="text"
                    value={quoteMeta.contact_number || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, contact_number: e.target.value })}
                    placeholder="+971 55 ..."
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Project Location</label>
                  <input
                    type="text"
                    value={quoteMeta.project_location || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, project_location: e.target.value })}
                    placeholder="Abu Dhabi - U.A.E."
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-[11px] font-medium text-slate-600">Subject</label>
                  <input
                    type="text"
                    value={quoteMeta.subject || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, subject: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div>
                    <label className="block text-[11px] font-medium text-slate-600">Currency</label>
                    <input
                      type="text"
                      value={quoteMeta.currency || "AED"}
                      onChange={(e) => setQuoteMeta({ ...quoteMeta, currency: e.target.value })}
                      className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-slate-600">VAT %</label>
                    <input
                      type="number"
                      step="0.5"
                      value={quoteMeta.vat_percent ?? 5}
                      onChange={(e) => setQuoteMeta({ ...quoteMeta, vat_percent: Number(e.target.value) })}
                      className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-medium text-slate-600">Rate Header</label>
                    <input
                      type="text"
                      value={quoteMeta.rate_column_label || `Rate (${currency})`}
                      onChange={(e) => setQuoteMeta({ ...quoteMeta, rate_column_label: e.target.value })}
                      className="mt-1 w-full rounded border border-slate-300 px-2 py-1.5 text-xs"
                    />
                  </div>
                </div>
                <div className="md:col-span-2">
                  <label className="block text-[11px] font-medium text-slate-600">Contract Period</label>
                  <input
                    type="text"
                    value={quoteMeta.contract_period || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, contract_period: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Validity</label>
                  <input
                    type="text"
                    value={quoteMeta.validity || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, validity: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Signatory Name</label>
                  <input
                    type="text"
                    value={quoteMeta.signatory_name || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, signatory_name: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Signatory Title</label>
                  <input
                    type="text"
                    value={quoteMeta.signatory_title || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, signatory_title: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Signatory Phone</label>
                  <input
                    type="text"
                    value={quoteMeta.signatory_phone || ""}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, signatory_phone: e.target.value })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
              </div>

              <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">General Notes (one per line)</label>
                  <textarea
                    rows={3}
                    value={linesToText(quoteMeta.general_notes)}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, general_notes: textToLines(e.target.value) })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Payment Terms (one per line)</label>
                  <textarea
                    rows={3}
                    value={linesToText(quoteMeta.payment_terms)}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, payment_terms: textToLines(e.target.value) })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Scope of Work Includes (one per line)</label>
                  <textarea
                    rows={2}
                    value={linesToText(quoteMeta.scope_includes)}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, scope_includes: textToLines(e.target.value) })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div>
                  <label className="block text-[11px] font-medium text-slate-600">Exclusions (one per line)</label>
                  <textarea
                    rows={2}
                    value={linesToText(quoteMeta.exclusions)}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, exclusions: textToLines(e.target.value) })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
                <div className="md:col-span-2">
                  <label className="block text-[11px] font-medium text-slate-600">Terms &amp; Conditions (one per line)</label>
                  <textarea
                    rows={4}
                    value={linesToText(quoteMeta.terms_conditions)}
                    onChange={(e) => setQuoteMeta({ ...quoteMeta, terms_conditions: textToLines(e.target.value) })}
                    className="mt-1 w-full rounded border border-slate-300 px-2.5 py-1.5 text-xs"
                  />
                </div>
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-[11px] font-medium text-slate-500">Total Amount (As Discussed)</div>
              <div className="mt-1 font-mono text-lg font-bold text-slate-900">
                {subtotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {currency}
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white p-3">
              <div className="text-[11px] font-medium text-slate-500">VAT ({vatPct}%)</div>
              <div className="mt-1 font-mono text-lg font-bold text-slate-900">
                {vatAmt.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 3 })} {currency}
              </div>
            </div>
            <div className="rounded-lg border border-blue-200 bg-blue-50/70 p-3">
              <div className="text-[11px] font-semibold text-blue-900">Total Amount with VAT</div>
              <div className="mt-1 font-mono text-lg font-bold text-blue-900">
                {grandTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {currency}
              </div>
            </div>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-full divide-y divide-slate-200 text-left text-xs">
              <thead className="bg-slate-50 font-semibold text-slate-600">
                <tr>
                  <th className="px-3 py-2">SL : NO</th>
                  <th className="px-3 py-2">Description / Takeoff Object</th>
                  <th className="px-3 py-2">Class</th>
                  <th className="px-3 py-2">Unit / Qty</th>
                  <th className="px-3 py-2">Unit Rate ({currency})</th>
                  <th className="px-3 py-2">Total Amount ({currency})</th>
                  <th className="px-3 py-2">Provenance</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {rows.map((r, idx) => {
                  const lineTotal =
                    r.total_cost != null ? Number(r.total_cost) : Number(r.quantity || 0) * Number(r.unit_cost || 0);
                  return (
                    <tr key={r.id}>
                      <td className="px-3 py-2 font-mono text-slate-600">A.{idx + 1}</td>
                      <td className="px-3 py-2">
                        <input
                          type="text"
                          value={r.object_name}
                          onChange={(e) => updateRowField(r.id, "object_name", e.target.value)}
                          className="w-full min-w-[200px] rounded border border-slate-200 px-2 py-1 font-medium text-slate-900 focus:border-blue-500 focus:outline-none"
                        />
                      </td>
                      <td className="px-3 py-2 font-mono text-slate-600">{r.native_class}</td>
                      <td className="px-3 py-2 font-mono font-semibold">
                        {r.quantity} {r.unit}
                      </td>
                      <td className="px-3 py-2">
                        <input
                          type="number"
                          step="0.01"
                          value={r.unit_cost ?? ""}
                          onChange={(e) => updateRowField(r.id, "unit_cost", e.target.value)}
                          placeholder="0.00"
                          className="w-24 rounded border border-slate-300 px-2 py-1 text-right font-mono text-xs"
                        />
                      </td>
                      <td className="px-3 py-2 font-mono font-bold text-slate-900">
                        {lineTotal.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </td>
                      <td className="px-3 py-2">
                        <ProvenanceBadge status={r.source_status} />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">
          Click Generate Deterministic Takeoff Rollup to compute SQL-verified quantities, then export Excel or Vortexen PDF Quotation.
        </div>
      )}
    </AppShell>
  );
}
