# Autonomous Factory MVP

Este MVP pega um comando de alto nivel (ex.: `build a SGA`) e gera, de forma deterministica:

- especificacao estruturada (`requirements.json`)
- decisao arquitetural inicial (ADR)
- backlog por fases
- scaffold inicial de backend, banco e frontend

## Como executar

No diretorio raiz do repositorio:

```bash
python3 autonomous_factory/factory.py \
  --goal "build a SGA" \
  --project-name sga-pilot \
  --constraint users=15000 \
  --constraint cloud=aws \
  --constraint compliance=LGPD \
  --output generated
```

### Modo interativo

Se quiser preencher lacunas de requisitos com perguntas guiadas:

```bash
python3 autonomous_factory/factory.py \
  --goal "build a SGA" \
  --interactive \
  --output generated
```

Esse modo pergunta, quando necessario:

- nome do projeto
- quantidade estimada de usuarios
- cloud alvo
- perfil de budget
- compliance
- canal principal de entrega

### Dry-run de execucao

Para gerar um relatorio de execucao por fase sem executar mudanças reais:

```bash
python3 autonomous_factory/factory.py \
  --goal "build a SGA" \
  --project-name dry-run-sga \
  --dry-run-execution \
  --output generated
```

### Estado persistente

Para avancar o estado entre execucoes:

```bash
python3 autonomous_factory/factory.py \
  --goal "build a SGA" \
  --project-name stateful-sga \
  --dry-run-execution \
  --advance-phase \
  --output generated
```

Isso gera `execution/state.json` e `execution/state.md`.

### Execucao de fase (idempotente)

Para executar tarefas da fase ativa e registrar evidencias:

```bash
python3 autonomous_factory/factory.py \
  --goal "build a SGA" \
  --project-name stateful-sga \
  --execute-phase \
  --output generated
```

Arquivos relevantes:

- `execution/evidence/`
- `execution/audit-trail.json`

Exemplos de artefatos gerados pelos handlers:

- `execution/validation/domain-check.json`
- `planning/constraint-resolution.md`
- `spec/requirements.lock.json`
- `planning/api-contract.md`
- `.github/workflows/ci-generated.yml`
- `scaffold/backend/app/modules/*.py`

Para apenas simular, use `--execute-phase --dry-run-actions`.

### Rollback da ultima tarefa

Para reverter a ultima tarefa concluida (via audit trail):

```bash
python3 autonomous_factory/factory.py \
  --goal "build a SGA" \
  --project-name stateful-sga \
  --rollback-last-task \
  --output generated
```

O rollback remove arquivos criados pela tarefa e marca a tarefa novamente como `pending`.
Quando a tarefa atualiza arquivo existente, o conteudo anterior e restaurado por snapshot.

## Saida esperada

Ao final, voce tera uma estrutura como:

```text
generated/sga-pilot/
  README.md
  spec/requirements.json
  architecture/adr-0001-initial-architecture.md
  planning/backlog.json
  planning/execution-plan.md
  governance/release-gates.md
  scaffold/
    backend/app/main.py
    database/schema.sql
    frontend/index.html
```

## Observacao

Este projeto e o ponto de partida pratico para evoluir para um sistema agentico completo (com execucao de testes, loop de correcao e deploy automatizado).

## Testes

```bash
python3 -m pip install ruff
python3 -m ruff check autonomous_factory
python3 -m compileall autonomous_factory

python3 -m unittest discover -s autonomous_factory/tests -p "test_*.py"
```
