import type { EvidenceReference } from "../types/chat";

interface Props {
  evidence?: EvidenceReference;
}

function evidenceHref(evidence: EvidenceReference): string {
  return (
    evidence.url ??
    `/v1/evidence?pointer=${encodeURIComponent(evidence.pointer)}`
  );
}

export function EvidenceLink({ evidence }: Props) {
  if (!evidence) return null;
  return (
    <a
      className="evidence-link"
      href={evidenceHref(evidence)}
      target="_blank"
      rel="noreferrer"
      title={evidence.pointer}
    >
      Evidence
      <span className="sr-only">: {evidence.pointer}</span>
    </a>
  );
}
