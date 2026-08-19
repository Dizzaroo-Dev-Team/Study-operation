import { useCallback, useState } from "react";
import { MvrTemplateBuilderView, type MvrTemplateBuilderSession } from "./MvrTemplateBuilderView";
import { MvrTemplateManagerView } from "./MvrTemplateManagerView";

type Phase = "manager" | "builder";

type Props = {
  showToast: (msg: string, type?: string) => void;
  organizationId?: string;
};

export function MvrTemplateStudio({ showToast, organizationId = "default" }: Props) {
  const [phase, setPhase] = useState<Phase>("manager");
  const [builderSession, setBuilderSession] = useState<MvrTemplateBuilderSession | null>(null);

  const openBlankBuilder = useCallback(() => {
    setBuilderSession({ kind: "new", preset: "blank" });
    setPhase("builder");
  }, []);

  const openLegacyBuilder = useCallback(() => {
    setBuilderSession({ kind: "new", preset: "legacy" });
    setPhase("builder");
  }, []);

  const openEditBuilder = useCallback((templateId: string) => {
    setBuilderSession({ kind: "edit", templateId });
    setPhase("builder");
  }, []);

  const backToManager = useCallback(() => {
    setPhase("manager");
    setBuilderSession(null);
  }, []);

  if (phase === "builder" && builderSession) {
    return (
      <MvrTemplateBuilderView
        session={builderSession}
        showToast={showToast}
        organizationId={organizationId}
        onBackToManager={backToManager}
        onTemplateIdChange={(id) => setBuilderSession({ kind: "edit", templateId: id })}
      />
    );
  }

  return (
    <MvrTemplateManagerView
      showToast={showToast}
      organizationId={organizationId}
      onOpenBlankBuilder={openBlankBuilder}
      onOpenLegacyLayoutBuilder={openLegacyBuilder}
      onEdit={openEditBuilder}
    />
  );
}
