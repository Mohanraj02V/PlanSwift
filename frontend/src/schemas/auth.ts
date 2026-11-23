import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(6, "Password must be at least 6 characters."),
});

export const registerSchema = z.object({
  email: z.string().email("Enter a valid email address."),
  password: z.string().min(10, "Password must be at least 10 characters."),
  full_name: z.string().min(1, "Full name is required."),
  job_title: z.string().optional(),
});

export const registerSourceSchema = z.object({
  project: z.string().uuid("Select a target project."),
  source_path: z.string().min(3, "Provide a valid local PlanSwift project path."),
});
