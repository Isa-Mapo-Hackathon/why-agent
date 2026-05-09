"use client";

import { useState } from "react";

interface TableMeta {
  name: string;
  description: string;
}

interface DatasetMeta {
  name: string;
  description: string;
  dateRange: string;
  rows: string;
  channels: string[];
  tables: TableMeta[];
  kaggleUrl: string;
}

// Demo-only: intentionally hardcoded for the REES46 hackathon dataset.
// If the project ever supports multiple datasets, this should be a prop
// fed from an API endpoint that reads semantic_layer.yml at runtime.
const DATASET: DatasetMeta = {
  name: "REES46 Direct Messaging",
  description:
    "Multichannel campaign data from a mid-size e-commerce retailer — 46 days of email and mobile push activity across ~3.35M recipients.",
  dateRange: "Apr 30 – Jun 14, 2021",
  rows: "~10M messages",
  channels: ["email", "mobile_push"],
  tables: [
    { name: "messages", description: "One row per message sent" },
    { name: "campaigns", description: "Campaign metadata & topic" },
    { name: "holidays", description: "Russian public holiday calendar" },
    {
      name: "client_first_purchase_date",
      description: "First purchase timestamp per recipient",
    },
  ],
  kaggleUrl: "https://www.kaggle.com/datasets/mkechinov/direct-messaging",
};

const PANEL_ID = "dataset-info-panel";

export default function DatasetInfo() {
  const [open, setOpen] = useState(false);

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={PANEL_ID}
        aria-label="Toggle dataset information panel"
        className="w-full flex items-center gap-2 rounded-lg px-2 py-2 text-left text-violet-400 hover:bg-elevated hover:text-violet-200 transition-colors"
      >
        <span className="text-[10px] font-mono text-violet-600 w-3">
          {open ? "▼" : "▶"}
        </span>
        <span className="text-xs font-mono uppercase tracking-widest">
          Dataset
        </span>
      </button>

      {open && (
        <div id={PANEL_ID} className="ml-3 pl-3 border-l border-frame space-y-3 pb-1">
          {/* Name + description */}
          <div>
            <p className="text-xs font-semibold text-violet-200">
              {DATASET.name}
            </p>
            <p className="text-[11px] text-violet-400 leading-relaxed mt-0.5">
              {DATASET.description}
            </p>
          </div>

          {/* Key stats */}
          <div className="space-y-1">
            <Stat label="Period" value={DATASET.dateRange} />
            <Stat label="Volume" value={DATASET.rows} />
            <Stat label="Channels" value={DATASET.channels.join(", ")} />
          </div>

          {/* Tables */}
          <div>
            <p className="text-[10px] font-mono text-violet-600 uppercase tracking-widest mb-1">
              Tables
            </p>
            <div className="space-y-1">
              {DATASET.tables.map((t) => (
                <div key={t.name}>
                  <span className="text-[11px] font-mono text-violet-300">
                    {t.name}
                  </span>
                  <p className="text-[10px] text-violet-500 leading-tight">
                    {t.description}
                  </p>
                </div>
              ))}
            </div>
          </div>

          {/* Kaggle link */}
          <a
            href={DATASET.kaggleUrl}
            target="_blank"
            rel="noopener noreferrer"
            aria-label="View REES46 dataset on Kaggle (opens in new tab)"
            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-violet-400 hover:text-violet-200 transition-colors"
          >
            <span className="text-[10px]">↗</span>
            View on Kaggle
          </a>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[10px] font-mono text-violet-600 uppercase tracking-widest w-14 shrink-0">
        {label}
      </span>
      <span className="text-[11px] text-violet-300">{value}</span>
    </div>
  );
}
