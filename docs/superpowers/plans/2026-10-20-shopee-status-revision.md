# Revisão da Lógica de Alteração de Status Shopee e Webhooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Revisar e aperfeiçoar a sincronização de status de pedidos com a Shopee OpenAPI v2 (canais 90021/90026 vs integrada), transformar o campo "Status Shopee" em dropdown no ERP, bloquear salvamento manual com toast de erro em caso de recusa da Shopee, manter o status anterior em erros de gatilhos automáticos, registrar histórico completo de eventos e criar o endpoint de webhooks da Shopee.

**Architecture:** 
- O modelo `Pedido` terá o campo `shopee_order_status` configurado com `component: 'select'` e opções oficiais nos metadados.
- O endpoint `PUT /generic/pedidos/{id}` em `generic.py` diferenciará alteração manual de alteração por gatilhos automáticos de regras: no manual, a chamada à Shopee é síncrona pré-commit e se falhar aborta com HTTP 400 exibindo Toast no frontend; no automático, se a Shopee falhar, reverte a alteração de status e grava a falha no histórico.
- O `ShopeeService` orquestrará as chamadas oficiais `v2.logistics.ship_order` e `v2.logistics.update_tracking_status` e processará webhooks de push da Shopee (código 3 para status e 4 para rastreio), persistindo todas as interações em `shopee_historico`.
- Um novo endpoint `POST /shopee/webhook` em `shopee.py` receberá os eventos enviados pela Shopee e invocará o serviço para sincronizar o pedido.
- No frontend, `ShopeeStatusRulesInput.jsx` e `InputFields.jsx` serão atualizados para refletir todos os status e formatar o download de `shopee_historico`.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, Requests, React, TailwindCSS.

**Spec:** [docs/superpowers/specs/2026-10-20-shopee-status-revision-design.md](file:///c:/Users/Administrator/Desktop/Trabalho/ERP%20Talatto/docs/superpowers/specs/2026-10-20-shopee-status-revision-design.md)

## Global Constraints
- Canais de Logística Integrada Shopee (Shopee Xpress, Correios) não aceitam baixa de entrega manual via API; o sistema deve identificar essa resposta da Shopee e informar claramente o motivo.
- Canais 90021 e 90026 exigem envio de `logistics_pickup_done` e `logistics_delivery_done` via `v2.logistics.update_tracking_status`.
- Salvamento manual com erro deve retornar HTTP 400 com mensagem detalhada para disparar o toast do frontend e cancelar a persistência do pedido.
- Salvamento automático com erro não deve impedir a persistência dos demais campos do pedido, mas não deve alterar o status do pedido na Shopee e deve salvar o erro em `shopee_historico`.

## Review Focus
- Tentativa de marcar pedido de canal integrado como `COMPLETED` ou `TO_CONFIRM_RECEIVE`: deve resultar em erro 400 claro no salvamento manual explicando que canais integrados não permitem confirmação manual de entrega via API.
- Pedido sem `shopee_order_sn`: deve validar antes da chamada e não gerar requisições desnecessárias para a Shopee.
- Webhook recebido para pedido inexistente no banco: deve responder HTTP 200 para a Shopee com log de aviso para não travar a fila de webhooks da Shopee.
- Download de `shopee_historico` no frontend: deve formatar corretamente cada evento e webhook recebido.
- Reversão de status em erro de gatilho automático: `item.shopee_order_status` deve voltar ao valor anterior ao salvar o pedido no ERP.

---

### Task 1: Configuração do Campo `shopee_order_status` como Dropdown nos Metadados do Pedido

**Files:**
- Modify: `backend/app/core/db/models.py:1198-1206`
- Test: `backend/tests/test_shopee_metadata.py`

**Interfaces:**
- Produces: `shopee_order_status` com `info={'component': 'select', 'options': [...]}` reconhecido pelo gerador de metadados de `Pedido`.

- [ ] **Step 1: Escrever teste para validar metadados de `shopee_order_status`**
Criar teste que consulta `/metadata/pedidos` ou inspeciona `models.Pedido.__table__.columns['shopee_order_status'].info` garantindo que `component == 'select'` e contém as opções de status oficiais da Shopee (`READY_TO_SHIP`, `PROCESSED`, `SHIPPED`, `TO_CONFIRM_RECEIVE`, `COMPLETED`, `CANCELLED`, `IN_CANCEL`, `UNPAID`, `TO_RETURN`).

- [ ] **Step 2: Rodar teste e verificar que falha**
Run: `pytest backend/tests/test_shopee_metadata.py -v`

- [ ] **Step 3: Modificar `models.py` para adicionar opções e `component: 'select'` em `shopee_order_status`**
Atualizar `backend/app/core/db/models.py` na linha 1200 para incluir o dicionário de opções completas e `component: 'select'`.

- [ ] **Step 4: Rodar teste e verificar que passa**
Run: `pytest backend/tests/test_shopee_metadata.py -v`

- [ ] **Step 5: Commit**
`git add backend/app/core/db/models.py backend/tests/test_shopee_metadata.py && git commit -m "feat(shopee): configure shopee_order_status as select dropdown in Pedido model metadata"`

---

### Task 2: Refatoração da Lógica de Transição de Status e Histórico no `ShopeeService`

**Files:**
- Modify: `backend/app/core/service/shopee_service.py:1488-1800`
- Test: `backend/tests/test_shopee_service_status.py`

**Interfaces:**
- Consumes: Configuração Shopee, Pedido com `shopee_order_sn`.
- Produces: `update_shopee_order_status(pedido, target_status, is_manual=False) -> Dict[str, Any]` retornando dict com `success: bool`, `status: str`, `message: str`, `data: dict`.

- [ ] **Step 1: Escrever testes unitários para `update_shopee_order_status`**
Criar testes cobrindo:
1. Atualização para `SHIPPED` (chama `ship_order` e `update_tracking_status` com `logistics_pickup_done`).
2. Atualização para `COMPLETED` / `TO_CONFIRM_RECEIVE` (chama `update_tracking_status` com `logistics_delivery_done`).
3. Retorno de erro da Shopee (ex: `channel not support` ou erro 400 da Shopee), garantindo que retorna `success: False` com a mensagem descritiva e grava em `shopee_historico`.

- [ ] **Step 2: Rodar teste e verificar comportamento atual**
Run: `pytest backend/tests/test_shopee_service_status.py -v`

- [ ] **Step 3: Implementar tratamento aprimorado no `ShopeeService`**
Atualizar `update_tracking_status` e `update_shopee_order_status` em `backend/app/core/service/shopee_service.py`:
- Garantir que `is_manual` receba a sinalização adequada.
- Retornar objeto estruturado com `success: bool`, `error_type: str`, `message: str`.
- Registrar cada tentativa em `shopee_historico` com payload enviado e resposta detalhada.

- [ ] **Step 4: Rodar teste e verificar que passa**
Run: `pytest backend/tests/test_shopee_service_status.py -v`

- [ ] **Step 5: Commit**
`git add backend/app/core/service/shopee_service.py backend/tests/test_shopee_service_status.py && git commit -m "feat(shopee): refine status transitions and error responses in ShopeeService"`

---

### Task 3: Criação do Processador e Endpoint de Webhooks da Shopee

**Files:**
- Modify: `backend/app/core/service/shopee_service.py`
- Modify: `backend/app/api/v1/endpoints/shopee.py`
- Test: `backend/tests/test_shopee_webhook.py`

**Interfaces:**
- Consumes: POST JSON payload da Shopee OpenAPI v2 contendo `shop_id`, `code`, `data` (`ordersn`, `status`, `tracking_no`).
- Produces: `POST /api/v1/shopee/webhook` respondendo `{"message": "success"}` e atualizando o pedido no banco.

- [ ] **Step 1: Escrever teste para o endpoint de webhook**
Testar:
1. Envio de webhook com `code == 3` (Order Status Change) para um pedido com `shopee_order_sn`: valida atualização de `shopee_order_status`, datas e adição de entrada no `shopee_historico`.
2. Envio de webhook com `code == 4` (Tracking Status Change): valida atualização de `shopee_tracking_number` e registro no histórico.
3. Webhook de pedido não localizado: retorna HTTP 200 com mensagem apropriada.

- [ ] **Step 2: Rodar teste e verificar falha (404 Not Found pois endpoint não existe)**
Run: `pytest backend/tests/test_shopee_webhook.py -v`

- [ ] **Step 3: Implementar método `process_shopee_webhook` em `ShopeeService` e rota `POST /shopee/webhook` em `shopee.py`**
- Em `shopee_service.py`: adicionar `process_shopee_webhook(payload: dict) -> dict` que extrai `ordersn`, busca o pedido correspondente, atualiza status e adiciona entrada formatada no `shopee_historico`.
- Em `shopee.py`: adicionar rota `@router.post("/shopee/webhook")` recebendo `payload = Body(...)`.

- [ ] **Step 4: Rodar teste e verificar que passa**
Run: `pytest backend/tests/test_shopee_webhook.py -v`

- [ ] **Step 5: Commit**
`git add backend/app/core/service/shopee_service.py backend/app/api/v1/endpoints/shopee.py backend/tests/test_shopee_webhook.py && git commit -m "feat(shopee): add Shopee webhook processing endpoint and history tracking"`

---

### Task 4: Atualização de Lógica Manual e Gatilhos em `generic.py` (`PUT /generic/pedidos/{id}`)

**Files:**
- Modify: `backend/app/api/v1/endpoints/generic.py:3042-3056,3304-3325`
- Test: `backend/tests/test_generic_shopee_triggers.py`

**Interfaces:**
- Consumes: `PUT /generic/pedidos/{id}` com `shopee_order_status` ou com colunas de gatilho modificadas.
- Produces:
  - Se alteração manual de `shopee_order_status` falhar: aborta com `HTTPException(400, detail="Erro Shopee: ...")`.
  - Se gatilho automático falhar: não altera `shopee_order_status` e registra falha no histórico.

- [ ] **Step 1: Escrever testes para alteração manual e automática via `PUT /generic/pedidos/{id}`**
Criar testes simulando:
1. Pedido Shopee editado manualmente alterando `shopee_order_status`: quando a API da Shopee simula falha, a requisição PUT deve retornar 400 Bad Request com o detalhe do erro e o pedido não deve ter seu status alterado no banco.
2. Pedido Shopee editado com alteração de coluna que dispara regra de gatilho: quando a Shopee aceita, o status é sincronizado; quando falha, o status permanece inalterado e o histórico recebe o registro do erro.

- [ ] **Step 2: Rodar teste e verificar falha**
Run: `pytest backend/tests/test_generic_shopee_triggers.py -v`

- [ ] **Step 3: Modificar `generic.py` para implementar as validações pré e pós salvamento**
- Antes do commit: verificar se `shopee_order_status` foi modificado manualmente. Se foi, chamar `shopee_svc.update_shopee_order_status(pedido=db_obj, target_status=new_status, is_manual=True)`. Se `not res.get('success')`: disparar `raise HTTPException(status_code=400, detail=f"Erro Shopee: {res.get('message')}")`.
- Após o commit: para regras automáticas (`regras_atualizacao_status`), invocar o serviço. Se falhar, restaurar `item.shopee_order_status` e persistir a entrada no histórico.

- [ ] **Step 4: Rodar teste e verificar que passa**
Run: `pytest backend/tests/test_generic_shopee_triggers.py -v`

- [ ] **Step 5: Commit**
`git add backend/app/api/v1/endpoints/generic.py backend/tests/test_generic_shopee_triggers.py && git commit -m "feat(shopee): enforce manual status update blocking on error and rule trigger syncing in generic PUT"`

---

### Task 5: Atualização dos Componentes Frontend (`ShopeeStatusRulesInput.jsx` e `InputFields.jsx`)

**Files:**
- Modify: `frontend/src/components/ui/ShopeeStatusRulesInput.jsx:7-14`
- Modify: `frontend/src/components/ui/InputFields.jsx:1475-1570`

**Interfaces:**
- Produces:
  - `STATUS_SHOPEE_OPTIONS` com todas as opções oficiais da Shopee OpenAPI v2.
  - `FileInput` em `InputFields.jsx` reconhecendo `shopee_historico` para download de `historico_shopee_pedido_{id}.txt`.

- [ ] **Step 1: Atualizar `STATUS_SHOPEE_OPTIONS` em `ShopeeStatusRulesInput.jsx`**
Garantir que a lista de status contenha todas as opções da Shopee OpenAPI v2:
- `READY_TO_SHIP`
- `PROCESSED`
- `SHIPPED`
- `TO_CONFIRM_RECEIVE`
- `COMPLETED`
- `CANCELLED`
- `IN_CANCEL`
- `UNPAID`
- `TO_RETURN`

- [ ] **Step 2: Atualizar `InputFields.jsx` para formatar `shopee_historico`**
Adicionar suporte específico para `isShopeeField = Boolean(name && name.toLowerCase().includes('shopee'))`, gerando o arquivo `historico_shopee_pedido_{id}.txt` com contagem de eventos e formatação limpa.

- [ ] **Step 3: Verificar build / sintaxe do frontend**
Run: `npm run build` ou `npx vite build` no diretório `frontend` para certificar que não há erros de tipagem ou sintaxe.

- [ ] **Step 4: Commit**
`git add frontend/src/components/ui/ShopeeStatusRulesInput.jsx frontend/src/components/ui/InputFields.jsx && git commit -m "feat(frontend): update Shopee status options in rules builder and format Shopee history download"`

---

### Task 6: Verificação de Ponta a Ponta e Validação Integrada

**Files:**
- Test: Todos os testes criados nas tasks anteriores e testes integrados de regressão.

- [ ] **Step 1: Executar suite de testes do backend para Shopee e Pedidos**
Run: `pytest backend/tests/test_shopee*.py backend/tests/test_generic_shopee*.py -v`
Expected: Todos os testes PASSANDO.

- [ ] **Step 2: Testar regressão geral de rotas de pedidos**
Verificar que a alteração não afeta pedidos comuns, Mercado Livre ou Magento.

- [ ] **Step 3: Finalizar e registrar documentação**
Validar que os status e endpoints estão em conformidade com as regras da documentação oficial Shopee OpenAPI v2 fornecida.
