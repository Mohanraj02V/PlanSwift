"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useProjectContext } from "@/hooks/useProjectContext";
import { getDefaultRoute } from "@/lib/rbac";

export default function HomePage() {
  const router = useRouter();
  const { user, loading } = useProjectContext();

  useEffect(() => {
    if (loading) return;
    router.replace(getDefaultRoute(user));
  }, [loading, user, router]);

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-3 bg-[#f8fafc] text-sm font-medium text-[#475569]">
      <img src="/brand/vortexen-mark.png" alt="Vortexen" className="h-10 w-10 object-contain" />
      <span>Loading Vortexen Estimator...</span>
    </div>
  );
}
