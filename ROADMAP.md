# Sage — Roadmap de Features

> Foco: widget de conhecimento pessoal que **facilita a vida do usuario**.
> Tudo que for adicionado deve respeitar a premissa de ser rapido, discreto e util.

---

## v0.6 — Produtividade

- [ ] **Clipboard watcher** — detectar texto copiado e sugerir salvar como nota automaticamente
- [ ] **Quick snippets** — salvar e colar trechos de codigo/texto com atalho (ex: `;;email` expande para o email do usuario)
- [ ] **Markdown export** — exportar todo o conhecimento salvo como `.md` organizados por tema
- [ ] **Busca fuzzy** — ao digitar no popup, sugerir resultados em tempo real com fuzzy match local antes de chamar a LLM

## v0.7 — Integracao com o Desktop

- [ ] **Drag & drop de arquivos** — arrastar PDF/imagem/txt para o popup e indexar automaticamente no RAG
- [ ] **Screenshot to knowledge** — capturar tela (hotkey), OCR do conteudo e salvar como nota
- [ ] **Notificacoes inteligentes** — lembrar o usuario de notas relevantes baseado no contexto (app ativo, horario, clipboard)
- [ ] **Startup silencioso** — autostart com o sistema (Linux autostart, Windows registry, macOS LaunchAgent)

## v0.8 — Organizacao

- [ ] **Tags e categorias** — permitir o usuario organizar notas por tags (#trabalho, #pessoal, #codigo)
- [ ] **Favoritos / Pins** — marcar notas importantes para acesso rapido no tray menu
- [ ] **Historico de conversas** — visualizar historico de perguntas e respostas anteriores no popup
- [ ] **Busca por data** — filtrar notas por periodo (hoje, semana, mes)

## v0.9 — Multi-device

- [ ] **Sync via API** — sincronizar notas entre dispositivos usando a sage-api (usuario logado)
- [ ] **Backup & restore** — exportar/importar base de conhecimento completa (encrypted)
- [ ] **Conflict resolution** — merge inteligente quando houver edicoes em dispositivos diferentes

## v1.0 — Inteligencia

- [ ] **Resumo diario** — ao final do dia, gerar um resumo do que foi salvo/consultado
- [ ] **Conexoes automaticas** — sugerir relacoes entre notas (ex: "essa nota parece relacionada com X")
- [ ] **Perguntas proativas** — "voce salvou isso ha 7 dias, ainda e relevante?"
- [ ] **Contexto por aplicativo** — detectar qual app esta ativo e priorizar notas relacionadas nas buscas

## v1.1 — Monetizacao e Growth

- [ ] **Plano free com limite** — ex: 50 notas ou 10 queries/dia no free, ilimitado no pro
- [ ] **Onboarding tour** — guia interativo no primeiro uso
- [ ] **Referral system** — "convide um amigo, ganhe 1 mes pro"
- [ ] **Usage analytics (local)** — dashboard simples mostrando quantas notas, queries, uso por dia

## Backlog (avaliar prioridade)

- [ ] **Plugin system** — permitir extensoes da comunidade (ex: integracao com Notion, Obsidian)
- [ ] **Voice input** — gravar audio curto e transcrever como nota (Whisper local ou API)
- [ ] **Web clipper** — extensao de browser para salvar trechos de paginas direto no Sage
- [ ] **API local** — expor endpoints localhost para automacoes (ex: salvar nota via curl/script)
- [ ] **Temas** — dark/light mode e customizacao visual do popup
- [ ] **Multi-idioma** — i18n para o app (pt-BR, en, es)

---

## Principios

1. **Rapido** — o popup deve abrir em <200ms, sempre
2. **Discreto** — nunca interromper o usuario sem necessidade
3. **Offline-first** — funcionar sem internet (LLM local via Ollama/LM Studio)
4. **Seguro** — dados encriptados, nada sai do dispositivo sem consentimento
5. **Simples** — cada feature nova deve resolver 1 problema claro
