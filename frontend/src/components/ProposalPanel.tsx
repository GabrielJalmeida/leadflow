import { useEffect, useMemo, useState } from 'react'
import { ClipboardRegular, OpenRegular, SaveRegular, SparkleRegular } from '@fluentui/react-icons'
import { api } from '../lib/api'
import type { LeadCard, LeadFlowSettings, LeadWorkspace } from '../lib/types'

function context(lead: LeadCard) {
  const socials = (lead.contact?.socials ?? []).join('\n') || 'Nenhuma'
  return `EMPRESA\nNome: ${lead.name}\nCidade: ${lead.location?.city || ''}/${lead.location?.state || ''}\nWebsite: ${lead.website?.url || 'não identificado'}\nRedes sociais:\n${socials}\nTelefone: ${lead.contact?.phone || 'não identificado'}\nE-mail: ${lead.contact?.email || 'não identificado'}\nOportunidade: ${lead.opportunity?.type || 'não classificada'}\nScore: ${lead.opportunity?.score ?? '—'}\nMotivos:\n${(lead.opportunity?.reasons || []).map(x => `- ${x}`).join('\n') || '- Nenhum'}`
}

function interpolate(template: string, lead: LeadCard) {
  return template.replaceAll('{{name}}', lead.name || 'empresa').replaceAll('{{segment}}', lead.opportunity?.service_fit || 'negócio local').replaceAll('{{city}}', lead.location?.city || '').replaceAll('{{state}}', lead.location?.state || '').replaceAll('{{opportunity_type}}', lead.opportunity?.type || '').replaceAll('{{lead_context}}', context(lead))
}

export function ProposalPanel({ lead, settings }: { lead: LeadCard; settings?: LeadFlowSettings }) {
  const [draft, setDraft] = useState<LeadWorkspace>({ lead_key: lead.lead_key || '', offer_title: '', proposal_text: '', price: '', delivery_time: '', notes: '' })
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    let active = true
    if (!lead.lead_key) return
    void api.getWorkspace(lead.lead_key).then(({ workspace }) => { if (active) setDraft(workspace) }).catch(() => {})
    return () => { active = false }
  }, [lead.lead_key])

  const proposalForCopy = useMemo(() => {
    const parts = [draft.offer_title, draft.proposal_text, draft.price && `Investimento: ${draft.price}`, draft.delivery_time && `Prazo: ${draft.delivery_time}`, draft.notes && `Observações: ${draft.notes}`].filter(Boolean)
    return parts.join('\n\n')
  }, [draft])

  async function save() {
    if (!lead.lead_key) return
    setSaving(true)
    try {
      const { workspace } = await api.updateWorkspace(lead.lead_key, { offer_title: draft.offer_title, proposal_text: draft.proposal_text, price: draft.price, delivery_time: draft.delivery_time, notes: draft.notes })
      setDraft(workspace); setSaved(true); window.setTimeout(() => setSaved(false), 1500)
    } finally { setSaving(false) }
  }

  async function copy() {
    await navigator.clipboard.writeText(proposalForCopy); setCopied(true); window.setTimeout(() => setCopied(false), 1500)
  }

  function openAi() {
    const template = settings?.site_text_prompt_template || 'Monte uma proposta comercial de website para {{name}}.\n\n{{lead_context}}'
    const prompt = `${interpolate(template, lead)}\n\nDIRETRIZES PARA A PROPOSTA\n${draft.proposal_text || 'Crie uma proposta comercial objetiva, convincente e sem inventar fatos.'}`
    void navigator.clipboard.writeText(prompt)
    const provider = settings?.text_ai || 'chatgpt'
    const urls: Record<string, string> = { chatgpt: 'https://chatgpt.com/', gemini: 'https://gemini.google.com/', claude: 'https://claude.ai/new' }
    window.open(urls[provider] || urls.chatgpt, '_blank', 'noopener,noreferrer')
  }

  return <section className="inspector-section proposal-panel"><div className="section-title"><span>Proposta</span><span className="section-index">05</span></div><p className="settings-help">Guarde aqui o material comercial específico desta empresa.</p><input className="proposal-field" value={draft.offer_title} onChange={e => setDraft({ ...draft, offer_title: e.target.value })} placeholder="Título da oferta" /><textarea value={draft.proposal_text} onChange={e => setDraft({ ...draft, proposal_text: e.target.value })} rows={8} placeholder="Texto da proposta / escopo..." /><div className="proposal-grid"><input value={draft.price} onChange={e => setDraft({ ...draft, price: e.target.value })} placeholder="Investimento" /><input value={draft.delivery_time} onChange={e => setDraft({ ...draft, delivery_time: e.target.value })} placeholder="Prazo de entrega" /></div><textarea value={draft.notes} onChange={e => setDraft({ ...draft, notes: e.target.value })} rows={4} placeholder="Observações internas" /><div className="composer-actions"><button className="button button--quiet" type="button" onClick={() => void save()} disabled={saving}><SaveRegular /> {saving ? 'Salvando…' : saved ? 'Salvo' : 'Salvar'}</button><button className="button button--quiet" type="button" onClick={() => void copy()} disabled={!proposalForCopy}><ClipboardRegular /> {copied ? 'Copiado' : 'Copiar'}</button></div><button className="button button--primary button--full" type="button" onClick={openAi}><SparkleRegular /> Preparar com IA</button></section>
}
