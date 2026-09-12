type Props = {
  tone: 'online' | 'warning' | 'offline' | 'neutral'
  label: string
}

export function StatusDot({ tone, label }: Props) {
  return (
    <span className={`status-dot status-dot--${tone}`}>
      <span aria-hidden="true" className="status-dot__orb" />
      {label}
    </span>
  )
}
