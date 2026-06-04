"use client";

import type { SourceChunk } from "@/lib/types";
import { SOURCE_TYPE_LABELS } from "@/lib/types";

interface Props {
  sourceId: string | null;
  chunk: SourceChunk | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}

function MetaRow({ label, value }: { label: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return null;
  return (
    <div className="flex gap-2 text-sm">
      <span className="text-gray-500 min-w-[120px] shrink-0">{label}</span>
      <span className="text-gray-800 font-mono break-all">{String(value)}</span>
    </div>
  );
}

export default function SourcePanel({
  sourceId,
  chunk,
  loading,
  error,
  onClose,
}: Props) {
  if (!sourceId) return null;

  return (
    <aside className="fixed right-0 top-0 h-full w-[380px] bg-white shadow-2xl border-l border-gray-200 z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b bg-gray-50">
        <h3 className="font-semibold text-gray-800 text-sm">Nguồn gốc dữ liệu</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-700 text-lg leading-none font-bold"
        >
          ×
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Source ID chip */}
        <div className="font-mono text-xs bg-blue-50 text-blue-700 px-3 py-2 rounded-lg break-all border border-blue-100">
          {sourceId}
        </div>

        {/* Loading */}
        {loading && (
          <div className="flex items-center justify-center py-8">
            <div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {/* Error */}
        {error && !loading && (
          <div className="text-red-600 text-sm bg-red-50 p-3 rounded-lg border border-red-200">
            {error}
          </div>
        )}

        {/* Chunk data */}
        {chunk && !loading && (
          <>
            {/* Type + Date */}
            <div className="flex gap-2 flex-wrap">
              <span className="px-2 py-1 bg-indigo-50 text-indigo-700 text-xs rounded-full border border-indigo-200 font-medium">
                {SOURCE_TYPE_LABELS[chunk.source_type] ?? chunk.source_type}
              </span>
              {chunk.date && (
                <span className="px-2 py-1 bg-gray-50 text-gray-600 text-xs rounded-full border border-gray-200">
                  {chunk.date}
                </span>
              )}
            </div>

            {/* Content */}
            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">
                Nội dung
              </p>
              <p className="text-base text-gray-800 bg-gray-50 rounded-lg p-3 border border-gray-200 leading-relaxed whitespace-pre-line">
                {chunk.content}
              </p>
            </div>

            {/* Metadata */}
            {Object.keys(chunk.metadata).length > 0 && (
              <div>
                <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
                  Metadata
                </p>
                <div className="space-y-1.5 bg-gray-50 rounded-lg p-3 border border-gray-200">
                  {Object.entries(chunk.metadata).map(([k, v]) => (
                    <MetaRow key={k} label={k} value={v as unknown} />
                  ))}
                </div>
              </div>
            )}

            {/* IDs */}
            <div className="space-y-1">
              <MetaRow label="patient_id"    value={chunk.patient_id} />
              <MetaRow label="encounter_id"  value={chunk.encounter_id} />
              <MetaRow label="source_id"     value={chunk.source_id} />
            </div>
          </>
        )}
      </div>
    </aside>
  );
}
