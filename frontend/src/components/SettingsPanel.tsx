import { useEffect, useMemo, useState } from 'react'
import type { LeadFlowSettings } from '../lib/types'

const AI_OPTIONS = {
  text: [['chatgpt', 'ChatGPT'], ['gemini', 'Gemini'], ['claude', 'Claude']] as const,
  image: [['chatgpt', 'ChatGPT'], ['gemini', 'Gemini'], ['midjourney', 'Midjourney']] as const,
  prototype: [['v0', 'v0'], ['lovable', 'Lovable'], ['chatgpt', 'ChatGPT'], ['gemini', 'Gemini'], ['claude', 'Claude']] as const,
}

const VARIABLES = [
  ['{{name}}', 'Nome público da empresa.', 'Use para personalizar saudações, títulos e prompts.'],
  ['{{segment}}', 'Segmento encontrado na busca.', 'Ajuda a adaptar a abordagem, copy e conceito ao nicho.'],
  ['{{city}}', 'Cidade do lead.', 'Use para localização, contexto comercial e personalização.'],
  ['{{state}}', 'Estado / UF do lead.', 'Complementa a localização quando o contexto regional importa.'],
  ['{{opportunity_type}}', 'Tipo de oportunidade detectado.', 'Ex.: novo site, rebuild, redesign ou otimização.'],
  ['{{lead_context}}', 'Resumo consolidado do lead.', 'Inclui evidências, contatos, presença digital e sinais disponíveis.'],
] as const

const DEFAULT_SETTINGS: LeadFlowSettings = {
  contact_message_template: 'Olá! Tudo bem? Vi o trabalho da {{name}} e achei muito interessante. Trabalho com desenvolvimento de sites e tive algumas ideias de como melhorar a presença digital de vocês. Posso te mostrar uma ideia sem compromisso?',
  site_text_prompt_template: 'Crie um conceito completo de website comercial para {{name}}, segmento {{segment}}, cidade {{city}}/{{state}}. Use apenas os fatos fornecidos. Defina posicionamento, sitemap, hero, proposta de valor, CTAs, seções, copy sugerida, direção visual e estratégia de conversão. Não invente fatos; marque hipóteses.\n\nDADOS DO LEAD:\n{{lead_context}}',
  visual_prompt_template: 'GERE IMAGENS CONCEPT PARA APRESENTAÇÃO COMERCIAL. Crie uma direção visual premium para {{name}}, segmento {{segment}}. Gere propostas de hero, mockup de homepage e cenas para apresentação. Use os dados abaixo apenas como contexto e não invente fatos da empresa.\n\nDADOS DO LEAD:\n{{lead_context}}',
  prototype_prompt_template: 'CONSTRUA UM PROTÓTIPO FUNCIONAL DE WEBSITE responsivo para {{name}}, segmento {{segment}}. Gere uma interface real e navegável, com homepage, hero, serviços, prova social, galeria e contato. Use placeholders quando faltar informação e não invente fatos. O resultado deve ser uma base de demonstração para proposta comercial.\n\nDADOS DO LEAD:\n{{lead_context}}',
  text_ai: 'chatgpt',
  image_ai: 'chatgpt',
  prototype_ai: 'v0',
}

type Props = { value?: LeadFlowSettings; saving?: boolean; onSave: (value: LeadFlowSettings) => void }
const STORAGE_KEY = 'leadflow.settings.v1'

function loadLocalSettings(): LeadFlowSettings {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_SETTINGS
    return { ...DEFAULT_SETTINGS, ...JSON.parse(raw) }
  } catch { return DEFAULT_SETTINGS }
}

function saveLocalSettings(value: LeadFlowSettings) {
  try { window.localStorage.setItem(STORAGE_KEY, JSON.stringify(value)) } catch { /* ignore */ }
}

export function SettingsPanel({ value, saving, onSave }: Props) {
  const [draft, setDraft] = useState<LeadFlowSettings>(() => typeof window === 'undefined' ? DEFAULT_SETTINGS : loadLocalSettings())
  const [activeSection, setActiveSection] = useState('contact')
  const [copiedToken, setCopiedToken] = useState('')

  useEffect(() => {
    if (value) {
      setDraft(value)
      saveLocalSettings(value)
    }
  }, [value])

  const dirty = useMemo(() => JSON.stringify(draft) !== JSON.stringify(value ?? DEFAULT_SETTINGS), [draft, value])

  function update<K extends keyof LeadFlowSettings>(key: K, next: LeadFlowSettings[K]) {
    setDraft((current) => ({ ...current, [key]: next }))
  }

  async function copyToken(token: string) {
    try {
      await navigator.clipboard.writeText(token)
      setCopiedToken(token)
      window.setTimeout(() => setCopiedToken(''), 1200)
    } catch { /* clipboard may be blocked */ }
  }

  function restoreDefaults() {
    setDraft(DEFAULT_SETTINGS)
  }

  return (
    <section className="settings-page">
      <header className="settings-hero">
        <div>
          <span className="settings-hero__eyebrow">PERSONALIZAÇÃO DO WORKFLOW</span>
          <h1>Seu LeadFlow, seu jeito de vender.</h1>
          <p>Defina uma vez suas mensagens, prompts e ferramentas. O LeadFlow reutiliza tudo automaticamente em cada empresa.</p>
        </div>
        <div className="settings-hero__status">
          <span className="settings-status__dot" />
          <div><strong>Configuração local</strong><span>salva no dispositivo</span></div>
        </div>
      </header>

      <div className="settings-layout">
        <aside className="settings-nav-card">
          <div className="settings-nav-card__title">Seções</div>
          {[
            ['contact', 'Contato', 'Mensagem padrão'],
            ['text', 'Texto', 'Conceito e copy'],
            ['image', 'Imagens', 'Prompts visuais'],
            ['prototype', 'Protótipo', 'Site demonstrável'],
          ].map(([id, title, hint]) => (
            <button key={id} type="button" className={`settings-nav-item ${activeSection === id ? 'is-active' : ''}`} onClick={() => document.getElementById(`settings-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
              <span className="settings-nav-item__number">0{['contact','text','image','prototype'].indexOf(id) + 1}</span>
              <span><strong>{title}</strong><small>{hint}</small></span>
            </button>
          ))}
          <div className="settings-nav-card__tip"><strong>Dica</strong><span>Clique em uma variável para copiar o comando e usar no texto.</span></div>
        </aside>

        <div className="settings-content">
          <section className="settings-card" id="settings-contact">
            <div className="settings-card__head"><div><span className="settings-card__index">01</span><div><p className="section-kicker">Contato</p><h2>Mensagem padrão</h2><p>Seu texto base para primeiro contato. Você ainda pode editar a mensagem antes de enviar.</p></div></div><span className="settings-chip">WhatsApp / Instagram</span></div>
            <textarea className="prompt-editor prompt-editor--compact" value={draft.contact_message_template} onChange={(e) => update('contact_message_template', e.target.value)} rows={7} />
            <div className="settings-card__footer"><span>Variáveis funcionam aqui também.</span><button className="button button--quiet" type="button" onClick={() => update('contact_message_template', DEFAULT_SETTINGS.contact_message_template)}>Restaurar padrão</button></div>
          </section>

          <section className="settings-card" id="settings-text">
            <div className="settings-card__head"><div><span className="settings-card__index">02</span><div><p className="section-kicker">IA para texto</p><h2>Conceito & copy</h2><p>Use para criar a estratégia do site, estrutura de páginas, copy e argumentos comerciais.</p></div></div><label className="ai-picker"><span>Ferramenta</span><select value={draft.text_ai} onChange={(e) => update('text_ai', e.target.value as LeadFlowSettings['text_ai'])}>{AI_OPTIONS.text.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label></div>
            <textarea className="prompt-editor" value={draft.site_text_prompt_template} onChange={(e) => update('site_text_prompt_template', e.target.value)} rows={12} />
            <div className="settings-card__footer"><span>O LeadFlow injeta os dados do lead automaticamente.</span><button className="button button--quiet" type="button" onClick={() => update('site_text_prompt_template', DEFAULT_SETTINGS.site_text_prompt_template)}>Restaurar prompt</button></div>
          </section>

          <section className="settings-card" id="settings-image">
            <div className="settings-card__head"><div><span className="settings-card__index">03</span><div><p className="section-kicker">IA para imagens</p><h2>Direção visual & geração</h2><p>Este é o prompt para pedir <strong>imagens reais</strong>: hero, mockups, cenas e referências visuais para sua proposta.</p></div></div><label className="ai-picker"><span>Ferramenta</span><select value={draft.image_ai} onChange={(e) => update('image_ai', e.target.value as LeadFlowSettings['image_ai'])}>{AI_OPTIONS.image.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label></div>
            <textarea className="prompt-editor" value={draft.visual_prompt_template} onChange={(e) => update('visual_prompt_template', e.target.value)} rows={12} />
            <div className="settings-card__footer"><span>Objetivo: sair do conceito escrito e chegar a material visual.</span><button className="button button--quiet" type="button" onClick={() => update('visual_prompt_template', DEFAULT_SETTINGS.visual_prompt_template)}>Restaurar prompt</button></div>
          </section>

          <section className="settings-card" id="settings-prototype">
            <div className="settings-card__head"><div><span className="settings-card__index">04</span><div><p className="section-kicker">IA para protótipo</p><h2>Site demonstrável</h2><p>Prompt para ferramentas que criam uma interface navegável que você pode mostrar ao cliente.</p></div></div><label className="ai-picker"><span>Ferramenta</span><select value={draft.prototype_ai} onChange={(e) => update('prototype_ai', e.target.value as LeadFlowSettings['prototype_ai'])}>{AI_OPTIONS.prototype.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label></div>
            <textarea className="prompt-editor" value={draft.prototype_prompt_template} onChange={(e) => update('prototype_prompt_template', e.target.value)} rows={12} />
            <div className="settings-card__footer"><span>Ideal para gerar uma demo rapidamente após qualificar o lead.</span><button className="button button--quiet" type="button" onClick={() => update('prototype_prompt_template', DEFAULT_SETTINGS.prototype_prompt_template)}>Restaurar prompt</button></div>
          </section>

          <section className="settings-card settings-card--reference">
            <div className="settings-card__head"><div><span className="settings-card__index">05</span><div><p className="section-kicker">Referência rápida</p><h2>Variáveis disponíveis</h2><p>Use estas variáveis em mensagens e prompts. O LeadFlow substitui cada comando pelos dados do lead.</p></div></div><span className="settings-chip settings-chip--soft">6 variáveis</span></div>
            <div className="variable-grid">
              {VARIABLES.map(([token, label, description]) => (
                <button type="button" key={token} className="variable-card" onClick={() => void copyToken(token)} title="Copiar variável">
                  <div className="variable-card__top"><code>{token}</code><span>{copiedToken === token ? 'Copiado' : 'Copiar'}</span></div>
                  <strong>{label}</strong><small>{description}</small>
                </button>
              ))}
            </div>
          </section>
        </div>
      </div>

      <div className="settings-savebar">
        <div><span className={`settings-savebar__dot ${dirty ? 'is-dirty' : ''}`} /><div><strong>{dirty ? 'Alterações pendentes' : 'Tudo salvo'}</strong><span>{dirty ? 'Salve quando terminar de editar.' : 'Seu padrão está pronto para reutilização.'}</span></div></div>
        <div className="settings-savebar__actions"><button className="button button--quiet" type="button" onClick={restoreDefaults}>Restaurar tudo</button><button className="button button--primary" type="button" disabled={!dirty || saving} onClick={() => { saveLocalSettings(draft); onSave(draft) }}>{saving ? 'Salvando…' : 'Salvar configurações'}</button></div>
      </div>
    </section>
  )
}
