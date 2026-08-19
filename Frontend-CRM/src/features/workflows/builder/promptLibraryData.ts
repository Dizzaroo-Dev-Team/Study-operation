// builder/promptLibraryData.ts
// A small, curated library of ready-made prompts for the "Describe your workflow"
// box in the builder's AI-generation panel. A user picks one instead of inventing a
// prompt from scratch every time — reuse, don't rebuild. The set doubles as a
// demo walkthrough of what the engine can express (review→sign, parallel review,
// decision gates, ordered signing, jobs/timers).
//
// Pure data — no React, no fetching. Clicking an entry just drops `text` into the
// existing `aiDesc` state, then the user edits and hits "Generate with AI".

export interface StarterPrompt {
  /** stable key (used as React list key) */
  id: string;
  /** short chip/card title, e.g. "Review → Sign" */
  label: string;
  /** one-line "what it makes" subtitle */
  blurb: string;
  /** the full plain-English prompt dropped into the description box */
  text: string;
  /** optional grouping tag, e.g. "simple" | "parallel" | "signing" */
  tags?: string[];
}

export const PROMPT_LIBRARY: StarterPrompt[] = [
  {
    id: "review-sign",
    label: "Review → Sign",
    blurb: "One legal review, then one signer. Reviewer can send back.",
    text:
      "Review by one legal reviewer, then one signer signs; the reviewer can send " +
      "the draft back for edits. When the signer signs, mark the agreement executed.",
    tags: ["simple"],
  },
  {
    id: "cda-style",
    label: "CDA / NDA",
    blurb: "Confidentiality agreement: draft → legal → sign → executed.",
    text:
      "Confidentiality agreement: draft, then a single legal review that can send " +
      "the draft back for edits, then one authorized signer signs, then executed.",
    tags: ["simple", "signing"],
  },
  {
    id: "parallel-review",
    label: "Parallel review",
    blurb: "Legal and business review at the same time; both must approve.",
    text:
      "Legal and business review the draft in parallel; both must approve before it " +
      "moves on. If either one rejects, send it back to draft. After both approve, a " +
      "single signer signs and the agreement is executed.",
    tags: ["parallel"],
  },
  {
    id: "decision-gate",
    label: "Decision gate by value",
    blurb: "High-value agreements need an extra executive approval.",
    text:
      "Draft an agreement that captures a contract value. If the value is over 50,000 " +
      "it needs an executive approval before legal review; otherwise it goes straight " +
      "to legal review. After legal approves, one signer signs and it is executed.",
    tags: ["decision"],
  },
  {
    id: "ordered-signing",
    label: "Ordered signing",
    blurb: "Sponsor signs first, then PI; then distribute the copy.",
    text:
      "After legal approval, the sponsor signs first, then the PI signs second. If " +
      "anyone declines, return the draft to the author. Once everyone has signed, " +
      "distribute the final copy to the site team.",
    tags: ["signing"],
  },
  {
    id: "parallel-job-timer",
    label: "Parallel + PDF job + timer",
    blurb: "Two reviews in parallel, escalation timer, auto-generate PDF.",
    text:
      "Legal and finance review the draft in parallel. Put a 2-minute escalation timer " +
      "on the finance review so it escalates to a VP if it stalls. When both reviews " +
      "complete, automatically generate and distribute the final PDF, then mark executed.",
    tags: ["parallel", "job", "timer"],
  },
  {
    id: "amendment",
    label: "Amendment round",
    blurb: "Negotiation back-and-forth before signing.",
    text:
      "Draft an amendment, send it to the counterparty for review; they can propose " +
      "changes that come back to the author for another round, repeating until both " +
      "sides agree. Then both parties sign and the amendment is executed.",
    tags: ["negotiation"],
  },
];
