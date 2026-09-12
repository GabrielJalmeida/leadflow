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
  ShieldCheckmarkRegular,
} from '@fluentui/react-icons'
import { api } from '../lib/api'
import type { ContactPreparation, LeadCard } from '../lib/types'
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

type Props = {
  lead: LeadCard | null
  onClose: () => void
}

export function LeadInspector({ lead, onClose }: Props) {
  const [contact, setContact] = useState<ContactPreparation | null>(null)
  const [message, setMessage] = useState('')
  const [loadingContact, setLoadingContact] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    setContact(null)
    setMessage('')
    setCopied(false)
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
        <div className="contact-lines">
          <div><PhoneRegular /><span>{lead.contact?.phone || 'Sem celular'}</span></div>
          <div><MailRegular /><span>{lead.contact?.email || 'Sem e-mail'}</span></div>
          <div><GlobeRegular /><span>{lead.website?.url || 'Sem site identificado'}</span></div>
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
