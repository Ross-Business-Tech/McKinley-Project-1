/** F1-F9 implementation status shown in the staff console. Mirrors docs/workflows/traceability.md. */
export type CoverageStatus = "working" | "simulated" | "partial" | "unavailable";

export interface Coverage {
  id: string;
  name: string;
  status: CoverageStatus;
  works: string;
  blockedOn: string;
}

export const COVERAGE: Coverage[] = [
  {
    id: "F1",
    name: "Phone and voice support",
    status: "unavailable",
    works: "Nothing channel-specific. The same conversation logic is tested in text.",
    blockedOn: "Telephony and speech services; I-01 disclosure and recording consent (legal); I-02 to I-04; D-01 to D-03",
  },
  {
    id: "F2",
    name: "SMS and email",
    status: "simulated",
    works: "Channel-specific reply rules (I-07 draft) and opt-out keywords (I-06 draft) via the API. No message is sent.",
    blockedOn: "SMS/email gateways; opt-in consent records and approved opt-out wording (I-06); D-04",
  },
  {
    id: "F3",
    name: "Caller type classification",
    status: "partial",
    works: "Audience comes from the demo sign-in, never from what the person types. Unmatched residents and vendors get public information only.",
    blockedOn: "Real verification method and permission matrix (I-10, I-11); vendor list (D-06)",
  },
  {
    id: "F4",
    name: "Property and leasing FAQs",
    status: "partial",
    works: "Answers only approved entries (housing vouchers). Every other topic says it isn't approved yet. Prices and availability are never quoted.",
    blockedOn: "Approved knowledge base per property (D-07); live pricing and availability (D-08); legal-approved Fair Housing rules (I-13)",
  },
  {
    id: "F5",
    name: "Tour scheduling",
    status: "simulated",
    works: "Collects city or community, days and time of day; preferences can change midway; saves a tour request, never a booking.",
    blockedOn: "Tour calendar (D-09); CRM lead record (D-10); required tour questions (I-15); reminders and consent (I-16)",
  },
  {
    id: "F6",
    name: "Maintenance request intake",
    status: "working",
    works: "Emergency first for every audience; asks one question at a time; reuses what's on the account; read-back before sending.",
    blockedOn: "NOT production ready: emergency detection misses some immediate dangers (independent holdout: 64.5% full alert). Approved emergency list and safety text (I-17, I-18); categories and fields (I-19); troubleshooting guides (I-20); on-call (D-03)",
  },
  {
    id: "F7",
    name: "Create and update work orders",
    status: "simulated",
    works: "Confirmed requests are saved to the prototype store as 'submitted for staff review'. Changes and cancellations go to staff.",
    blockedOn: "Yardi work-order write access (D-11); approval rules and approvers (I-21, D-12); change rules (I-24); templates (I-22)",
  },
  {
    id: "F8",
    name: "Request status lookup",
    status: "partial",
    works: "Signed-in residents see open items from synthetic history and the prototype store. No repair times are given.",
    blockedOn: "Live work-order status (D-11); target timing and overdue rules (I-23); notifications with consent and quiet hours (D-13)",
  },
  {
    id: "F9",
    name: "Human handoff and escalation",
    status: "simulated",
    works: "Structured note with team, priority and summary; the person confirms before it is saved to the prototype staff queue. Emergencies are saved immediately.",
    blockedOn: "Routing table (I-26); response-time promises (I-05); live transfer, on-call paging and a monitored queue (D-01 to D-03, D-14)",
  },
];
