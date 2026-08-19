import { useCallback, useState } from "react";
import type { ReviewComment } from "@/lib/queries/useMonitoring";
import { useSaveAuthorCommentReply } from "@/lib/queries/useMonitoring";

export interface MvrReviewerCommentsSidebarProps {
  visitId: string;
  comments: ReviewComment[];
  activeCommentId: string | null;
  onCommentClick: (comment: ReviewComment) => void;
  /** When true, sponsor can post/edit replies (rejected report revision). */
  canReply?: boolean;
  onCommentsChange?: (comments: ReviewComment[]) => void;
  variant?: "legacy" | "modern";
}

function truncateQuote(text: string, max = 120): string {
  const t = text.trim();
  if (!t) return "";
  return t.length > max ? `${t.slice(0, max)}…` : t;
}

export function MvrReviewerCommentsSidebar({
  visitId,
  comments,
  activeCommentId,
  onCommentClick,
  canReply = false,
  onCommentsChange,
  variant = "modern",
}: MvrReviewerCommentsSidebarProps) {
  const replyMutation = useSaveAuthorCommentReply(visitId);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [openReplyId, setOpenReplyId] = useState<string | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  const handleSaveReply = useCallback(
    async (comment: ReviewComment) => {
      const text = (drafts[comment.id] ?? comment.author_reply ?? "").trim();
      if (!text) return;
      setSavingId(comment.id);
      try {
        const result = await replyMutation.mutateAsync({
          commentId: comment.id,
          author_reply: text,
        });
        const updated = result.comment;
        onCommentsChange?.(
          comments.map((c) => (c.id === comment.id ? { ...c, ...updated } : c)),
        );
        setOpenReplyId(null);
      } catch {
        /* mutation error surfaces via react-query; parent may toast on refetch failure */
      } finally {
        setSavingId(null);
      }
    },
    [comments, drafts, onCommentsChange, replyMutation],
  );

  if (comments.length === 0) return null;

  const isLegacy = variant === "legacy";

  return (
    <aside
      className={
        isLegacy
          ? undefined
          : "w-full shrink-0 self-start lg:w-[300px] rounded-xl border border-gray-200 bg-slate-50 lg:rounded-none lg:border-l lg:border-t-0 lg:border-r-0 lg:border-b-0 px-3 py-3.5"
      }
      style={
        isLegacy
          ? {
              width: 280,
              flexShrink: 0,
              display: "flex",
              flexDirection: "column",
              gap: 0,
              alignSelf: "flex-start",
            }
          : undefined
      }
    >
      {isLegacy ? (
        <>
          <div
            style={{
              fontSize: 12,
              fontWeight: 700,
              color: "#92400e",
              padding: "10px 14px",
              background: "#fffbeb",
              border: "1.5px solid #fcd34d",
              borderRadius: "10px 10px 0 0",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <span>💬</span>
            <span>
              {comments.length} Reviewer Comment{comments.length !== 1 ? "s" : ""}
            </span>
          </div>
          <div
            style={{
              fontSize: 11,
              color: "#78716c",
              padding: "6px 14px",
              background: "#fffbeb",
              borderLeft: "1.5px solid #fcd34d",
              borderRight: "1.5px solid #fcd34d",
            }}
          >
            Click a comment to jump to the highlighted text. Add a reply to explain your fix.
          </div>
        </>
      ) : (
        <>
          <div className="text-[13px] font-bold text-gray-900 mb-1">
            Comments ({comments.length})
          </div>
          <p className="text-[11px] text-gray-500 mb-3 leading-snug">
            Click a comment to jump to the highlighted text. Add a reply to explain your fix.
          </p>
        </>
      )}

      <div
        className={isLegacy ? undefined : "flex flex-col gap-2.5"}
        style={
          isLegacy
            ? {
                display: "flex",
                flexDirection: "column",
                border: "1.5px solid #fcd34d",
                borderTop: "none",
                borderRadius: "0 0 10px 10px",
                overflow: "hidden",
              }
            : undefined
        }
      >
        {comments.map((c, idx) => {
          const quote = truncateQuote(c.highlighted_text ?? "", isLegacy ? 45 : 120);
          const isActive = activeCommentId === c.id;
          const existingReply = (c.author_reply ?? "").trim();
          const draft = drafts[c.id] ?? existingReply;
          const showReplyBox = canReply && openReplyId === c.id;

          const cardInner = (
            <>
              {quote ? (
                <div
                  className={
                    isLegacy
                      ? undefined
                      : "text-xs italic text-amber-900 bg-amber-50 border border-amber-100 rounded-md px-2 py-1.5 mb-2 break-words"
                  }
                  style={
                    isLegacy
                      ? {
                          fontSize: 11,
                          fontWeight: 700,
                          color: "#92400e",
                          padding: "2px 8px",
                          background: "#fef3c7",
                          borderRadius: 4,
                          display: "inline-block",
                          marginBottom: 6,
                          maxWidth: "100%",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }
                      : undefined
                  }
                >
                  {isLegacy ? `"${quote}"` : `“${quote}”`}
                </div>
              ) : null}
              <div
                className={isLegacy ? undefined : "text-[13px] text-gray-800 whitespace-pre-wrap break-words leading-snug"}
                style={isLegacy ? { fontSize: 12.5, color: "#374151", lineHeight: 1.45 } : undefined}
              >
                {c.comment_text}
              </div>

              {existingReply && openReplyId !== c.id ? (
                <div
                  className={
                    isLegacy
                      ? undefined
                      : "mt-2.5 rounded-md border border-blue-100 bg-blue-50 px-2.5 py-2 text-[12px] text-blue-950"
                  }
                  style={
                    isLegacy
                      ? {
                          marginTop: 10,
                          padding: "8px 10px",
                          background: "#eff6ff",
                          border: "1px solid #bfdbfe",
                          borderRadius: 6,
                          fontSize: 12,
                          color: "#1e3a8a",
                        }
                      : undefined
                  }
                >
                  <div className="text-[10px] font-bold uppercase tracking-wide text-blue-700 mb-1">
                    Your reply
                  </div>
                  <div className="whitespace-pre-wrap break-words">{existingReply}</div>
                </div>
              ) : null}

              {canReply && (
                <div
                  className={isLegacy ? undefined : "mt-2.5 pt-2 border-t border-gray-100"}
                  style={isLegacy ? { marginTop: 10, paddingTop: 8, borderTop: "1px solid #fde68a" } : undefined}
                  onClick={(e) => e.stopPropagation()}
                >
                  {showReplyBox ? (
                    <>
                      <textarea
                        value={draft}
                        onChange={(e) =>
                          setDrafts((prev) => ({ ...prev, [c.id]: e.target.value }))
                        }
                        rows={3}
                        placeholder="Explain how you addressed this comment…"
                        className={
                          isLegacy
                            ? undefined
                            : "w-full text-xs border border-gray-300 rounded-md px-2 py-1.5 resize-y min-h-[72px] focus:outline-none focus:ring-2 focus:ring-blue-500"
                        }
                        style={
                          isLegacy
                            ? {
                                width: "100%",
                                fontSize: 12,
                                border: "1px solid #d1d5db",
                                borderRadius: 6,
                                padding: "6px 8px",
                                resize: "vertical",
                                minHeight: 72,
                                boxSizing: "border-box",
                              }
                            : undefined
                        }
                      />
                      <div
                        className={isLegacy ? undefined : "flex gap-2 mt-2"}
                        style={isLegacy ? { display: "flex", gap: 8, marginTop: 8 } : undefined}
                      >
                        <button
                          type="button"
                          disabled={!draft.trim() || savingId === c.id}
                          onClick={() => void handleSaveReply(c)}
                          className={
                            isLegacy
                              ? undefined
                              : "text-xs font-semibold px-2.5 py-1 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                          }
                          style={
                            isLegacy
                              ? {
                                  fontSize: 11,
                                  fontWeight: 600,
                                  padding: "4px 10px",
                                  borderRadius: 6,
                                  border: "none",
                                  background: "#2563eb",
                                  color: "#fff",
                                  cursor: draft.trim() ? "pointer" : "default",
                                  opacity: !draft.trim() || savingId === c.id ? 0.5 : 1,
                                }
                              : undefined
                          }
                        >
                          {savingId === c.id ? "Saving…" : existingReply ? "Update reply" : "Save reply"}
                        </button>
                        {openReplyId === c.id && (
                          <button
                            type="button"
                            onClick={() => {
                              setOpenReplyId(null);
                              setDrafts((prev) => ({ ...prev, [c.id]: existingReply }));
                            }}
                            className={
                              isLegacy
                                ? undefined
                                : "text-xs font-medium px-2 py-1 rounded-md text-gray-600 hover:bg-gray-100"
                            }
                            style={
                              isLegacy
                                ? {
                                    fontSize: 11,
                                    padding: "4px 8px",
                                    background: "transparent",
                                    border: "none",
                                    color: "#6b7280",
                                    cursor: "pointer",
                                  }
                                : undefined
                            }
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setOpenReplyId(c.id);
                        setDrafts((prev) => ({ ...prev, [c.id]: existingReply }));
                      }}
                      className={
                        isLegacy
                          ? undefined
                          : "text-xs font-semibold text-blue-700 hover:text-blue-800"
                      }
                      style={
                        isLegacy
                          ? {
                              fontSize: 11,
                              fontWeight: 600,
                              color: "#1d4ed8",
                              background: "none",
                              border: "none",
                              padding: 0,
                              cursor: "pointer",
                            }
                          : undefined
                      }
                    >
                      {existingReply ? "Edit reply" : "Reply"}
                    </button>
                  )}
                </div>
              )}
            </>
          );

          if (isLegacy) {
            return (
              <div
                key={c.id}
                onClick={() => onCommentClick(c)}
                style={{
                  background: isActive ? "#fffbeb" : "#fff",
                  borderTop: idx > 0 ? "1px solid #fde68a" : "none",
                  padding: "12px 14px",
                  cursor: "pointer",
                  transition: "background .15s",
                  outline: isActive ? "2px solid #f59e0b" : "none",
                  outlineOffset: -2,
                }}
              >
                {cardInner}
              </div>
            );
          }

          return (
            <div
              key={c.id}
              className={
                "rounded-lg border p-3 shadow-sm text-sm transition-colors " +
                (isActive
                  ? "border-amber-400 bg-amber-50 ring-2 ring-amber-300"
                  : "border-gray-200 bg-white")
              }
            >
              <div
                role="button"
                tabIndex={0}
                onClick={() => onCommentClick(c)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") onCommentClick(c);
                }}
                className="cursor-pointer hover:opacity-95"
              >
                {quote ? (
                  <div className="text-xs italic text-amber-900 bg-amber-50 border border-amber-100 rounded-md px-2 py-1.5 mb-2 break-words">
                    “{quote}”
                  </div>
                ) : null}
                <div className="text-[13px] text-gray-800 whitespace-pre-wrap break-words leading-snug">
                  {c.comment_text}
                </div>
              </div>

              {existingReply && openReplyId !== c.id ? (
                <div className="mt-2.5 rounded-md border border-blue-100 bg-blue-50 px-2.5 py-2 text-[12px] text-blue-950">
                  <div className="text-[10px] font-bold uppercase tracking-wide text-blue-700 mb-1">
                    Your reply
                  </div>
                  <div className="whitespace-pre-wrap break-words">{existingReply}</div>
                </div>
              ) : null}

              {canReply && (
                <div className="mt-2.5 pt-2 border-t border-gray-100">
                  {showReplyBox ? (
                    <>
                      <textarea
                        value={draft}
                        onChange={(e) =>
                          setDrafts((prev) => ({ ...prev, [c.id]: e.target.value }))
                        }
                        rows={3}
                        placeholder="Explain how you addressed this comment…"
                        className="w-full text-xs border border-gray-300 rounded-md px-2 py-1.5 resize-y min-h-[72px] focus:outline-none focus:ring-2 focus:ring-blue-500"
                      />
                      <div className="flex gap-2 mt-2">
                        <button
                          type="button"
                          disabled={!draft.trim() || savingId === c.id}
                          onClick={() => void handleSaveReply(c)}
                          className="text-xs font-semibold px-2.5 py-1 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          {savingId === c.id ? "Saving…" : existingReply ? "Update reply" : "Save reply"}
                        </button>
                        {openReplyId === c.id && (
                          <button
                            type="button"
                            onClick={() => {
                              setOpenReplyId(null);
                              setDrafts((prev) => ({ ...prev, [c.id]: existingReply }));
                            }}
                            className="text-xs font-medium px-2 py-1 rounded-md text-gray-600 hover:bg-gray-100"
                          >
                            Cancel
                          </button>
                        )}
                      </div>
                    </>
                  ) : (
                    <button
                      type="button"
                      onClick={() => {
                        setOpenReplyId(c.id);
                        setDrafts((prev) => ({ ...prev, [c.id]: existingReply }));
                      }}
                      className="text-xs font-semibold text-blue-700 hover:text-blue-800"
                    >
                      {existingReply ? "Edit reply" : "Reply"}
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
