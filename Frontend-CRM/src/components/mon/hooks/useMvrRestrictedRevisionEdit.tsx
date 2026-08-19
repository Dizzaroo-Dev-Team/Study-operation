import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import type { ReviewComment } from "@/lib/queries/useMonitoring";
import { resolveCommentedFieldKeys } from "../utils/mvrReviewCommentNavigation";

type MvrRestrictedEditContextValue = {
  restrictedRevision: boolean;
  editableFieldKeys: Set<string>;
  fieldDisabled: (fieldKey: string) => boolean;
};

const MvrRestrictedEditContext = createContext<MvrRestrictedEditContextValue>({
  restrictedRevision: false,
  editableFieldKeys: new Set(),
  fieldDisabled: () => false,
});

export function useMvrRestrictedFieldEdit() {
  return useContext(MvrRestrictedEditContext);
}

export function useMvrRestrictedRevisionEdit({
  reportStatus,
  reviewComments,
  reportBodyRef,
  baseLocked,
  templateFields,
  contentReady = true,
}: {
  reportStatus: string;
  reviewComments: ReviewComment[];
  reportBodyRef: RefObject<HTMLElement | null>;
  baseLocked: boolean;
  templateFields?: Array<{ id: string; label?: string; type?: string; columns?: { id: string; label: string }[]; unlockFieldIds?: string[] }>;
  /** When false, field-key resolution waits until the form has mounted. */
  contentReady?: boolean;
}): MvrRestrictedEditContextValue {
  const restrictedRevision =
    !baseLocked && reportStatus === "Rejected" && reviewComments.length > 0;

  const [editableFieldKeys, setEditableFieldKeys] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!restrictedRevision) {
      setEditableFieldKeys(new Set());
      return;
    }

    const resolve = () => {
      setEditableFieldKeys(
        resolveCommentedFieldKeys(
          contentReady ? reportBodyRef.current : null,
          reviewComments,
          templateFields,
        ),
      );
    };

    resolve();
    if (!contentReady) return;

    const timers = [100, 300, 600].map((ms) => window.setTimeout(resolve, ms));
    return () => timers.forEach((t) => window.clearTimeout(t));
  }, [restrictedRevision, reviewComments, reportBodyRef, templateFields, contentReady]);

  const fieldDisabled = useCallback(
    (fieldKey: string) => {
      if (baseLocked) return true;
      if (!restrictedRevision) return false;
      return !editableFieldKeys.has(fieldKey);
    },
    [baseLocked, restrictedRevision, editableFieldKeys],
  );

  return useMemo(
    () => ({ restrictedRevision, editableFieldKeys, fieldDisabled }),
    [restrictedRevision, editableFieldKeys, fieldDisabled],
  );
}

export function MvrRestrictedEditProvider({
  reportStatus,
  reviewComments,
  reportBodyRef,
  baseLocked,
  templateFields,
  contentReady = true,
  children,
}: {
  reportStatus: string;
  reviewComments: ReviewComment[];
  reportBodyRef: RefObject<HTMLElement | null>;
  baseLocked: boolean;
  templateFields?: Array<{ id: string; label?: string; type?: string; columns?: { id: string; label: string }[]; unlockFieldIds?: string[] }>;
  contentReady?: boolean;
  children: ReactNode;
}) {
  const value = useMvrRestrictedRevisionEdit({
    reportStatus,
    reviewComments,
    reportBodyRef,
    baseLocked,
    templateFields,
    contentReady,
  });

  return (
    <MvrRestrictedEditContext.Provider value={value}>
      {children}
    </MvrRestrictedEditContext.Provider>
  );
}
