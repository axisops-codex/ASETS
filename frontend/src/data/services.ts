// Built-in psychology services catalogue (UK). Users can also add their own in Settings.
export type ServiceUnit = "session" | "hour" | "fixed";

export type ServiceItem = { id: string; name: string; price?: number; unit: ServiceUnit };

export const PSYCHOLOGY_SERVICES: { name: string; unit: ServiceUnit }[] = [
  { name: "Initial consultation", unit: "session" },
  { name: "Individual therapy session (50 min)", unit: "session" },
  { name: "Teleconsultation (video)", unit: "session" },
  { name: "Telephone consultation", unit: "session" },
  { name: "Couples therapy session", unit: "session" },
  { name: "Family therapy session", unit: "session" },
  { name: "Group therapy session", unit: "session" },
  { name: "CBT session", unit: "session" },
  { name: "EMDR session", unit: "session" },
  { name: "ACT session", unit: "session" },
  { name: "Psychological assessment", unit: "fixed" },
  { name: "Cognitive / neuropsychological testing", unit: "hour" },
  { name: "ADHD assessment", unit: "fixed" },
  { name: "Autism (ASD) assessment", unit: "fixed" },
  { name: "Clinical report writing", unit: "hour" },
  { name: "Court / medico-legal report", unit: "hour" },
  { name: "Clinical supervision", unit: "hour" },
  { name: "Workshop / training", unit: "hour" },
  { name: "Late cancellation / DNA fee", unit: "fixed" },
];

export const UNIT_LABEL: Record<ServiceUnit, string> = {
  session: "sessions",
  hour: "hours",
  fixed: "qty",
};
