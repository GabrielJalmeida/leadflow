import {
  CompassNorthwestRegular,
  DataTrendingRegular,
  HistoryRegular,
  PeopleTeamRegular,
  SettingsRegular,
  SparkleRegular,
} from '@fluentui/react-icons'

type View = 'discover' | 'pipeline' | 'queue' | 'followups' | 'contacted' | 'ignored' | 'accepted' | 'hidden' | 'settings'

type Props = { view: View; onView: (view: View) => void }

export function NavRail({ view, onView }: Props) {
  return (
    <nav className="nav-rail" aria-label="Navegação principal">
      <div className="brand-mark" aria-label="LeadFlow"><span>LF</span></div>
      <div className="nav-rail__group">
        <button className={`nav-item ${view === 'discover' ? 'is-active' : ''}`} aria-current={view === 'discover' ? 'page' : undefined} title="Descobrir" onClick={() => onView('discover')}><CompassNorthwestRegular /><span>Descobrir</span></button>
        <button className={`nav-item ${view === 'pipeline' ? 'is-active' : ''}`} aria-current={view === 'pipeline' ? 'page' : undefined} title="Pipeline de vendas" onClick={() => onView('pipeline')}><PeopleTeamRegular /><span>Pipeline</span></button>
        <button className={`nav-item ${view === 'queue' ? 'is-active' : ''}`} aria-current={view === 'queue' ? 'page' : undefined} title="Fila de contato" onClick={() => onView('queue')}><PeopleTeamRegular /><span>Fila</span></button>
        <button className={`nav-item ${view === 'accepted' ? 'is-active' : ''}`} aria-current={view === 'accepted' ? 'page' : undefined} title="Leads aceitos" onClick={() => onView('accepted')}><DataTrendingRegular /><span>Aceitos</span></button>
        <button className={`nav-item ${view === 'contacted' ? 'is-active' : ''}`} aria-current={view === 'contacted' ? 'page' : undefined} title="Leads já contactados" onClick={() => onView('contacted')}><HistoryRegular /><span>Contactados</span></button>
      </div>
      <div className="nav-rail__spacer" />
      <div className="nav-rail__group">
        <button className={`nav-item ${view === 'ignored' ? 'is-active' : ''}`} aria-current={view === 'ignored' ? 'page' : undefined} title="Leads ignorados" onClick={() => onView('ignored')}><SparkleRegular /><span>Ignorados</span></button>
        <button className={`nav-item ${view === 'hidden' ? 'is-active' : ''}`} aria-current={view === 'hidden' ? 'page' : undefined} title="Leads escondidos" onClick={() => onView('hidden')}><SettingsRegular /><span>Escondidos</span></button>
        <button className={`nav-item ${view === 'settings' ? 'is-active' : ''}`} aria-current={view === 'settings' ? 'page' : undefined} title="Configurações" onClick={() => onView('settings')}><SettingsRegular /><span>Config.</span></button>
      </div>
    </nav>
  )
}
