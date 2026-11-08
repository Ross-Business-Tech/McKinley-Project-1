import type { Metadata } from "next";

import { StaffConsole } from "@/components/staff/StaffConsole";

export const metadata: Metadata = {
  title: "Staff and demo console | McKinley Help (prototype)",
  description: "Decision diagnostics, saved prototype requests, workflow coverage and evaluations.",
};

export default function StaffPage() {
  return <StaffConsole />;
}
