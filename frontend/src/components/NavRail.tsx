import {
  CompassNorthwestRegular,
  DataTrendingRegular,
  HistoryRegular,
  PeopleTeamRegular,
  SettingsRegular,
  SparkleRegular,
} from '@fluentui/react-icons'

export function NavRail() {
  return (
    <nav className="nav-rail" aria-label="Navegação principal">
      <div className="brand-mark" aria-label="LeadFlow"><span>LF</span></div>
      <div className="nav-rail__group">
        <button className="nav-item is-active" aria-current="page" title="Descobrir"><CompassNorthwestRegular /><span>Descobrir</span></button>
        <button className="nav-item" disabled title="Leads — próxima etapa"><PeopleTeamRegular /><span>Leads</span></button>
        <button className="nav-item" disabled title="Funil — próxima etapa"><DataTrendingRegular /><span>Funil</span></button>
        <button className="nav-item" disabled title="Histórico — próxima etapa"><HistoryRegular /><span>Histórico</span></button>
      </div>
      <div className="nav-rail__spacer" />
      <div className="nav-rail__group">
        <button className="nav-item" disabled title="Análises — futura etapa"><SparkleRegular /><span>Análises</span></button>
        <button className="nav-item" disabled title="Configurações — futura etapa"><SettingsRegular /><span>Configurações</span></button>
      </div>
    </nav>
  )
}
