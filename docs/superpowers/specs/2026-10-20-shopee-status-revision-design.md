# Design Document: Revisão da Lógica de Alteração de Status Shopee e Webhooks (OpenAPI v2)

## 1. Contexto e Intenção (Intent & The Why)
A integração com a Shopee (OpenAPI v2) possui regras específicas de atualização de status de pedidos no Brasil, distinguindo canais com **Logística Integrada** (onde a Shopee gerencia o envio e não permite baixa manual de entrega via API) e canais com **Logística Própria / Cotação do Vendedor** (canais 90021 e 90026, onde o ERP tem a obrigação de atualizar via API os status de despacho e entrega através dos endpoints `v2.logistics.ship_order` e `v2.logistics.update_tracking_status`).

O objetivo desta revisão é:
1. Permitir que o usuário visualize e altere manualmente o "Status Shopee" no formulário do pedido através de um dropdown completo com os status oficiais da Shopee.
2. No salvamento manual: se o status for alterado e a Shopee recusar a atualização (ex: validação de transição, canal integrado que proíbe entrega via API ou credencial inválida), o salvamento deve ser impedido com erro 400 e um toast deve informar a mensagem exata de erro retornada pela Shopee.
3. No disparo automático (via regras de gatilho nas configurações da Shopee, quando uma coluna do pedido muda de valor): se a requisição der erro na Shopee, o status do pedido não deve ser alterado e o erro deve ser registrado no histórico.
4. Criar um endpoint para ouvir Webhooks da Shopee (push notifications da Shopee OpenAPI v2), atualizando os pedidos no ERP automaticamente e gravando cada ocorrência no histórico de eventos (`shopee_historico`).
5. Garantir que todas as requisições (manuais, automáticas e webhooks) fiquem registradas no campo `shopee_historico` do pedido, com suporte a visualização e download formatado.

---

## 2. Metas, Não-Metas e Anti-Metas

### Metas (Goals)
- Transformar `shopee_order_status` em um campo do tipo `select` (dropdown) nos metadados do modelo `Pedido` com os status oficiais da Shopee OpenAPI v2.
- No endpoint `PUT /api/v1/generic/pedidos/{id}`:
  - Detectar alteração manual de `shopee_order_status`. Executar a chamada para a Shopee *antes* de persistir a alteração. Se a Shopee recusar, registrar o erro no histórico, realizar rollback e disparar `HTTPException(status_code=400, detail="Erro Shopee: ...")`, exibindo o toast de erro no frontend e impedindo o salvamento.
  - Detectar alterações automáticas disparadas por `regras_atualizacao_status` (ShopeeConfiguracao). Se a Shopee aceitar, atualiza o status. Se recusar, não atualiza o status e grava o erro em `shopee_historico`.
- Refinar a máquina de estados no `ShopeeService` para os canais 90021 / 90026 e logística integrada:
  - `READY_TO_SHIP` -> `v2.logistics.ship_order`
  - `SHIPPED` -> `v2.logistics.update_tracking_status` com `logistics_pickup_done`
  - `TO_CONFIRM_RECEIVE` / `COMPLETED` -> `v2.logistics.update_tracking_status` com `logistics_delivery_done`
- Criar endpoint `POST /api/v1/shopee/webhook` para receber notificações oficiais da Shopee:
  - Processa notificações de atualização de status (Code 3) e rastreamento (Code 4).
  - Localiza o pedido correspondente por `shopee_order_sn`.
  - Atualiza status local, datas (`data_despacho`, `data_entrega`, `data_finalizacao`) e rastreio.
  - Registra o evento de webhook no `shopee_historico`.
  - Retorna HTTP 200 conforme exigido pela Shopee.
- Atualizar `ShopeeStatusRulesInput.jsx` para compartilhar as opções completas de status.
- Atualizar `InputFields.jsx` (`FileInput`) para suportar o download e formatação dos eventos de `shopee_historico`.

### Não-Metas (Non-Goals)
- Não tentar forçar a baixa de entrega em pedidos de Logística Integrada Oficial da Shopee (SPX, Correios Integrados), já que a própria Shopee veta essa ação via API, mas sim fornecer retorno claro e informativo caso o usuário tente forçar manualmente.

### Anti-Metas (Anti-Goals)
- Não silenciar erros da Shopee durante o salvamento manual (o sistema anterior capturava a exceção silenciosamente em um log e salvava o pedido no banco com status que a Shopee recusou).
- Não quebrar integrações existentes de Mercado Livre, Intelipost ou Magento no endpoint genérico de pedidos.

---

## 3. Arquitetura e Decisões de Implementação

### 3.1. Modelo `Pedido` e Metadados (`backend/app/core/db/models.py`)
- O campo `shopee_order_status` terá seu dicionário `info` atualizado para conter:
  ```python
  info={
      'tab': 'Integrações',
      'sub_tab': 'Shopee',
      'label': 'Status Shopee',
      'component': 'select',
      'options': [
          {'label': 'Pronto para Envio (READY_TO_SHIP)', 'value': 'READY_TO_SHIP'},
          {'label': 'Em Expedição / Despacho Solicitado (PROCESSED)', 'value': 'PROCESSED'},
          {'label': 'Despachado / Em Trânsito (SHIPPED)', 'value': 'SHIPPED'},
          {'label': 'A Confirmar Recebimento (TO_CONFIRM_RECEIVE)', 'value': 'TO_CONFIRM_RECEIVE'},
          {'label': 'Concluído / Entregue (COMPLETED)', 'value': 'COMPLETED'},
          {'label': 'Cancelado (CANCELLED)', 'value': 'CANCELLED'},
          {'label': 'Em Cancelamento (IN_CANCEL)', 'value': 'IN_CANCEL'},
          {'label': 'Não Pago (UNPAID)', 'value': 'UNPAID'},
          {'label': 'Em Devolução (TO_RETURN)', 'value': 'TO_RETURN'},
      ]
  }
  ```
- O frontend (`GenericForm` / `FormRenderer`) automaticamente interpretará o campo como um `SelectInput` com as opções acima.

### 3.2. Fluxo Manual vs. Fluxo Automático (`backend/app/api/v1/endpoints/generic.py`)
No endpoint `PUT /api/v1/generic/pedidos/{id}`:
1. **Captura do estado inicial**:
   - Salvar `old_shopee_order_status = db_obj.shopee_order_status`.
   - Capturar valores anteriores das colunas envolvidas em `regras_atualizacao_status`.
2. **Avaliação pré-salvamento**:
   - Identificar se houve alteração manual direta no payload: `new_shopee_order_status = item_data.get('shopee_order_status')` diferente de `old_shopee_order_status`.
   - Se for manual:
     - Invocar `shopee_svc.update_shopee_order_status(pedido=db_obj, target_status=new_shopee_order_status, is_manual=True)`.
     - Se o resultado retornar erro ou recusa da Shopee (`status in ['error', 'warning', 'failed']` com mensagem de erro da API):
       - Grava a tentativa no histórico com status de falha.
       - Dispara `HTTPException(status_code=400, detail=f"Erro ao alterar status na Shopee: {mensagem}")`.
       - Isso cancela o commit no banco do ERP e faz o frontend disparar o toast vermelho de erro, mantendo o formulário intacto para correção.
3. **Avaliação pós-salvamento / Gatilhos Automáticos**:
   - Se não foi alteração manual direta, mas uma das colunas com regras de gatilho (`regras_atualizacao_status`) ou situação do pedido foi modificada:
     - Avalia a regra correspondente.
     - Invoca `shopee_svc.update_shopee_order_status(pedido=item, target_status=status_alvo, is_manual=False)`.
     - Se a Shopee aceitar: atualiza `item.shopee_order_status` e grava no histórico.
     - Se a Shopee recusar: reverte `item.shopee_order_status` para o valor anterior, não propaga a alteração de status e grava o erro e payload no `shopee_historico`.

### 3.3. Refinamento do `ShopeeService` (`backend/app/core/service/shopee_service.py`)
- Método `update_shopee_order_status`:
  - Trata explicitamente os status:
    - `READY_TO_SHIP` / `PROCESSED`: dispara `arrange_shipment` (`v2.logistics.ship_order`).
    - `SHIPPED`: dispara `update_tracking_status` com `logistics_pickup_done` (e `arrange_shipment` se ainda não tiver sido chamado).
    - `COMPLETED` / `TO_CONFIRM_RECEIVE`: dispara `update_tracking_status` com `logistics_delivery_done`.
  - Tratamento de canais:
    - Se a Shopee retornar erro indicando canal integrado (ex: `channel not support`, `logistics channel`), identifica explicitamente a situação. Em alteração manual, reporta como erro amigável ao usuário. Em automático, registra no histórico.
  - Registro de histórico completo: cada envio registra data/hora, evento, status enviado, resposta da API Shopee, tracking number e mensagem.

### 3.4. Endpoint de Webhooks da Shopee (`backend/app/api/v1/endpoints/shopee.py`)
- Endpoint: `POST /api/v1/shopee/webhook`
- Validação:
  - Validação opcional da assinatura Shopee OpenAPI v2 via query param `sign` / header se configurado.
  - Recebimento do payload Push da Shopee (conforme doc OpenAPI v2 Push Mechanism).
  - Códigos de evento:
    - `code == 3` (Order status change): atualiza `shopee_order_status` no pedido e ajusta datas (`data_despacho`, `data_entrega`, `data_finalizacao`).
    - `code == 4` (Tracking status change): atualiza `shopee_tracking_number` e status logístico.
  - Registro no `shopee_historico`: grava a entrada com `evento: "Webhook Shopee Recebido"`, código, payload e data/hora.
  - Retorno HTTP 200: `{"message": "success"}`.

### 3.5. Frontend (`ShopeeStatusRulesInput.jsx` e `InputFields.jsx`)
- Atualizar `STATUS_SHOPEE_OPTIONS` para sincronizar os mesmos status da API v2.
- Ajustar `InputFields.jsx` para reconhecer `shopee_historico` no componente de histórico/download, formatando os logs de eventos de envio e webhooks para exportação em texto limpo.

---

## 4. O que Fica a Cargo do Construtor (Builder Calls)
- Nomes dos endpoints: `POST /api/v1/shopee/webhook` (e alias `@router.post("/shopee/webhook")`).
- Mensagens amigáveis de erro do Toast traduzidas para português claro.
- Sanitização e validação de existência do `shopee_order_sn` antes de efetuar chamadas externas.
