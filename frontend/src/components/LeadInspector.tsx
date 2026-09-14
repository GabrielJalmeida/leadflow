import { useEffect, useMemo, useState } from 'react'
import {
  ArrowUpRightRegular,
  CheckmarkCircleRegular,
  ClipboardRegular,
  DismissRegular,
  GlobeRegular,
  MailRegular,
  PhoneRegular,
  SendRegular,
  SparkleRegular,
  ColorRegular,
  ShieldCheckmarkRegular,
} from '@fluentui/react-icons'
import { api } from '../lib/api'
import type { ContactPreparation, LeadCard, LeadFlowSettings, LifecycleStatus, LeadInteraction } from '../lib/types'
import {
  identityLabel,
  opportunityLabel,
  readinessLabel,
  serviceFitLabel,
} from '../lib/ptBR'

function percent(value?: number) {
  if (value == null) return '—'
  return `${Math.round(value <= 1 ? value * 100 : value)}%`
}

function score(value?: number | null) {
  return value == null ? '—' : `${Math.round(value)}`
}

function leadContext(lead: LeadCard) {
  const socials = (lead.contact?.socials ?? []).map((url) => `- ${url}`).join('\n') || '- Nenhuma rede social identificada'
  return `EMPRESA\nNome: ${lead.name}\nSegmento: ${lead.opportunity?.service_fit ?? 'não identificado'}\nCidade: ${lead.location?.city ?? 'não identificada'}\nEstado: ${lead.location?.state ?? 'não identificado'}\nWebsite: ${lead.website?.url ?? 'não identificado'}\nInstagram/redes sociais:\n${socials}\nTelefone: ${lead.contact?.phone ?? 'não identificado'}\nE-mail: ${lead.contact?.email ?? 'não identificado'}\nTipo de oportunidade: ${lead.opportunity?.type ?? 'não classificado'}\nScore: ${lead.opportunity?.score ?? '—'}\nSinais:\n${(lead.opportunity?.reasons ?? []).map((x) => `- ${x}`).join('\n') || '- Nenhum'}\nCuidados:\n${(lead.opportunity?.cautions ?? []).map((x) => `- ${x}`).join('\n') || '- Nenhum'}`
}

function interpolate(template: string, lead: LeadCard) {
  const context = leadContext(lead)
  return template
    .replaceAll('{{name}}', lead.name || 'empresa')
    .replaceAll('{{segment}}', lead.opportunity?.service_fit || 'negócio local')
    .replaceAll('{{city}}', lead.location?.city || '')
    .replaceAll('{{state}}', lead.location?.state || '')
    .replaceAll('{{opportunity_type}}', lead.opportunity?.type || '')
    .replaceAll('{{lead_context}}', context)
}

const AI_URLS: Record<string, string> = {
  chatgpt: 'https://chatgpt.com/',
  gemini: 'https://gemini.google.com/',
  claude: 'https://claude.ai/new',
  v0: 'https://v0.app/',
  lovable: 'https://lovable.dev/',
  midjourney: 'https://www.midjourney.com/imagine/',
}

async function openAiWithPrompt(prompt: string, provider: string) {
  try { await navigator.clipboard.writeText(prompt) } catch { /* clipboard may be blocked */ }
  window.open(AI_URLS[provider] || AI_URLS.chatgpt, '_blank', 'noopener,noreferrer')
}


type Props = {
  lead: LeadCard | null
  onClose: () => void
  onLifecycle?: (lead: LeadCard, status: LifecycleStatus) => void
  onEnqueue?: (lead: LeadCard, message?: string) => void
  settings?: LeadFlowSettings
}

export function LeadInspector({ lead, onClose, onLifecycle, onEnqueue, settings }: Props) {
  const [contact, setContact] = useState<ContactPreparation | null>(null)
  const [message, setMessage] = useState('')
  const [loadingContact, setLoadingContact] = useState(false)
  const [copied, setCopied] = useState(false)
  const [followUpNote, setFollowUpNote] = useState('')
  const [followUpAt, setFollowUpAt] = useState('')
  const [savingFollowUp, setSavingFollowUp] = useState(false)
  const [interactions, setInteractions] = useState<LeadInteraction[]>([])
  const [interactionNote, setInteractionNote] = useState('')
  const [savingInteraction, setSavingInteraction] = useState(false)
  const lifecycle = lead?.lifecycle?.status ?? 'new'
  const canQueue = lifecycle !== 'contacted' && lifecycle !== 'ignored' && lifecycle !== 'hidden'

  useEffect(() => {
    setContact(null)
    setMessage('')
    setCopied(false)
    setInteractionNote('')
    if (lead?.lead_key) {
      void api.interactions(lead.lead_key).then((response) => setInteractions(response.items)).catch(() => setInteractions([]))
    } else {
      setInteractions([])
    }
  }, [lead])

  const socials = useMemo(() => lead?.contact?.socials ?? [], [lead])
  if (!lead) return null
  const activeLead = lead

  async function prepare() {
    setLoadingContact(true)
    try {
      const prepared = await api.prepareContact(activeLead)
      setContact(prepared)
      setMessage(prepared.message)
    } finally {
      setLoadingContact(false)
    }
  }

  async function saveFollowUp() {
    if (!activeLead.lead_key || !followUpAt) return
    setSavingFollowUp(true)
    try {
      await api.scheduleFollowUp(activeLead.lead_key, new Date(followUpAt).toISOString(), followUpNote)
    } finally { setSavingFollowUp(false) }
  }

  async function addInteraction(outcome: string, status?: LifecycleStatus) {
    if (!activeLead.lead_key || savingInteraction) return
    setSavingInteraction(true)
    try {
      const response = await api.addInteraction(activeLead.lead_key, { kind: 'sales_activity', channel: 'manual', outcome, note: interactionNote, status }) as { id: number; lead_key: string; occurred_at: string; kind: string; channel: string; outcome: string; note: string; lead: LeadCard | null }
      setInteractions((current) => [{ id: response.id, lead_key: response.lead_key, occurred_at: response.occurred_at, kind: response.kind, channel: response.channel, outcome: response.outcome, note: response.note }, ...current])
      setInteractionNote('')
    } finally { setSavingInteraction(false) }
  }

  async function copyMessage() {
    await navigator.clipboard.writeText(message)
    setCopied(true)
    window.setTimeout(() => setCopied(false), 1600)
  }

  async function openPrimary() {
    if (!contact || contact.channel === 'none') return
    if (contact.channel === 'instagram' && contact.instagram_url) {
      void navigator.clipboard.writeText(message)
      window.open(contact.instagram_url, '_blank', 'noopener,noreferrer')
      return
    }
    if (contact.whatsapp_number) {
      const url = `https://wa.me/${contact.whatsapp_number}?text=${encodeURIComponent(message)}`
      window.open(url, '_blank', 'noopener,noreferrer')
    }
  }

  return (
    <aside className="inspector" aria-label={`Detalhes de ${lead.name}`}>
      <div className="inspector__top">
        <div>
          <p className="eyebrow">Oportunidade selecionada</p>
          <h2>{lead.name}</h2>
          <div className="lead-meta-line">
            <span>{opportunityLabel(lead.opportunity?.type)}</span>
            <span>·</span>
            <span>{readinessLabel(lead.opportunity?.actionable)}</span>
          </div>
        </div>
        <button className="icon-button" type="button" aria-label="Fechar detalhes" onClick={onClose}>
          <DismissRegular />
        </button>
      </div>

      <div className="fit-hero">
        <div className="fit-orb" style={{ '--fit': `${Math.min(100, Math.max(0, lead.opportunity?.score ?? 0)) * 3.6}deg` } as React.CSSProperties}>
          <div><strong>{lead.opportunity?.score ?? 0}</strong><span>pot.</span></div>
        </div>
        <div>
          <span className="section-kicker">Potencial da oportunidade</span>
          <strong className="fit-summary">{serviceFitLabel(lead.opportunity?.service_fit)}</strong>
          <p>{lead.opportunity?.reasons?.[0] || 'Revise os sinais antes de abordar.'}</p>
        </div>
      </div>

      <section className="inspector-section">
        <div className="section-title"><span>Contato</span><span className="section-index">01</span></div>
        <div className="lead-actions">
          <span className="lifecycle-badge">{lifecycle}</span>
          {onLifecycle && lead.lead_key && lifecycle !== 'contacted' && <button className="button button--quiet" type="button" onClick={() => onLifecycle(lead, 'contacted')}>Marcar contactado</button>}
          {onLifecycle && lead.lead_key && lifecycle !== 'accepted' && <button className="button button--quiet" type="button" onClick={() => onLifecycle(lead, 'accepted')}>Aceitar</button>}
          {onLifecycle && lead.lead_key && lifecycle !== 'ignored' && <button className="button button--quiet" type="button" onClick={() => onLifecycle(lead, 'ignored')}>Ignorar</button>}
          {onLifecycle && lead.lead_key && lifecycle !== 'hidden' && <button className="button button--quiet" type="button" onClick={() => onLifecycle(lead, 'hidden')}>Esconder</button>}
          {onLifecycle && lead.lead_key && lifecycle !== 'new' && lifecycle !== 'queued' && <button className="button button--quiet button--restore" type="button" onClick={() => onLifecycle(lead, 'new')}>Restaurar para novos</button>}
          {onLifecycle && lead.lead_key && <select className="lifecycle-select" value={lifecycle} onChange={(event) => onLifecycle(lead, event.target.value as LifecycleStatus)} aria-label="Etapa comercial"><option value="new">Novo</option><option value="queued">Na fila</option><option value="accepted">Aceito</option><option value="contacted">Contactado</option><option value="awaiting_response">Aguardando resposta</option><option value="responded">Respondeu</option><option value="proposal_sent">Proposta enviada</option><option value="negotiating">Negociando</option><option value="won">Ganho</option><option value="lost">Perdido</option><option value="ignored">Ignorado</option><option value="hidden">Escondido</option></select>}
        </div>
        <div className="contact-lines">
          <div><PhoneRegular /><span>{lead.contact?.phone || 'Sem celular'}</span></div>
          <div><MailRegular /><span>{lead.contact?.email || 'Sem e-mail'}</span></div>
          <div><GlobeRegular /><span>{lead.website?.url || 'Sem site identificado'}</span></div>
        </div>
        <div className="ai-tools">
          <button className="button button--quiet" type="button" onClick={() => void openAiWithPrompt(interpolate(settings?.site_text_prompt_template || 'Crie um conceito de site para {{name}}.\n\n{{lead_context}}', activeLead), settings?.text_ai || 'chatgpt')}><SparkleRegular /> Conceito / copy</button>
          <button className="button button--quiet" type="button" onClick={() => void openAiWithPrompt(interpolate(settings?.visual_prompt_template || 'GERE IMAGENS CONCEPT PARA {{name}}.\n\n{{lead_context}}', activeLead), settings?.image_ai || 'chatgpt')}><ColorRegular /> Gerar imagens</button>
          <button className="button button--quiet" type="button" onClick={() => void openAiWithPrompt(interpolate(settings?.prototype_prompt_template || 'CONSTRUA UM PROTÓTIPO FUNCIONAL DE WEBSITE PARA {{name}}.\n\n{{lead_context}}', activeLead), settings?.prototype_ai || 'v0')}>Protótipo de site</button>
        </div>
        {!contact ? (
          <button className="button button--primary button--full" type="button" onClick={prepare} disabled={loadingContact}>
            <SendRegular /> {loadingContact ? 'Preparando…' : 'Preparar contato'}
          </button>
        ) : (
          <div className="contact-composer">
            <div className="contact-route">
              <span>Canal recomendado</span>
              <strong>{contact.label}</strong>
            </div>
            <textarea value={message} onChange={(event) => setMessage(event.target.value)} rows={7} aria-label="Mensagem de contato" />
            <div className="composer-actions">
              <button className="button button--primary" type="button" disabled={contact.channel === 'none'} onClick={openPrimary}>
                <ArrowUpRightRegular /> {contact.channel === 'instagram' ? 'Abrir Instagram' : 'Abrir WhatsApp'}
              </button>
              <button className="button button--quiet" type="button" onClick={copyMessage}>
                {copied ? <CheckmarkCircleRegular /> : <ClipboardRegular />}{copied ? 'Copiado' : 'Copiar'}
              </button>
              {onEnqueue && canQueue && lead.lead_key && (
                <button className="button button--quiet" type="button" onClick={() => onEnqueue(lead, message)}>Adicionar à fila</button>
              )}
            </div>
          </div>
        )}
      </section>

      <section className="inspector-section">
        <div className="section-title"><span>Sinais</span><span className="section-index">02</span></div>
        <div className="signal-grid">
          <div className="signal"><span>Identidade</span><strong>{percent(lead.identity?.confidence)}</strong><small>{identityLabel(lead.identity?.status)}</small></div>
          <div className="signal"><span>Técnico</span><strong>{score(lead.website?.technical_score)}</strong><small>Saúde do site</small></div>
          <div className="signal"><span>UX no navegador</span><strong>{score(lead.website?.browser_ux_score)}</strong><small>Experiência objetiva</small></div>
          <div className="signal"><span>Visual</span><strong>{score(lead.website?.visual_score)}</strong><small>Qualidade visual</small></div>
        </div>
      </section>

      <section className="inspector-section">
        <div className="section-title"><span>Evidências e cuidados</span><span className="section-index">03</span></div>
        <ul className="reason-list">
          {(lead.opportunity?.reasons ?? []).slice(0, 5).map((reason) => <li key={reason}><CheckmarkCircleRegular />{reason}</li>)}
          {(lead.opportunity?.cautions ?? []).slice(0, 4).map((reason) => <li className="caution" key={reason}><ShieldCheckmarkRegular />{reason}</li>)}
          {!lead.opportunity?.reasons?.length && !lead.opportunity?.cautions?.length ? <li className="muted">Sem sinais adicionais no contrato atual.</li> : null}
        </ul>
      </section>


      <section className="inspector-section">
        <div className="section-title"><span>Histórico comercial</span><span className="section-index">05</span></div>
        <div className="interaction-form">
          <textarea value={interactionNote} onChange={(e) => setInteractionNote(e.target.value)} rows={3} placeholder="Ex.: pediu exemplos de sites e quer receber uma proposta." maxLength={4000} />
          <div className="interaction-actions">
            <button className="button button--quiet" type="button" disabled={savingInteraction} onClick={() => void addInteraction('Contato enviado', 'contacted')}>Contato enviado</button>
            <button className="button button--quiet" type="button" disabled={savingInteraction} onClick={() => void addInteraction('Respondeu', 'responded')}>Respondeu</button>
            <button className="button button--quiet" type="button" disabled={savingInteraction} onClick={() => void addInteraction('Proposta enviada', 'proposal_sent')}>Proposta enviada</button>
            <button className="button button--quiet" type="button" disabled={savingInteraction} onClick={() => void addInteraction('Sem interesse', 'lost')}>Sem interesse</button>
          </div>
        </div>
        <div className="interaction-timeline">
          {interactions.length ? interactions.slice(0, 10).map((item) => (
            <div className="interaction-item" key={item.id}>
              <span className="interaction-item__dot" />
              <div><strong>{item.outcome || item.kind}</strong><small>{new Date(item.occurred_at).toLocaleString('pt-BR')}</small>{item.note && <p>{item.note}</p>}</div>
            </div>
          )) : <div className="interaction-empty">Nenhuma interação registrada ainda.</div>}
        </div>
      </section>

      <section className="inspector-section">
        <div className="section-title"><span>Follow-up</span><span className="section-index">05</span></div>
        {lead.lifecycle?.follow_up_at ? (
          <div className="followup-box"><strong>{new Date(lead.lifecycle.follow_up_at).toLocaleString('pt-BR')}</strong><span>{lead.lifecycle.follow_up_note || 'Sem observação'}</span><button className="button button--quiet" type="button" onClick={() => lead.lead_key && void api.clearFollowUp(lead.lead_key)}>Limpar follow-up</button></div>
        ) : (
          <div className="followup-form"><input type="datetime-local" value={followUpAt} onChange={(e) => setFollowUpAt(e.target.value)} /><input value={followUpNote} onChange={(e) => setFollowUpNote(e.target.value)} placeholder="Ex.: cobrar retorno da proposta" maxLength={2000} /><button className="button button--quiet" type="button" disabled={!followUpAt || savingFollowUp} onClick={() => void saveFollowUp()}>{savingFollowUp ? 'Salvando…' : 'Agendar follow-up'}</button></div>
        )}
      </section>

      {socials.length > 0 && (
        <section className="inspector-section inspector-section--last">
          <div className="section-title"><span>Fontes</span><span className="section-index">04</span></div>
          <div className="source-stack">
            {socials.slice(0, 5).map((url) => (
              <a key={url} href={url} target="_blank" rel="noreferrer">{url.replace(/^https?:\/\//, '').replace(/\/$/, '')}<ArrowUpRightRegular /></a>
            ))}
          </div>
        </section>
      )}
    </aside>
  )
}
