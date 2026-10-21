// Shared labels and colours

export const SITUATION: Record<number, { label: string; th: string; color: string }> = {
  1: { label: "Critically low", th: "น้อยวิกฤต", color: "#b7791f" },
  2: { label: "Low", th: "น้อย", color: "#e2c26b" },
  3: { label: "Normal", th: "ปกติ", color: "#5f9a6b" },
  4: { label: "High", th: "มาก", color: "#1f6f8b" },
  5: { label: "Overflowing", th: "ล้นตลิ่ง", color: "#b8323a" },
};
export const NO_DATA_COLOR = "#9aa7a9";

export const SEVERITY: Record<number, { label: string; color: string }> = {
  1: { label: "Watch", color: "#e0a92e" },
  2: { label: "Serious", color: "#d9682b" },
  3: { label: "Severe", color: "#b8323a" },
};

export const INCIDENT_KIND: Record<string, string> = {
  inundation: "Inundation",
  overflow: "Bank overflow",
  breach: "Embankment breach",
  flash_flood: "Flash flood",
};

export const INCIDENT_STATUS: Record<string, string> = {
  active: "Active",
  receding: "Receding",
  closed: "Closed",
};

export const DAMAGE_TYPE: Record<string, string> = {
  crops: "Crops",
  house: "House",
  livestock: "Livestock",
  fishery: "Fishery",
  property: "Property",
};

export const CLAIM_FLOW = ["submitted", "surveyed", "approved", "paid"] as const;
export const CLAIM_STATUS: Record<string, { label: string; color: string; next?: string; action?: string }> = {
  submitted: { label: "Submitted", color: "#8a9a9c", next: "surveyed", action: "Mark surveyed" },
  surveyed: { label: "Surveyed", color: "#1f6f8b", next: "approved", action: "Approve" },
  approved: { label: "Approved", color: "#d39a12", next: "paid", action: "Mark paid" },
  paid: { label: "Paid", color: "#5f9a6b" },
  rejected: { label: "Rejected", color: "#b8323a" },
};

export const thb = (n: number | null | undefined) =>
  n == null ? "–" : `฿${Math.round(n).toLocaleString("en-US")}`;

export const num = (n: number | null | undefined, d = 2) => (n == null ? "–" : n.toFixed(d));

export const ago = (iso: string) => {
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6;
  if (h < 1) return "just now";
  if (h < 24) return `${Math.round(h)} h ago`;
  const d = Math.round(h / 24);
  return d === 1 ? "yesterday" : `${d} days ago`;
};

export const fmtTime = (t: string) =>
  new Date(t).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
