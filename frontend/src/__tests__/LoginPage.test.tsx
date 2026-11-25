import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import LoginPage from "@/app/login/page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}));

vi.mock("@/hooks/useProjectContext", () => ({
  useProjectContext: () => ({ refreshContext: vi.fn() }),
}));

describe("LoginPage validation & org-only access", () => {
  it("validates invalid email format via Zod before sending API calls", async () => {
    render(<LoginPage />);
    fireEvent.change(screen.getByLabelText(/Work Email/i), { target: { value: "invalid-email" } });
    fireEvent.change(screen.getByLabelText(/^Password$/i), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: /Sign In/i }));
    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent(/valid email/i);
    });
  });

  it("does not render any public registration or self-signup controls", () => {
    render(<LoginPage />);
    expect(screen.queryByRole("button", { name: /register/i })).toBeNull();
    expect(screen.queryByText(/Create Estimator Account/i)).toBeNull();
    expect(screen.getByText(/Self-registration is disabled/i)).toBeInTheDocument();
  });
});
