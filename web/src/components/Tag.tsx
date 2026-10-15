export function Tag({ kind, children, title }: { kind?: "ok" | "warn" | "bad"; children: React.ReactNode; title?: string }) {
  return <span className={`tag ${kind ?? ""}`} title={title}>{children}</span>;
}

export function StatusTag({ rendered, stale }: { rendered: boolean; stale: boolean }) {
  if (rendered && !stale) return <Tag kind="ok">rendered</Tag>;
  if (rendered) return <Tag kind="warn">edited since the last render</Tag>;
  return <Tag>not rendered yet</Tag>;
}
