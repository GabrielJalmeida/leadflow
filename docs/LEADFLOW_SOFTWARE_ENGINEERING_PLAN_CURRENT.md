# LeadFlow — Plano de Engenharia Atualizado, Estado Real e Roadmap para v1.0

**Documento vivo de engenharia e continuidade do projeto**  
**Atualização:** 13 de setembro de 2026  
**Fonte de verdade desta revisão:** `leadflow-agent.zip` fornecido nesta conversa + referência visual final do dashboard + plano anterior de 10/09/2026  
**Versão declarada no pacote:** `0.2.0a1`  
**Git HEAD presente no ZIP:** `4db08ab` — `feat: add React frontend and adaptive lead discovery`  
**Estado adicional no working tree:** Phase 8.4.3 — Qualified Result Fulfillment  
**Testes verificados nesta revisão:** **199/199 passando** com `python -m unittest discover -s tests -q`  
**Fase atual:** **8.4.4 Real-World Quality Validation — Fast Capture + Investigator Fast Path implementados; próximo gate externo é um smoke de integração somente quando o core local estiver estável**  
**Estado do produto:** alpha funcional, local-first, ainda não v1.0 pública

---

# 1. Resumo executivo atualizado

O LeadFlow deixou de ser apenas um protótipo de descoberta de empresas. A versão atual já possui um núcleo de pesquisa, qualificação, auditoria e oportunidade comercial integrado a uma API local e a uma interface React funcional.

O risco principal do projeto também mudou.

Na fase inicial, a pergunta era:

> Conseguimos transformar pesquisa web em empresas reais e utilizáveis?

Essa hipótese já foi validada.

Depois, o problema passou a ser:

> Se o usuário pedir 10 leads, o produto consegue retornar 10 em vez de encerrar prematuramente com 2, 3 ou 7?

As fases 8.4, 8.4.1, 8.4.2 e 8.4.3 atacaram exatamente esse problema. O sistema atual amplia o plano de consultas, utiliza múltiplas capacidades de descoberta quando disponíveis, aumenta a reserva de investigação e, desde a 8.4.3, **não considera o pool bruto de candidatos como suficiente quando esses candidatos provavelmente serão rejeitados pelos filtros finais**.

O próximo risco é mais importante do que quantidade:

> Os 10 leads entregues são realmente 10 bons leads?

Por isso, **não devemos continuar adicionando funcionalidades antes de validar a qualidade real do retorno**.

A prioridade imediata é a **Phase 8.4.4 — Real-World Quality Validation**, usando benchmarks manuais em diferentes segmentos e cidades. A meta é medir precisão, duplicação, qualidade de contato, atribuição correta de website, aderência geográfica e capacidade de cumprir a quantidade solicitada sem degradar a qualidade.

**Atualização de implementação da 8.4.4:** o benchmark harness já foi criado em `benchmarks/` + `scripts/run_benchmark.py`. Ele carrega os cinco casos oficiais sem dependência externa de YAML, executa a busca com o perfil real do produto, salva `run.json`, `leads.csv`, `review.csv`, `metrics.json` e `summary.md`, e mantém a verdade de mundo real como revisão humana (`PASS` / `FAIL` / `UNCERTAIN`). O validity guard agora considera tanto falhas globais de provider/rede quanto a taxa de auditorias inconclusivas especificamente entre os leads finais que possuem website.

O primeiro run real enviado pelo usuário (`marcenaria + Praia Grande/SP + 10`) cumpriu **10/10** e foi revisado manualmente. A camada de discovery teve resultado forte: **Precision@N 100%**, **phone plausibility 100%**, **duplicate rate 0%** e **false-merge rate 0%**. Identity precision, canonical-name precision, contact usefulness e evidence sufficiency ficaram em **90%**. O overall PASS por linha ficou em **70%**, principalmente por dois falsos `REBUILD` causados por auditoria DNS inconclusiva e por um caso de identidade/unidade comercial ambígua.

Esse run revelou uma falha do próprio validity guard: o erro global de website audit era apenas `3/10`, mas **os dois leads finais com website estavam 2/2 inconclusivos**. O harness antigo marcou a medição como válida; a regra nova a marca corretamente como inválida para o gate oficial. Portanto, o run conta como **amostra diagnóstica revisada**, não como `1/5` oficial.

Foi aplicado um primeiro patch estreito permitido durante a 8.4.4: falha de resolução DNS deixou de ser tratada como SSRF/safety block, auditoria inconclusiva deixou de virar `REBUILD`, o validity guard passou a medir auditorias dos leads finais e a pré-qualificação de discovery passou a adiar filtros que só existem após investigação/audit.

O **segundo run real** mostrou que essa correção funcionou parcialmente na eficiência de discovery: o planner caiu de **20 para 9 queries**, encontrou **37 candidatos únicos** e classificou **31 como pré-qualificados**. Entretanto, somente **5/10** sobreviveram ao filtro final. A análise do código encontrou um bug determinístico na ordenação do Investigator: a chave usava `not _preliminary_accepts(...)` junto com `reverse=True`, o que fazia o sistema gastar a reserva de investigação primeiro em candidatos que **não** satisfaziam os sinais baratos de contato. O mesmo princípio de prioridade foi então aplicado também aos candidatos de website/browser/visual audit. O report agora registra `filter_rejection_reasons`, permitindo explicar precisamente por que candidatos são eliminados no próximo run. A suíte naquela revisão possuía **187/187 testes passando**; o Fast Capture Loop levou a baseline a **191/191** e o Investigator Fast Path atual elevou a suíte para **199/199**.

Esse segundo run também permanece diagnóstico: houve **1 erro externo/timeout**, **5/10 website audits inconclusivos** e a medição foi corretamente marcada como inválida. Além disso, duas linhas com o nome `MP Marcenaria` e telefones diferentes mostraram um possível risco de duplicação pós-investigação que deverá ser observado no próximo rerun antes de qualquer regra de merge mais agressiva. Depois disso, um smoke replayável de 3 leads confirmou o priority fix, mas também mostrou que o gargalo de parede estava no Investigator/Gemini e em falhas externas. O Investigator Fast Path foi então implementado e validado localmente por regressão + replay. O próximo run externo deve ser apenas um **smoke de integração**, não um ciclo de debug; somente depois de a integração/latência ficar estável fazemos o benchmark oficial de 10 leads que pode contar como `1/5`.

A interface enviada como referência continua sendo a direção visual e comportamental final do produto. O frontend atual já reproduz o núcleo dessa experiência — busca, tabela densa, painel lateral, estados de execução e preparação de contato — mas ainda possui áreas propositalmente adiadas, como biblioteca completa de leads, histórico operacional, configurações de providers, campanhas e relatórios.

---

# 2. Regra central do projeto

A regra de engenharia que deve continuar guiando o LeadFlow é:

> **False association is worse than missing information.**

Em português:

> **Associar um telefone, site, perfil ou empresa errada é pior do que deixar o campo vazio.**

Essa regra se aplica a:

- identidade da empresa;
- website oficial;
- telefone;
- cidade/estado;
- perfis sociais;
- deduplicação;
- auditoria;
- scoring;
- preparação de contato.

A segunda regra, adicionada pelas fases 8.4.x, é:

> **A quantidade solicitada é um objetivo de fulfillment, mas nunca autoriza reduzir silenciosamente os critérios de qualidade.**

Portanto:

```text
10 solicitados
    ↓
procurar mais candidatos se necessário
    ↓
qualificar
    ↓
filtrar
    ↓
entregar até 10 bons leads
    ↓
se não for possível: retornar resultado parcial explícito
```

Nunca:

```text
10 solicitados
    ↓
retornar qualquer coisa até completar 10
```

---

# 3. Definição atual do produto

## 3.1 Problema do usuário

> Preciso encontrar empresas com potencial comercial para o serviço que vendo sem pesquisar manualmente uma por uma, e preciso entender por que cada empresa é ou não uma boa oportunidade.

## 3.2 Proposta de valor atual

> LeadFlow transforma uma intenção comercial em uma lista priorizada de empresas verificáveis, com contato, presença digital, identidade, auditoria de website, sinais de oportunidade e evidências suficientes para que o usuário decida quem abordar.

## 3.3 Público inicial

- freelancer;
- desenvolvedor que vende sites;
- agência pequena;
- operador comercial;
- profissional que realiza prospecção manual recorrente.

## 3.4 Objetivo comercial primário da versão atual

O perfil principal continua sendo **Website Sales**:

- encontrar empresas sem website identificado;
- encontrar websites tecnicamente fracos;
- encontrar problemas objetivos de experiência;
- identificar oportunidades de redesign quando a camada visual estiver ativada;
- priorizar empresas contactáveis;
- preparar contato manual assistido.

## 3.5 O que o LeadFlow NÃO é nesta fase

O LeadFlow ainda não é:

- plataforma de disparo em massa;
- automação de cold WhatsApp;
- CRM completo;
- HubSpot local;
- ferramenta de scraping autenticado;
- crawler irrestrito;
- plataforma cloud multiusuário;
- agente autônomo autorizado a enviar mensagens sem revisão;
- solução de billing/assinatura.

---

# 4. Situação geral do projeto em 13/09/2026

| Área | Estado atual | Avaliação |
|---|---|---|
| Descoberta de empresas | Implementada | Funcional |
| Planejamento de queries | Gemini + fallback determinístico | Funcional |
| Extração de empresas | Gemini + fallback heurístico quando disponível | Funcional |
| Multi-source discovery | Local + web na mesma rodada | Implementado |
| Round-robin de providers | Implementado | Funcional |
| Deduplicação | Conservadora, baseada em sinais fortes | Funcional, precisa benchmark real |
| Identidade comercial | Estados explícitos + confiança | Implementado |
| Telefone | Classificação móvel/fixo + sanitização | Implementado |
| Estratégia digital-first | Implementada | Funcional |
| Lead Investigator | Implementado e budget-aware | Funcional |
| Website status | UNKNOWN / PRESENT / NOT_FOUND / UNREACHABLE | Implementado |
| Website audit HTTP | Implementado | Funcional |
| Browser/UX audit | Implementado, opcional | Funcional com Playwright |
| Visual AI audit | Implementado, opcional | Funcional com Gemini |
| Opportunity Intelligence | Implementado | Funcional |
| Cache persistente | Implementado | Funcional |
| Lead memory | Implementada | Funcional |
| Runtime budgets | Implementados | Funcional |
| Circuit breaker | Implementado | Funcional |
| Cancelamento | Implementado | Funcional |
| Resultado parcial explícito | Implementado | Funcional |
| Fulfillment de quantidade | Implementado | Phase 8.4.3 |
| SQLite | Implementado | Funcional |
| Migração SQLite | `PRAGMA user_version` + migração idempotente | Funcional |
| API local FastAPI | Implementada | Funcional |
| Frontend React | Implementado | Slice principal funcional |
| Preparação de contato | WhatsApp/Instagram manual assistido | Funcional |
| Histórico completo no frontend | Não | Pendente |
| Configuração de API keys pelo painel | Não | Pendente |
| Leads library completa | Não | Pendente |
| Campanhas / CRM | Não | Fora do slice atual |
| Relatórios | Não | Futuro |
| Empacotamento Windows | Não | Futuro |
| Benchmark real multi-segmento | Ainda não concluído | **Próxima prioridade** |

---

# 5. Baseline técnica real do ZIP atual

## 5.1 Versionamento

O código atual declara:

```text
leadflow_agent.__version__ = 0.2.0a1
pyproject.toml version     = 0.2.0a1
API_VERSION               = 1.0
FRONTEND_CONTRACT_VERSION = 1.0
```

O documento antigo e parte dos docs internos ainda utilizam `0.1.4-dev`. Isso é dívida documental e deve ser corrigido antes da próxima release.

## 5.2 Git

Branch no ZIP:

```text
feat/frontend-v0
```

HEAD:

```text
4db08ab feat: add React frontend and adaptive lead discovery
```

Commits imediatamente anteriores relevantes:

```text
1a9aac4 feat: add quota fulfillment and pt-br interface
cca0730 feat: improve lead quality and result fulfillment
d27b034 feat: add contact workspace and local application API
768b6ec feat: add functional frontend v0
```

A **Phase 8.4.3** está presente no working tree e também como:

```text
leadflow-phase8.4.3-qualified-fulfillment.patch
```

Portanto, antes de avançar em desenvolvimento normal, essa fase deve ser consolidada em commit próprio depois do benchmark/regression check desejado.

## 5.3 Testes

Comando executado nesta revisão:

```bash
python -m unittest discover -s tests -v
```

Resultado:

```text
Ran 181 tests
OK
```

Isso valida a regressão automatizada da base atual, mas **não substitui o benchmark real da Phase 8.4.4**.

---

# 6. Evolução do projeto — fases concluídas

Esta seção substitui o roadmap antigo baseado em semanas hipotéticas. A partir de agora, o projeto é acompanhado pelo que realmente foi implementado.

## 6.1 v0.1.3 — Discovery proof

Validou o princípio:

```text
web search
   ↓
evidence
   ↓
AI extraction
   ↓
real businesses
```

Principais pontos:

- Tavily como baseline de pesquisa web;
- Gemini como planner/extractor;
- múltiplas empresas extraídas de uma única evidência;
- CLI;
- SQLite;
- CSV/JSON;
- dedupe básico;
- scoring básico.

## 6.2 Data Quality / Identity Core

Implementado posteriormente:

- `IdentityStatus` explícito;
- comparação por telefone, domínio, nome e localidade;
- prevenção de associação por nome sozinho;
- candidatos rejeitados persistidos;
- conflitos geográficos tratados como evidência negativa;
- website não atribuído apenas porque “parece plausível”.

Estados atuais:

```text
UNVERIFIED
MATCHED
PROBABLE_MATCH
AMBIGUOUS
MISMATCH
```

## 6.3 Lead Investigator

Implementado:

- investigação limitada por lead;
- queries específicas para campos faltantes;
- uso explícito de budget;
- merge conservador;
- website `NOT_FOUND` apenas após investigação dedicada;
- reaproveitamento de memória recente;
- preservação de localidades observadas pela evidência.

## 6.4 Cache + Lead Memory

Implementado:

- cache SQLite de pesquisas;
- TTL configurável;
- refresh explícito;
- métricas de hit/miss/write;
- memória de campos verificados;
- memória de candidatos rejeitados;
- `NOT_FOUND` expira e volta a ser desconhecido quando antigo;
- mesma empresa não é hidratada apenas por nome+cidade.

## 6.5 Resilience & Quality Guardrails

Implementado:

- retries transitórios Gemini;
- backoff exponencial + jitter;
- quality gate de empresas;
- rejeição de nomes genéricos/plataformas/diretórios;
- sanitização de telefone;
- taxonomia de erros;
- runtime budget;
- cancellation;
- circuit breaker.

## 6.6 Website Verification & HTTP Audit

Implementado:

- site oficial separado de site desconhecido;
- auditoria HTTP opt-in;
- HTTPS;
- status;
- redirects;
- tempo de resposta;
- title;
- meta description;
- viewport;
- forms;
- links de contato;
- score técnico;
- SSRF-oriented URL safety;
- cache/memory de auditoria.

## 6.7 Opportunity Intelligence

Implementado:

```text
new_site
rebuild
redesign
optimization
review_needed
low_opportunity
```

A decisão comercial é separada de identidade e de fatos técnicos.

Um site tecnicamente saudável não é automaticamente visualmente bom.

## 6.8 Browser / UX Intelligence

Implementado como camada opcional:

- Playwright;
- overflow mobile;
- CTA visível;
- navegação;
- erros de console;
- page errors;
- screenshots desktop/mobile;
- score de browser UX.

## 6.9 Visual Intelligence

Implementado como camada opcional:

- screenshots do browser audit;
- avaliação multimodal Gemini;
- modernidade;
- hierarquia;
- coerência de marca;
- legibilidade;
- clareza de conversão;
- confidence gate.

Visual AI não pode alterar identidade nem fatos HTTP.

## 6.10 Search Profiles & Filters

Implementado:

- segmentos preset + free text;
- perfis reutilizáveis;
- filtros por website;
- Instagram;
- telefone;
- e-mail;
- readiness;
- tipo de oportunidade;
- scores técnicos/browser/visual;
- score mínimo de oportunidade;
- presença de contato.

## 6.11 Runtime Safety & Provider Foundation

Implementado:

- máximo normal de 100 leads;
- budgets independentes;
- usage counters;
- provider capabilities;
- cache integrado ao accounting;
- resultados parciais em vez de crash quando o budget termina.

## 6.12 Security Boundaries

Implementado:

- contract versionado frontend/backend;
- sanitização conservadora de input;
- redaction de secrets;
- caminhos de artefato seguros;
- prompts tratam conteúdo web como não confiável;
- API local com host/origin safeguards;
- migration SQLite versionada.

## 6.13 Phase 8.1 — Contact Workspace v0

Implementado:

- preparação de contato assistida;
- WhatsApp click-to-chat com mensagem editável;
- Instagram como canal alternativo;
- preferência por Instagram sobre telefone fixo sem evidência de WhatsApp;
- número móvel = candidato a WhatsApp, não confirmação de conta;
- mensagem adaptada ao tipo de oportunidade;
- usuário continua responsável por revisar e enviar.

## 6.14 Phase 8.2 — Local Application API

Implementado:

- FastAPI local;
- bind em `127.0.0.1` na execução local;
- runs assíncronos em processo;
- polling;
- cancelamento;
- catálogo de providers;
- catálogo de segmentos;
- catálogo de perfis;
- preparação de contato;
- contrato mínimo de frontend.

## 6.15 Phase 8.3 — Frontend React vertical slice

Implementado:

```text
Search
  ↓
Run state
  ↓
Results table
  ↓
Lead inspector
  ↓
Prepared contact
```

O frontend atual já é um produto utilizável para o slice principal, não apenas um mockup.

## 6.16 Phase 8.4 — Lead Quality

Implementado:

- classificação de telefone em móvel/fixo;
- modo `digital-first` remove telefone fixo do contato primário;
- dedupe por domínio forte;
- empresas iguais com celulares realmente distintos podem permanecer separadas;
- telefone fixo não gera pontuação artificial de contactability;
- defaults de busca ampliados;
- plano curto pode ser expandido para utilizar o budget disponível;
- pool de candidatos maior para filtros mais exigentes.

## 6.17 Phase 8.4.1 — Quota Fulfillment

Implementado:

- `fulfill_quota=True` por padrão;
- quantidade pedida deixa de ser apenas uma sugestão;
- o sistema amplia max queries e candidate pool dentro de limites rígidos;
- se terminar com menos resultados do que solicitado, o run vira `partial_results`;
- UI não apresenta shortfall como sucesso completo.

## 6.18 Phase 8.4.2 — Adaptive Discovery

Implementado:

- fontes locais e web podem atuar na mesma rodada;
- `RoundRobinLocalSearchProvider`;
- `RoundRobinWebSearchProvider`;
- uma fonte web pode falhar sem interromper automaticamente a outra;
- `auto` usa as capacidades configuradas;
- queries sociais ganham ângulo de recuperação próprio;
- budgets default permitem descoberta mais ampla.

## 6.19 Phase 8.4.3 — Qualified Result Fulfillment

**Última fase implementada.**

Problema resolvido:

O mecanismo anterior podia encontrar candidatos brutos suficientes para encher o `target_pool`, parar a descoberta e somente depois descobrir que muitos seriam rejeitados pelos filtros finais.

Exemplo:

```text
pedido: 10
pool bruto: 50
pool bruto considerado “suficiente”
↓
filtro digital-first remove fixos
↓
filtros de oportunidade removem outros
↓
resultado final: 3
```

A 8.4.3 altera o critério de parada.

Agora o agente acompanha:

```text
unique_candidates
prequalified_candidates
```

E, com fulfillment ativo, continua buscando até que:

- exista quantidade preliminarmente qualificada suficiente; ou
- o limite rígido de candidatos seja atingido; ou
- as queries terminem; ou
- o budget seja consumido; ou
- o usuário cancele.

Também foi adicionado um pequeno `qualification_buffer` quando existem etapas profundas de pós-processamento, reduzindo o risco de ficar abaixo da quota depois de investigação/auditoria.

Quando há shortage antes do Investigator, o limite efetivo de investigação pode ser aumentado de forma controlada para tentar converter candidatos ainda incompletos em leads elegíveis.

Contrato do frontend agora inclui:

```json
"discovery": {
  "queries_executed": 0,
  "unique_candidates": 0,
  "prequalified_candidates": 0
}
```

Testes específicos atuais:

- pool bruto cheio + candidatos não elegíveis não encerra prematuramente;
- comportamento antigo permanece quando fulfillment é desligado;
- queries esgotadas sem leads elegíveis retornam `partial_results` explícito.

---

# 7. Arquitetura atual implementada

O LeadFlow é hoje um **modular monolith local-first**.

```text
┌─────────────────────────────────────────────────────────────┐
│ React / TypeScript Frontend                                 │
│ Search · Run · Results · Inspector · Contact                │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP localhost
┌──────────────────────────────▼──────────────────────────────┐
│ FastAPI Local Application API                               │
│ /health · /catalog · /runs · /contact                      │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ Search Service / Application Layer                          │
│ validation · profiles · filters · budgets · persistence     │
└──────────────────────────────┬──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│ LeadResearchAgent                                           │
│ planner                                                     │
│ local discovery + web discovery                             │
│ extractor                                                   │
│ quality gate                                                │
│ dedupe                                                      │
│ memory                                                      │
│ investigator                                                │
│ website audit                                               │
│ browser audit                                               │
│ visual audit                                                │
│ opportunity scoring                                         │
└───────────┬──────────────────┬───────────────────┬───────────┘
            │                  │                   │
     Search Providers       Gemini             SQLite
   Tavily/Brave/etc.   planner/extractor/     cache/memory/
                          visual               reports
```

A arquitetura continua correta para o estágio atual. Não há justificativa para quebrá-la em microservices.

---

# 8. Stack REAL atual

O plano antigo recomendava algumas tecnologias que não foram adotadas. Este documento passa a diferenciar **implementado** de **possível refactor futuro**.

## 8.1 Backend

Implementado:

```text
Python >= 3.11
setuptools / pyproject.toml
FastAPI (extra opcional api)
Uvicorn
Pydantic via FastAPI models
sqlite3 nativo
urllib/custom JsonHttpClient
Playwright opcional
```

Não implementado atualmente:

```text
uv como gerenciador obrigatório
SQLAlchemy
Alembic
HTTPX
keyring
Google GenAI SDK
Pydantic Structured Outputs no Gemini
```

Esses itens **não devem virar refactor obrigatório apenas porque estavam no plano antigo**.

Regra nova:

> Refatorar infraestrutura somente quando existir uma falha real, requisito de distribuição ou custo de manutenção que justifique a mudança.

## 8.2 Frontend

Stack real atual:

```text
React 19.3
React DOM 19.3
TypeScript 7
Vite 8.2
TanStack Query 5
TanStack Table 9
Zustand 5
Fluent UI React Icons
CSS próprio
```

O frontend **não usa Tailwind nem shadcn/ui** neste momento.

A estética atual foi construída diretamente em CSS e deve continuar sendo preservada enquanto atende a referência visual.

---

# 9. Pipeline de pesquisa atual

```text
SearchRequest
    ↓
validate_search_request
    ↓
resolve segment/profile/filter
    ↓
calculate effective fulfillment budgets
    ↓
RunController / RunBudget
    ↓
build_agent
    ↓
Query Plan
    ↓
for each query:
    ├─ Local Search (quando disponível)
    ├─ Web Search (quando disponível)
    ├─ AI extraction / heuristic fallback
    ├─ sanitize fields
    ├─ quality gate
    ├─ dedupe / merge
    └─ preliminary qualification count
    ↓
Lead Memory hydration
    ↓
preliminary scoring
    ↓
Lead Investigator
    ↓
Website HTTP Audit
    ↓
Browser / UX Audit
    ↓
Visual AI Audit
    ↓
final scoring
    ↓
final LeadFilter
    ↓
rank
    ↓
quota status
    ↓
SQLite / frontend contract / optional export
```

---

# 10. Defaults atuais de busca

O frontend envia por padrão:

```text
segment             = marcenaria
city                = Praia Grande
state               = SP
country             = Brazil
limit               = 10
max_queries         = 20
profile             = website-sales
provider            = auto
no_ai               = false
filter_pool          = 5x
contact_strategy    = digital-first
fulfill_quota       = true
cache               = true
cache_ttl           = 14 days
memory              = true
```

Features default:

```text
investigate             = true
investigation_limit     = 3 (pode aumentar efetivamente em fulfillment)
investigation_budget    = 2 searches/lead
website_audit           = true
audit_limit             = 3
browser_audit           = false
visual_audit            = false
```

Budgets default:

```text
max_search_calls     = 30
max_llm_calls        = 30
max_website_audits   = 25
max_browser_audits   = 10
max_visual_audits    = 10
```

Quando `fulfill_quota=true`, o application layer pode aumentar alguns limites efetivos dentro dos tetos de segurança.

---

# 11. Lógica atual de fulfillment

## 11.1 Objetivo

Se o usuário pede `N`, o sistema tenta entregar `N` leads finais elegíveis.

## 11.2 O que NÃO conta como fulfillment

Não basta ter:

- N URLs;
- N snippets;
- N nomes brutos;
- N empresas antes do filtro;
- N registros duplicados;
- N telefones fixos em modo digital-first.

## 11.3 Prequalified candidates

Durante discovery, cada lead pode ser submetido ao scoring determinístico e ao filtro preliminar.

O contador:

```text
discovery_prequalified
```

representa candidatos que, com os dados naquele momento, já parecem capazes de sobreviver ao filtro final.

## 11.4 Buffer de qualificação

Quando existem etapas que podem eliminar ou modificar candidatos posteriormente:

```text
enrichment
investigation
website audit
browser audit
visual audit
```

o agente busca uma pequena reserva acima da quantidade solicitada.

Objetivo:

```text
pedido 10
↓
pré-qualificar aproximadamente 12
↓
pós-processamento
↓
maior probabilidade de finalizar 10
```

## 11.5 Resultado parcial continua válido

Se os limites seguros forem atingidos:

```text
partial_results
```

é comportamento correto.

O produto não deve inventar candidatos apenas para mostrar `10/10`.

---

# 12. Providers — estratégia atual

## 12.1 Providers existentes no código

```text
Tavily     → web evidence
Brave      → web + local search
Outscraper → local/business results
Gemini     → planner + extractor + investigator extraction + visual analysis
```

## 12.2 `auto`

O modo automático é capability-based.

Se múltiplas fontes estiverem configuradas, elas podem contribuir por round-robin e por combinação local+web.

## 12.3 Decisão atual

**Não priorizar novos providers agora.**

Antes de adicionar Exa, outro search engine ou outro LLM, precisamos saber:

- onde a qualidade atual falha;
- qual provider é responsável pela falha;
- se o problema é discovery, extraction, identity, filter ou scoring.

Adicionar providers antes do benchmark pode apenas esconder a causa real.

## 12.4 Provider diversification volta a ser prioridade quando

- Phase 8.4.4 mostrar baixa cobertura consistente;
- uma cidade/segmento depender claramente de fonte diferente;
- um provider atual se tornar economicamente inviável;
- termos de uso exigirem mudança;
- disponibilidade/rate limit impedir o produto.

---

# 13. Identidade e deduplicação atuais

## 13.1 Sinais fortes

- telefone compatível;
- domínio oficial;
- identidade social forte;
- sinais de localidade coerentes.

## 13.2 Regra conservadora

```text
same name != same company
```

Especialmente quando:

- cidade diverge;
- estado diverge;
- telefones são móveis distintos;
- websites divergem.

## 13.3 Deduplication atual

O sistema já evita vários falsos merges simples, mas a Phase 8.4.4 deve medir:

```text
duplicate_rate
false_merge_rate
```

em dados reais.

---

# 14. Telefone e estratégia de contato

## 14.1 Classificação

Estados conceituais atuais:

```text
mobile
fixed_line
invalid/unknown
```

## 14.2 Digital-first

Default atual:

```text
contact_strategy = digital-first
```

Consequências:

- fixo não conta como contato digital primário;
- fixo não é tratado automaticamente como WhatsApp;
- Instagram pode ser melhor rota que fixo;
- número móvel pode gerar rota WhatsApp candidata;
- abertura do WhatsApp continua sob decisão do usuário.

## 14.3 Multichannel

Continua disponível como estratégia alternativa para usos onde telefone fixo ainda tem valor comercial.

---

# 15. Website intelligence atual

## 15.1 Website status

```text
UNKNOWN      → não investigado o suficiente
PRESENT      → site oficial/aceitável associado
NOT_FOUND    → investigação dedicada sem site oficial identificado
UNREACHABLE  → domínio associado, porém indisponível
```

## 15.2 `NOT_FOUND` não significa inexistência absoluta

Interpretação correta:

> O LeadFlow procurou dentro do escopo de investigação e não identificou um site oficial com confiança suficiente.

## 15.3 Camadas independentes

```text
Identity Confidence
    ↓
Website Technical Health
    ↓
Browser UX
    ↓
Visual Quality
    ↓
Opportunity Fit
```

Nenhuma camada deve reescrever fatos de outra camada.

---

# 16. Opportunity Intelligence atual

O score comercial é uma interpretação, não uma verdade objetiva.

Ele utiliza sinais de:

- website;
- contactability;
- identidade;
- atividade/evidência;
- técnica;
- UX;
- visual quando disponível.

Tipos atuais:

```text
NEW_SITE
REBUILD
REDESIGN
OPTIMIZATION
REVIEW_NEEDED
LOW_OPPORTUNITY
```

A UI apresenta:

- score;
- tipo;
- readiness/actionable;
- service fit;
- reasons;
- cautions.

---

# 17. API local atual

Base default:

```text
http://127.0.0.1:8765/api/v1
```

Endpoints implementados:

```text
GET  /health
GET  /catalog/segments
GET  /catalog/profiles
GET  /catalog/providers

POST /contact/prepare

POST /runs
GET  /runs/{id}
GET  /runs/{id}/result
POST /runs/{id}/cancel
```

## 17.1 O que ainda NÃO existe na API

Ainda não existe API completa para:

- listar histórico de runs;
- listar biblioteca persistida de leads;
- atualizar lifecycle/status manual;
- salvar notas;
- configurar secrets pelo frontend;
- consultar usage global/mensal;
- campanhas;
- relatórios;
- settings completos.

Esses recursos são posteriores ao benchmark de qualidade.

---

# 18. Frontend atual

## 18.1 Slice funcional existente

O frontend atual possui:

- app shell;
- navegação lateral;
- top status;
- health check da API;
- catálogo de segmentos;
- catálogo de perfis;
- catálogo de providers;
- formulário de busca;
- filtros avançados;
- toggles de investigação/auditoria;
- execução assíncrona;
- polling;
- cancelamento;
- estados de erro;
- estado de resultado parcial;
- tabela ordenável;
- seleção por mouse/teclado;
- inspector lateral;
- score de oportunidade;
- identidade;
- auditoria técnica;
- browser UX;
- visual score;
- preparação de contato;
- mensagem editável;
- abrir WhatsApp/Instagram;
- copiar mensagem;
- responsividade básica.

## 18.2 Direção visual canônica

A imagem fornecida nesta conversa é a **referência final de produto**.

Características que devem ser preservadas:

- dashboard B2B escuro premium;
- alta densidade de informação;
- navegação lateral compacta;
- grande workspace central;
- busca e filtros no topo;
- tabela de oportunidades como elemento principal;
- inspector persistente à direita no desktop;
- estados com azul/ciano/verde discretos;
- legibilidade > decoração;
- sensação de software comercial, não “site conceitual”.

## 18.3 Diferenças atuais para a referência

Ainda precisam convergir:

- naming e estrutura final da navegação;
- top global search da referência;
- biblioteca de Leads;
- Campanhas;
- Relatórios;
- Integrações;
- Configurações;
- painel mais completo de fontes/evidências;
- provider/AI status detalhado;
- histórico de runs;
- uso/quota;
- ações operacionais de lead;
- alguns refinamentos de densidade e proporção.

Esses gaps não bloqueiam a Phase 8.4.4.

---

# 19. Persistência atual

## 19.1 SQLite

Tabelas atuais principais:

```text
research_runs
leads
run_leads
```

Além das estruturas próprias de cache/memory utilizadas por seus módulos.

## 19.2 Migração

O projeto usa:

```text
PRAGMA user_version
DB_SCHEMA_VERSION = 2
```

com alterações idempotentes de colunas.

Isso substitui, na prática atual, a antiga proposta de Alembic.

## 19.3 Decisão atual

Não migrar para SQLAlchemy/Alembic agora apenas por arquitetura idealizada.

Reavaliar quando:

- migrations se tornarem numerosas/difíceis;
- houver cloud/PostgreSQL;
- múltiplos processos precisarem escrever;
- schema evoluir para CRM completo.

---

# 20. Segurança e confiabilidade atuais

Implementado:

- API local restrita;
- origin/host checks;
- input normalization;
- secret redaction;
- budget hard limits;
- cancellation;
- circuit breakers;
- retries limitados;
- conteúdo web marcado como não confiável em prompts;
- SSRF-oriented checks em auditoria;
- browser com bloqueios de rede privada;
- erros públicos estáveis;
- nenhum envio automático de contato.

## 20.1 Dívida importante: secrets

No desenvolvimento, as keys ainda são carregadas principalmente por `.env`.

O antigo plano propunha keyring. Ainda não foi implementado.

Para alpha local isso é aceitável com boas práticas, mas antes de distribuição para usuário não técnico precisamos escolher entre:

- keyring do sistema;
- sessão local;
- environment variables;
- outra solução segura comprovada.

Nunca criar criptografia caseira.

---

# 21. Release hygiene — problema atual observado

O ZIP recebido contém itens que **não devem compor um release público limpo**, incluindo artefatos de desenvolvimento e estado local, por exemplo:

- `.git/`;
- `frontend/node_modules/`;
- banco SQLite local;
- `output/` com resultados de pesquisas;
- `.env` no pacote de trabalho.

Este ZIP é útil como snapshot de desenvolvimento, mas **não é um pacote de distribuição**.

Antes de beta/release, criar um processo de build limpo que exclua obrigatoriamente:

```text
.env
*.db
output/
node_modules/
.git/
__pycache__/
*.pyc
screenshots temporários
API keys
```

Nunca presumir que o `.gitignore` sozinho limpa um ZIP criado manualmente.

---

# 22. Dívidas técnicas/documentais conhecidas

## Alta prioridade antes da beta

- benchmark real ainda não executado como suíte formal;
- Phase 8.4.3 ainda precisa ser consolidada em commit/release history;
- versão dos docs está inconsistente (`0.1.4-dev` vs `0.2.0a1`);
- CHANGELOG está historicamente desorganizado e possui seções fora de ordem;
- não existe frontend para configurar secrets;
- não existe biblioteca/histórico de runs no frontend;
- release ZIP não é higienizado;
- frontend ainda não possui testes próprios automatizados equivalentes ao backend;
- não existe E2E real do React + FastAPI + fake provider.

## Média prioridade

- Gemini continua usando REST + extração manual de JSON;
- HTTP client continua custom/urllib-style;
- banco continua com migrations manuais simples;
- evidência completa ainda não é exposta no contrato enxuto do frontend;
- API job state é recente/in-memory enquanto resultados duráveis ficam no SQLite;
- provider usage é principalmente por run, não um painel histórico completo.

## Baixa prioridade agora

- Tauri/Electron;
- cloud;
- PostgreSQL;
- Redis;
- Celery;
- microservices;
- plugin system;
- billing.

---

# 23. FASE ATUAL — 8.4.4 Real-World Quality Validation

## 23.0 Status de implementação

```text
Benchmark harness                 ✅ implementado
5 casos oficiais                  ✅ definidos
review.csv manual                 ✅ implementado
metrics/summary                   ✅ implementados + rejection reasons
validity guard infraestrutura     ✅ implementado + final-output guard
unit/regression suite             ✅ 199/199
run diagnóstico Marcenaria #1      ✅ 10/10 + revisão manual concluída
run diagnóstico Marcenaria #2      ✅ 5/10; revelou priority bug
benchmark oficial válido           0/5 — snapshot replayável disponível; integração do fast path ainda não confirmada externamente
leads manualmente avaliados         10/50 oficiais (diagnósticos não contam)
```

Além da tentativa inválida no sandbox, houve agora um run real na máquina do usuário. Ele foi excelente para discovery, mas expôs que 2/2 auditorias de website presentes nos leads finais estavam inconclusivas. A regra antiga olhava apenas a taxa global (3/10) e não invalidava o run. A regra foi corrigida; por isso este primeiro run permanece diagnóstico e deve ser repetido antes de ser contabilizado oficialmente.

## 23.0.1 Primeiro run real — achados e decisão

Caso: `marcenaria-praia-grande-sp`, target `10`.

| Métrica | Resultado diagnóstico |
|---|---:|
| Fulfillment@N | 10/10 (100%) |
| Precision@N | 100% |
| Canonical-name precision | 90% |
| Identity precision | 90% |
| Phone plausibility | 100% |
| Website attribution false positive | 0% |
| Duplicate rate | 0% |
| False-merge rate | 0% |
| Contact usefulness | 90% |
| Evidence sufficiency | 90% |
| Overall row PASS | 70% |
| Queries executed | 20 |
| Search calls | 37 |
| LLM calls | 30 |
| Final website audits inconclusive | 2/2 (100%) |

Três classes de falha apareceram:

1. **False rebuild from infrastructure** — duas empresas com domínio corretamente atribuído receberam `REBUILD` porque a auditoria local não conseguiu resolver DNS. Uma falha de resolver/timeout é evidência inconclusiva, não prova de site ruim. **Corrigido e coberto por regressão.**
2. **Discovery prequalification stage mismatch** — `website-sales` exige tipos de oportunidade produzidos apenas após investigation/audit; aplicar o filtro completo antes dessas etapas produziu `prequalified_candidates = 0` e fez o planner gastar as 20 queries. A pré-qualificação agora considera somente sinais disponíveis no estágio (contato) e usa overfetch conservador quando há filtros diferidos. **Corrigido e coberto por regressão.**
3. **Identity/unit ambiguity** — um lead apresentou conflito entre nome/unidade/contato público. Esse é um problema real de entity resolution, não um erro de infraestrutura. **Não será corrigido por um único caso; deve ser observado nos próximos benchmarks e tratado na 8.4.5 se houver padrão.**

Decisão de gate:

```text
run revisado?                         sim
discovery útil?                       sim
medição final de opportunity válida?  não
conta como benchmark oficial?         não
próxima ação                          rerun do mesmo caso após patch
```

## 23.0.2 Segundo run real — achados e patch de prioridade

Caso: `marcenaria-praia-grande-sp`, target `10`, após o primeiro patch de estabilização.

| Métrica | Resultado diagnóstico |
|---|---:|
| Fulfillment@N | 5/10 (50%) |
| Queries executed | 9 |
| Unique candidates | 37 |
| Prequalified candidates | 31 |
| Duplicates removed durante discovery | 39 |
| Investigated leads | 13 |
| Investigation searches | 24 |
| Filter candidates seen | 37 |
| Filter rejected | 32 |
| Search calls | 33 |
| LLM calls | 33 |
| Website audits | 10 |
| Website audit errors | 5/10 |
| External/provider/network errors | 1 |
| Quality-gate measurement valid | false |

A redução de `20 → 9` queries confirma que a pré-qualificação por estágio corrigiu o desperdício anterior. O novo gargalo passou a ser **post-processing**: havia candidatos suficientes, mas a reserva de investigação era consumida na ordem errada.

Bug encontrado:

```python
key=lambda item: (
    not _preliminary_accepts(item, lead_filter),
    ...
),
reverse=True
```

Com `reverse=True`, candidatos que **falhavam** a pré-qualificação (`not ... == True`) iam para o topo. Isso contradizia o objetivo da Phase 8.4.3/8.4.4: gastar investigação nos candidatos com maior probabilidade de virar resultado final.

Patch aplicado:

```text
1. prequalified/contactable candidates first in Investigator
2. same qualification-first priority for website/browser/visual audit pools
3. aggregate filter_rejection_reasons in ResearchReport
4. benchmark summary prints rejection reason counts
5. regression test reproduces the ordering bug
```

A suíte passou de `185` para **187 testes**.

Observação adicional: o rerun retornou duas entradas `MP Marcenaria` com telefones diferentes e evidências parcialmente sobrepostas. Isso é um **sinal de possível duplicata pós-investigação**, mas a regra conservadora atual não deve fazer merge automático apenas por nome+cidade quando há telefones conflitantes. Primeiro medir a recorrência; se o padrão se repetir, a Phase 8.4.5 deverá adicionar resolução pós-investigação com sinais fortes (domínio/social canônico/provider id/evidência cruzada), mantendo a regra “false merge is worse than duplicate”.

## 23.1 Objetivo

Provar que:

```text
10/10 != apenas quantidade
10/10 == quantidade + relevância + identidade + contato + oportunidade
```

## 23.2 Não alterar grandes features durante o benchmark

Durante 8.4.4:

**permitido**

- correção de bug que impede medir;
- instrumentação;
- logs de diagnóstico;
- export de métricas;
- fixture/teste que reproduz falha encontrada.

**evitar**

- novo provider;
- redesign grande;
- nova camada de IA;
- CRM;
- novo framework;
- refactor arquitetural amplo.

A razão é simples: precisamos medir o sistema atual, não um alvo que muda diariamente.

---

# 23.1 Fast Validation Loop — infraestrutura de desenvolvimento

O benchmark real de 10 leads continua sendo a fonte de verdade do gate, mas não deve mais ser usado para validar cada alteração determinística.

Fluxo obrigatório durante 8.4.4/8.4.5:

```text
1. testes unitários/regressão
2. replay local do último snapshot real
3. smoke de 3 leads somente quando provider/investigator/auditoria externa precisa ser revalidada
4. benchmark oficial de 10 somente quando o patch estiver pronto para gate
```

Artefatos de replay capturados por novos smoke/benchmarks:

```text
replay_snapshot.json
  stages.post_discovery
  stages.post_investigation
  stages.post_audits
  selections.investigation
  selections.website_audit
  selections.browser_audit
  selections.visual_audit
```

Comandos:

```text
run-phase844-smoke.bat
run-phase844-replay.bat
run-phase844-benchmark.bat
```

`--replay` nunca chama Tavily/Gemini e deve reportar `provider_calls=0` e `llm_calls=0`. `--smoke` reduz o target para 3 e grava em `benchmarks/smoke/`; smoke nunca conta como `1/5` oficial.

Limitação de compatibilidade: os dois runs diagnósticos já feitos foram gerados antes da captura de replay e contêm apenas os leads finais no `run.json`. Eles não preservam os 37 candidatos intermediários do segundo run, portanto não é tecnicamente correto fingir que conseguem revalidar a nova ordenação. Um novo smoke de 3 leads é o último passo externo necessário para criar a primeira fixture replayável.

---

# 24. Benchmark oficial da Phase 8.4.4

Casos mínimos:

```yaml
- segment: marcenaria
  city: Praia Grande
  state: SP
  target: 10

- segment: estetica automotiva
  city: Santos
  state: SP
  target: 10

- segment: vidracaria
  city: Sao Vicente
  state: SP
  target: 10

- segment: eletricista
  city: Campinas
  state: SP
  target: 10

- segment: moveis planejados
  city: Sao Luis
  state: MA
  target: 10
```

Adicionar depois pelo menos:

- um segmento com presença digital muito forte;
- um segmento com pouca presença digital;
- uma cidade grande;
- uma cidade média;
- uma busca em que muitas empresas tenham website;
- uma busca em que predominem redes sociais.

---

# 25. Como validar manualmente cada lead

Criar uma planilha ou fixture de avaliação com as colunas:

```text
benchmark_id
run_id
rank
lead_name
canonical_name_correct
segment_match
city_match
state_match
real_business
identity_correct
phone_present
phone_kind
phone_plausible
instagram_correct
website_status_predicted
website_status_manual
website_correctly_attributed
opportunity_type_predicted
opportunity_type_manual
is_duplicate
is_false_merge
contact_route_useful
evidence_sufficient
final_grade
notes
```

Valores manuais importantes:

```text
PASS
FAIL
UNCERTAIN
```

Não transformar dúvida humana em `PASS` automaticamente.

---

# 26. Métricas da Phase 8.4.4

## 26.1 Fulfillment@N

```text
final_eligible_leads / requested_leads
```

Meta desejada em buscas com oferta suficiente:

```text
10/10
```

Se o mercado não possuir quantidade suficiente sob os filtros, `partial_results` é correto.

## 26.2 Precision@N

Dos resultados entregues, quantos realmente pertencem ao segmento/local desejado?

Meta de referência:

```text
>= 90%
```

## 26.3 Identity precision

Dos leads apresentados como matched/probable, quantos são realmente a empresa correta?

Meta:

```text
>= 98% para MATCHED
>= 95% agregado MATCHED + PROBABLE_MATCH
```

## 26.4 Contact usefulness

Dos leads apresentados em modo digital-first, quantos possuem rota de contato realmente útil?

Medir separadamente:

```text
mobile
instagram
explicit whatsapp
email
none
```

## 26.5 Phone plausibility

Dos telefones considerados válidos:

```text
>= 98% sintaticamente plausíveis
```

Isso não significa que o número está ativo.

## 26.6 Website attribution false positive

Site de outra empresa associado ao lead é uma falha grave.

Meta:

```text
< 2%
```

Desejável:

```text
~0%
```

## 26.7 Website status quality

Separar:

```text
PRESENT precision
NOT_FOUND precision
UNKNOWN rate
UNREACHABLE precision
```

Não usar apenas “accuracy” agregada porque UNKNOWN pode mascarar comportamento conservador correto.

## 26.8 Duplicate rate

Após dedupe:

```text
< 5%
```

## 26.9 False merge rate

Mais grave do que duplicata.

Meta:

```text
~0%
```

## 26.10 Opportunity usefulness

Pergunta manual:

> Eu realmente consideraria abordar esta empresa para o serviço sugerido pelo LeadFlow?

Medir:

```text
useful_opportunity_rate
```

## 26.11 Run completion reliability

Meta futura:

```text
>= 95% dos runs sem exception não tratada
```

## 26.12 Cost / usage

Registrar por run:

```text
search_calls
llm_calls
website_audits
browser_audits
visual_audits
cache_hits
```

A Phase 8.4.4 não deve otimizar custo às cegas, mas precisa medir custo por lead bom.

---

# 27. Gate de conclusão da Phase 8.4.4

A fase só termina quando tivermos:

- [ ] 5 benchmarks principais executados;
- [ ] pelo menos 50 leads manualmente avaliados;
- [ ] fulfillment medido;
- [ ] precision medida;
- [ ] duplicate rate medida;
- [ ] false merge rate medida;
- [ ] website attribution verificada;
- [ ] contact usefulness verificada;
- [ ] failures agrupadas por causa;
- [ ] cada falha importante possui teste/regression case;
- [ ] sabemos se o problema dominante está em discovery, extraction, identity, dedupe, investigation, audit, filter ou score.

Somente depois disso começamos 8.4.5.

---

# 28. Phase 8.4.5 — Quality Correction Pass

Esta fase será definida pelos resultados reais da 8.4.4.

Possíveis classes de correção:

```text
A. Discovery coverage
B. Query quality
C. Extraction precision
D. Geographic mismatch
E. Contact sanitization
F. Identity resolution
G. Deduplication
H. Website attribution
I. NOT_FOUND confidence
J. Opportunity scoring
K. Filter semantics
L. Fulfillment stopping criteria
```

Regra:

> Nenhuma correção grande entra porque “parece melhor”. Toda mudança deve responder a uma falha observada no benchmark.

Gate:

- [ ] rerun dos mesmos benchmarks;
- [ ] métricas melhoraram ou permaneceram estáveis;
- [ ] nenhum regression conhecido;
- [ ] 199 testes da baseline atual continuam passando;
- [ ] novos testes adicionados para bugs reais encontrados.

---

# 29. Phase 8.5 — Frontend Product Completion

Após o core de qualidade estar estável, avançar a interface em direção à referência final.

## 29.1 Prioridade 1 — Evidence-rich inspector

Adicionar ao inspector:

- fontes reais, não apenas socials;
- por que identidade está matched/probable;
- origem do telefone;
- origem do website;
- confiança por campo quando disponível;
- quantas fontes sustentam cada decisão;
- warnings claros.

## 29.2 Prioridade 2 — Run progress mais granular

UI desejada:

```text
Planning
Searching
Extracting
Investigating
Auditing
Ranking
```

Mostrar também:

```text
unique candidates
prequalified
requested
search calls
```

Sem spinner opaco.

## 29.3 Prioridade 3 — Histórico e biblioteca de leads

Adicionar backend + frontend para:

- runs anteriores;
- reabrir resultado;
- filtros persistidos;
- biblioteca consolidada de empresas;
- refresh de lead;
- export pelo painel;
- delete/archive seguro.

## 29.4 Prioridade 4 — Settings

Painel mínimo:

```text
Providers
Gemini
Search budgets
Cache
Database
Privacy
Diagnostics
About
```

Não exibir secret depois de salvo.

## 29.5 Prioridade 5 — Paridade visual com referência

Ajustar:

- navegação final;
- proporções;
- topbar;
- densidade;
- badge/status;
- inspector;
- tabelas;
- detalhes de interação;
- responsividade.

---

# 30. Phase 8.6 — Operational Hardening

Após a UI principal:

- frontend component tests;
- API integration tests;
- E2E React + FastAPI + fake providers;
- crash/restart behavior;
- history recovery;
- clean error states;
- secret storage decision;
- clean release build;
- dependency audit;
- release artifact check;
- logging diagnostic export.

---

# 31. Phase 8.7 — Public Beta

Critérios mínimos:

- [ ] quality benchmarks aceitáveis;
- [ ] nenhum bug conhecido de false merge grave;
- [ ] website attribution aceitável;
- [ ] frontend principal completo;
- [ ] onboarding sem editar código;
- [ ] provider configuration utilizável;
- [ ] resultado parcial explicado;
- [ ] cancelamento funcional;
- [ ] secrets não aparecem em logs/UI;
- [ ] release sem `.env`, DB, outputs, node_modules ou `.git`;
- [ ] README atualizado;
- [ ] CHANGELOG limpo;
- [ ] licença e disclaimers presentes;
- [ ] testes backend + frontend + E2E verdes.

Distribuição inicial recomendada:

```text
source-first
+ Windows onedir beta depois
```

Não gastar energia com instalador sofisticado antes de usuários reais utilizarem a beta.

---

# 32. Phase 8.8 — Release Candidate / v1.0

O v1.0 não será definido pela quantidade de features, e sim pela confiança do workflow principal.

Workflow que precisa estar sólido:

```text
configure
   ↓
search
   ↓
receive requested quantity or explicit partial result
   ↓
inspect evidence
   ↓
understand opportunity
   ↓
prepare contact
   ↓
user reviews and acts
```

---

# 33. Definition of Done atualizada para v1.0

## Discovery

- [x] busca por segmento/cidade/estado;
- [x] planner adaptativo;
- [x] fallback;
- [x] multi-source;
- [x] quota fulfillment;
- [x] partial results explícito;
- [ ] benchmark real multi-segmento aprovado.

## Data quality

- [x] quality gate;
- [x] telefone estruturado;
- [x] digital-first;
- [x] identity states;
- [x] conservative merge;
- [x] rejected candidate memory;
- [x] dedupe melhorado;
- [ ] métricas reais de precision/duplicate/false merge aprovadas.

## Website intelligence

- [x] website states;
- [x] bounded investigation;
- [x] HTTP audit;
- [x] browser audit;
- [x] visual audit;
- [ ] website attribution benchmark aprovado.

## Opportunity

- [x] score comercial separado;
- [x] opportunity types;
- [x] reasons/cautions;
- [x] actionability;
- [ ] usefulness benchmark aprovado.

## Runtime

- [x] budgets;
- [x] cancellation;
- [x] retry;
- [x] circuit breaker;
- [x] cache;
- [x] memory;
- [x] partial budget/result;
- [ ] crash recovery/restart UX final.

## API

- [x] local FastAPI;
- [x] health;
- [x] catalogs;
- [x] async run;
- [x] result;
- [x] cancel;
- [x] contact prepare;
- [ ] history endpoints;
- [ ] leads library endpoints;
- [ ] settings/provider-secret endpoints.

## Frontend

- [x] search;
- [x] filters;
- [x] run state;
- [x] results table;
- [x] inspector;
- [x] contact prep;
- [x] partial warning;
- [x] basic responsive behavior;
- [ ] evidence inspector completo;
- [ ] history;
- [ ] leads library;
- [ ] settings;
- [ ] final visual parity;
- [ ] frontend automated tests;
- [ ] E2E.

## Security

- [x] input normalization;
- [x] secret redaction;
- [x] API local restrictions;
- [x] untrusted-web prompt rule;
- [x] SSRF-oriented website protection;
- [x] browser private-network blocking;
- [ ] user-friendly secret store;
- [ ] release artifact secret scan.

## Distribution

- [ ] clean release pipeline;
- [ ] source beta;
- [ ] Windows beta package;
- [ ] public v1.0 release.

---

# 34. Prioridades atuais — ordem estrita

A partir desta revisão, seguir esta ordem:

```text
1. Phase 8.4.4 — real-world quality benchmark
2. Phase 8.4.5 — corrections driven by benchmark
3. consolidate 8.4.3/8.4.5 in Git + docs
4. Phase 8.5 — frontend product completion
5. Phase 8.6 — operational/security/release hardening
6. Phase 8.7 — public beta
7. feedback real
8. Phase 8.8 — RC / v1.0
```

Não inverter a ordem adicionando features grandes antes da qualidade.

---

# 35. O que NÃO priorizar agora

Não começar agora:

- Exa integration;
- novos LLMs;
- Tauri;
- Electron;
- cloud;
- PostgreSQL;
- campanhas automáticas;
- WhatsApp API;
- cold email automation;
- payment/billing;
- analytics complexos;
- dashboards decorativos;
- mobile app nativo;
- plugin marketplace;
- agentes autônomos de outreach.

Esses recursos podem existir no futuro, mas não resolvem o risco atual.

---

# 36. Plano imediato de commits

## Commit A — Consolidate Phase 8.4.3

Depois de confirmar novamente testes:

```text
feat: fulfill requested quota using prequalified candidates
```

Incluir:

- agent qualified stop condition;
- investigation expansion;
- discovery counters;
- contract counters;
- tests 8.4.3;
- documentação/changelog.

## Commit B — Benchmark Harness — IMPLEMENTADO NA WORKING BASELINE

```text
test: add real-world lead quality benchmark harness
```

Criado:

```text
benchmarks/cases.yaml
benchmarks/README.md
benchmarks/results/.gitkeep
```

Também criado:

```text
scripts/run_benchmark.py
leadflow_agent/benchmark.py
tests/test_benchmark.py
```

O harness não marca automaticamente verdade de mundo real. Ele exporta dados para revisão manual, calcula métricas somente depois da revisão e invalida execuções contaminadas por falha relevante de infraestrutura externa.

## Commit C+ — Regression fixes

Um commit por classe de falha real encontrada.

Exemplos:

```text
fix: reject cross-city social identity collisions
fix: preserve distinct mobile businesses during dedupe
fix: avoid false official-domain attribution
fix: improve qualified pool estimation for website-sales
```

---

# 37. Test strategy atualizada

## 37.1 Backend regression

Atual:

```text
181 tests passing
```

Manter todos.

## 37.2 Fase nova: benchmark manual

Unit tests não conseguem responder:

- empresa existe de verdade?
- pertence à cidade?
- website é realmente dela?
- vale a pena abordar?

Por isso 8.4.4 é obrigatória.

## 37.3 Frontend tests

Ainda precisam entrar:

```text
Vitest
React Testing Library
```

Fluxos prioritários:

- search payload;
- running state;
- partial result warning;
- empty result;
- lead selection;
- contact prepare;
- API error;
- cancel.

## 37.4 E2E

Playwright de aplicação:

```text
start fake/local API
open frontend
submit run
wait
view results
select lead
prepare contact
```

Providers externos não devem ser necessários no CI.

---

# 38. Observabilidade necessária para 8.4.4

Já existem vários counters. O benchmark deve registrar pelo menos:

```text
run_id
provider
segment
city
requested
returned
quota_fulfilled
queries_executed
unique_candidates
prequalified_candidates
quality_rejected
invalid_fields_removed
duplicates_removed
investigated_leads
investigation_searches
filter_candidates_seen
filter_rejected
search_calls
llm_calls
website_audits
browser_audits
visual_audits
errors
external_failure_errors
website_audit_errors
quality_gate_measurement_valid
validity_reasons
stop_reason
```

Esses dados permitem descobrir **em qual etapa os 10 viraram 7** ou **em qual etapa candidatos ruins entraram**.

---

# 39. Estados de execução e UI

Estados de backend atuais:

```text
running
completed
partial_budget
partial_results
cancelled
```

A API adiciona estados transitórios próprios:

```text
queued
cancelling
failed
```

Frontend deve continuar diferenciando claramente:

```text
COMPLETED       → objetivo cumprido
PARTIAL_RESULTS → qualidade preservada, quantidade insuficiente
PARTIAL_BUDGET  → limite de segurança atingido
CANCELLED       → usuário interrompeu
FAILED          → erro impede resultado normal
```

Nunca pintar `partial_results` como sucesso total.

---

# 40. UX state matrix atual

| Área | Estado | Resposta esperada |
|---|---|---|
| API | offline | estado persistente + instrução para iniciar API |
| Search | idle | formulário + empty/prior workspace |
| Search | queued/running | banner + cancel |
| Search | cancelling | mensagem de finalização segura |
| Search | failed | erro acionável |
| Search | partial_results | resultados mantidos + shortfall explícito |
| Search | partial_budget | resultados mantidos + motivo de limite |
| Results | empty | nenhuma oportunidade elegível |
| Results | populated | tabela ordenável |
| Lead | selected | inspector sem perder contexto |
| Contact | preparing | loading/disabled |
| Contact | ready | mensagem editável + ação explícita |

---

# 41. Limites de produto e contato

A versão atual mantém uma fronteira importante:

```text
LeadFlow pesquisa e prepara.
Usuário revisa e envia.
```

Não transformar `Prepare Contact` em envio silencioso.

Mesmo no futuro, qualquer automação de outreach deve possuir controles próprios de autorização, consentimento, opt-out e limites de uso adequados ao canal e ao contexto jurídico aplicável.

As referências jurídicas e termos de providers presentes no documento antigo foram pesquisadas em 10/09/2026 e **devem ser re-verificadas antes de qualquer beta pública ou automação de marketing**. Este documento não atualiza essas políticas externas sem nova pesquisa.

---

# 42. Direção de distribuição

## Alpha atual

```text
source + local development workflow
```

## Beta

Preferir:

```text
source release limpa
+ instruções simples
```

Depois:

```text
Windows onedir package
```

Evitar inicialmente:

- Electron;
- auto-updater;
- installer complexo;
- signing caro;
- cloud obrigatório.

---

# 43. Critério para adicionar um novo provider

Só adicionar se o benchmark demonstrar uma necessidade objetiva.

Checklist:

- [ ] current coverage insuficiente;
- [ ] falha não é causada por query/extractor/filter;
- [ ] provider novo possui melhor cobertura no caso problemático;
- [ ] custo aceitável;
- [ ] termos compatíveis;
- [ ] adapter isolado;
- [ ] contract test;
- [ ] benchmark A/B;
- [ ] fallback claro.

---

# 44. Futuro pós-v1

Depois de uma v1 confiável, evolução possível:

## v1.1

- browser audit refinado;
- screenshot no inspector;
- saved searches;
- provider diversification baseada em benchmark;
- export pelo painel.

## v1.2

- multi-location;
- sugestões de segmentos;
- scheduling local de pesquisa;
- richer evidence viewer.

## v1.5

- import CSV;
- notas;
- lifecycle básico;
- follow-up manual;
- lead pipeline leve.

## v2

- cloud opcional;
- sync;
- times/equipes;
- advanced CRM;
- provider/plugin ecosystem;
- controlled automations.

Nada disso deve atrasar a v1 local.

---

# 45. Checklist para a próxima sessão

Ao abrir o projeto em outro chat ou sessão:

```text
1. Este documento é o estado de referência.
2. Usar o ZIP/repositório atual como fonte de código.
3. Confirmar Phase 8.4.3 + Fast Capture + Investigator Fast Path.
4. Rodar 199 testes.
5. Não usar benchmark completo como ferramenta de debug.
6. Usar replay local para mudanças determinísticas; fast capture só quando uma fixture nova for necessária.
7. Validar o Investigator Fast Path com um smoke externo de 3 leads apenas quando o core local estiver estável.
8. Conferir `investigation_searches`, `investigation_extractions`, LLM calls, fulfillment e falhas externas.
9. Se integração/latência estiver estável, rodar marcenaria + Praia Grande/SP + 10 como candidato oficial a Benchmark 1/5.
10. Se houver shortfall, corrigir apenas o estágio responsável e cobrir com regressão antes de novo run externo.
```

---

# 46. Próximo benchmark oficial da 8.4.4

Pré-condição:

```text
quality_gate_measurement_valid deve permanecer true
provider/rede externa deve estar operacional
website audit não pode estar sistematicamente bloqueado pelo ambiente
```

Entrada:

```text
segment: marcenaria
city: Praia Grande
state: SP
limit: 10
profile: website-sales
provider: auto (com a configuração real disponível)
contact_strategy: digital-first
fulfill_quota: true
investigate: true
website audit: true
browser audit: false
visual audit: false
```

Registrar:

```text
returned
queries_executed
unique_candidates
prequalified_candidates
search_calls
investigation_searches
filter_rejected
stop_reason
```

Depois revisar manualmente cada lead.

Somente após isso repetir:

```text
estética automotiva / Santos
vidraçaria / São Vicente
eletricista / Campinas
móveis planejados / São Luís
```

---

# 47. Decisões que substituem o plano antigo

## Decisão 1 — Frontend stack

**Antigo:** React + Tailwind + shadcn como recomendação.  
**Atual:** React + TypeScript + Vite + TanStack + Zustand + CSS próprio.

Não migrar sem razão funcional.

## Decisão 2 — Banco

**Antigo:** SQLAlchemy + Alembic recomendados.  
**Atual:** `sqlite3` + migrations idempotentes + `PRAGMA user_version`.

Manter até a complexidade justificar mudança.

## Decisão 3 — Gemini SDK

**Antigo:** migrar para `google-genai` + structured outputs.  
**Atual:** REST `generateContent` + JSON MIME + parser/validator próprio.

Reavaliar apenas se parsing/schema drift se tornar problema material.

## Decisão 4 — Provider expansion

**Antigo:** benchmark Exa cedo.  
**Atual:** congelar provider expansion até concluir 8.4.4.

## Decisão 5 — Cronograma por semanas

**Antigo:** semanas 1–8 estimadas.  
**Atual:** fases por risco e gates de qualidade.

O projeto avançou de forma diferente da simulação inicial; o roadmap agora acompanha a realidade.

## Decisão 6 — Frontend

**Antigo:** frontend era etapa futura.  
**Atual:** vertical slice React já existe e está integrado à API.

## Decisão 7 — Problema central

**Antigo:** “conseguir descobrir leads”.  
**Atual:** “entregar a quantidade pedida com qualidade mensurável”.

---

# 48. Estado final desta revisão

```text
LeadFlow 0.2.0-alpha line

CORE
✓ discovery
✓ extraction
✓ identity
✓ dedupe
✓ investigation
✓ cache
✓ memory
✓ website audit
✓ browser audit
✓ visual audit
✓ opportunity intelligence
✓ filters/profiles
✓ budgets
✓ circuit breaker
✓ cancellation
✓ quota fulfillment
✓ qualified fulfillment

APPLICATION
✓ FastAPI local
✓ versioned frontend contract
✓ async runs
✓ result polling
✓ cancel
✓ contact preparation

FRONTEND
✓ React workspace
✓ search
✓ advanced filters
✓ status
✓ results table
✓ lead inspector
✓ prepared contact
✓ partial-result feedback
~ visual parity: advanced but not complete
~ library/history/settings: pending

QUALITY
✓ 199 automated tests passing
✗ benchmark oficial 1/5 ainda não validado

CURRENT GATE
→ Phase 8.4.4 Real-World Quality Validation
```

---

# 48.1 Atualização — Smoke real e Fast Capture

O primeiro smoke pós-priority-fix mostrou que o gargalo de desenvolvimento não é mais discovery:

```text
2 queries
15 candidatos únicos
12 pré-qualificados
5 investigados
10 investigation searches
9 LLM calls
~6 minutos
1/3 leads finais
5 falhas externas
```

A medição é inválida para o gate oficial por falhas externas, mas é válida como diagnóstico de processo. O ranking de investigação colocou candidatos contactáveis primeiro, confirmando o priority fix. O problema passou a ser o custo/latência do pós-processamento e a dependência de Gemini durante investigação.

Foi criado **Fast Capture Mode** para o ciclo de desenvolvimento:

```text
--capture-only
<= 2 search calls
0 Gemini
0 Investigator
0 website/browser/visual audits
replay_snapshot.json
```

Hierarquia oficial de validação durante 8.4.4:

```text
unit/regression tests
  ↓
fast capture (somente quando precisamos de fixture nova)
  ↓
replay local
  ↓
3-lead smoke (integração)
  ↓
10-lead benchmark oficial
```

O Fast Capture resolve o tempo de iteração de engenharia. A latência do pipeline completo continua sendo um problema de produto a ser otimizado separadamente, sem afrouxar identidade/qualidade.

---

# 48.2 Atualização — Investigator Fast Path

O smoke replayável confirmou que o gargalo de tempo migrou de discovery para o pós-processamento. O snapshot real mais recente possui:

```text
2 discovery queries
15 candidatos únicos
12 pré-qualificados
5 candidatos selecionados para investigação
10 buscas de investigação observadas no smoke antigo
~6 minutos de duração total
5 falhas externas
```

A correção seguinte foi feita **sem novo run externo**, usando o `post_discovery` real como fixture. O objetivo é reduzir latência/custo sem relaxar identidade ou transformar ausência de evidência em certeza.

Mudanças implementadas:

1. **Uma rota de contato útil já é suficiente para pular contact-search redundante.**
   Telefone plausível, e-mail ou social público impedem uma query extra apenas para obter um segundo canal.

2. **Batch de extração por lead.**
   Até duas buscas independentes continuam existindo quando necessárias para segurança, mas o Gemini recebe as evidências das duas em uma única geração. O fallback legado permanece para extractors que não suportam batch.

3. **Quota-first investigation.**
   Após cada candidato investigado, o lead é sanitizado, rescored e reavaliado contra o filtro final. Quando a quantidade solicitada já foi atingida, o loop não esgota o `investigation_limit` apenas porque ainda existe capacidade configurada.

4. **Re-score antes de audit.**
   Mudanças de identidade/website produzidas pelo Investigator entram no Opportunity Intelligence antes da seleção do próximo estágio caro.

5. **Audit identity gate em runs filtrados.**
   Website só entra no audit de fulfillment quando a associação business/site está `MATCHED` ou `PROBABLE_MATCH`. Isso evita gastar auditoria em domínios ainda não atribuídos com segurança.

6. **Fail-fast para rede/DNS.**
   `HTTPError` sem status, quando representa DNS/timeout/connection failure, agora conta como falha transitória para o circuit breaker. Isso corrige um caso em que falhas de rede podiam continuar repetindo chamadas lentas sem abrir o circuito.

7. **Telemetria específica.**
   `investigation_extractions` agora é separado de `investigation_searches`, permitindo medir se a otimização realmente reduz Gemini sem confundir com Tavily/search calls.

Replay do snapshot real mais recente sob a nova política:

```text
5 candidatos selecionados
9 investigation searches (máximo estimado)
5 batched investigation extractions (máximo estimado)
9 legacy per-query extractions (mesmas queries)
4 gerações evitadas pelo batching no pior caso do snapshot
```

Isso representa **~44% menos chamadas de extração de investigação no cenário máximo desse snapshot**, antes de considerar o early-stop por quota. Se os três primeiros candidatos converterem em leads finais, o caminho estimado cai para aproximadamente:

```text
6 buscas de investigação
3 extrações Gemini
```

Esses números são **estimativas determinísticas de chamadas**, não promessa de tempo de parede. O próximo smoke completo deve existir apenas como validação de integração/latência real, não como ferramenta de debug cotidiano.

Estado de regressão após o patch:

```text
199/199 testes passando
replay local: 0 provider calls / 0 LLM calls
```

---

# 49. Regra de ouro daqui para frente

> **Não confundir mais features com mais produto.**

O LeadFlow já tem inteligência suficiente para ser impressionante tecnicamente.

O que transforma o projeto em produto agora é:

```text
reliability
precision
explainability
repeatability
clear UX
safe limits
```

A próxima vitória não é adicionar outra API.

A próxima vitória é poder pedir:

```text
10 marcenarias em Praia Grande
```

receber:

```text
10 oportunidades realmente úteis
```

entender por que cada uma está ali, confiar nos contatos e saber quando o sistema não conseguiu concluir a quota sem que ele esconda isso.

---

# 50. Handoff resumido para continuação em outro chat

Se este projeto precisar ser retomado sem o histórico da conversa, considerar como verdade inicial:

1. O LeadFlow é um agente local-first de descoberta e qualificação de oportunidades comerciais.
2. O pacote atual declara `0.2.0a1`.
3. O frontend React funcional já existe.
4. A referência visual final é o dashboard enviado junto desta revisão.
5. A API local FastAPI já integra o frontend ao core.
6. O core já possui discovery, Gemini extraction, investigation, dedupe, identity, cache, memory, audits e opportunity scoring.
7. O contato é assistido e manual; não existe envio automático.
8. A Phase 8.4.1 fez a quantidade pedida virar target real.
9. A Phase 8.4.2 adicionou discovery adaptativo/multi-source.
10. A Phase 8.4.3 corrigiu o encerramento prematuro baseado em pool bruto e passou a usar candidatos pré-qualificados.
11. Os testes atuais passam: `199/199`.
12. O próximo trabalho NÃO é uma nova feature.
13. A **Phase 8.4.4 está ativa**. O primeiro smoke com replay snapshot já foi executado: 15 candidatos únicos / 12 pré-qualificados em 2 queries, mas apenas 1/3 final por falhas externas no Investigator/Gemini. O priority fix foi validado no replay determinístico. O loop usa `--capture-only` + replay local; o Investigator Fast Path agora faz batch de extração por lead, evita contact-search redundante, para cedo ao cumprir quota, evita audit de identidade não verificada em fulfillment e trata DNS/network sem status como falha transitória para circuit breaker.
14. Primeiro benchmark: `marcenaria + Praia Grande/SP + 10`.
15. Depois: Santos, São Vicente, Campinas e São Luís nos casos definidos neste documento.
16. Correções da Phase 8.4.5 devem ser baseadas nos erros encontrados nesses benchmarks.
17. Só depois completar library/history/settings e paridade final do frontend.

---

**Fim do documento atualizado — 14/09/2026 — Investigator Fast Path.**

---

# 51. Atualização — Lead Lifecycle + Contact Queue (14/09/2026)

A prioridade operacional mudou: para uso diário, o LeadFlow precisa evitar a repetição dos mesmos leads entre buscas e transformar a abordagem manual em uma fila organizada.

Implementado no snapshot atual:

- lifecycle persistente por lead: `new`, `queued`, `contacted`, `accepted`, `ignored`, `hidden`;
- SQLite schema v3 com notas e timestamp de último contato;
- fila persistente de contato manual, sem envio automático;
- endpoint de fila e endpoints de lifecycle na API local;
- novas visões no frontend: Descobrir, Fila, Aceitos, Contactados, Ignorados e Escondidos;
- novas buscas excluem, por padrão, leads já existentes na biblioteca local;
- adicionar à fila não marca como contactado;
- `contacted` só ocorre mediante ação explícita do usuário;
- a fila é removida da fila ativa quando o usuário marca o lead como contactado;
- contrato de lead passa a carregar `lead_key` para ações operacionais estáveis.

Princípio operacional:

```text
Descobrir → Selecionar → Adicionar à fila → Abrir contato manual → Marcar contactado
                                      ↘ ignorar / esconder / aceitar
```

Isso não transforma o LeadFlow em disparador automático. O usuário continua revisando e realizando cada envio.

Regra de descoberta:

```text
nova busca
    ↓
consultar memória persistente de leads já vistos
    ↓
excluir leads já presentes
    ↓
retornar somente empresas novas
```

Para restaurar/reutilizar um lead antigo, usar as visões persistentes da aplicação em vez de depender de uma nova busca que o redescubra.
