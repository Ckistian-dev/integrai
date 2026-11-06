# Design Técnico: Inutilização de NF-e e Módulo Dedicado de Notas Fiscais

**Data:** 2026-11-04  
**Autor:** Antigravity & Equipe ERP IntegraAI / Talatto  
**Status:** Proposta para Aprovação (Awaiting Approval)  
**Tópico:** Desacoplamento do Menu de Notas Fiscais da Sidebar e Implementação da Inutilização de Numeração na SEFAZ  

---

## 1. Contexto e Motivação (Intent & The Why)

No fluxo fiscal de uma empresa emissora de Nota Fiscal Eletrônica (NF-e modelo 55) e Nota Fiscal de Consumidor Eletrônica (NFC-e modelo 65), a legislação tributária brasileira (Ajuste SINIEF 07/05) determina que quebras involuntárias na sequência numérica (saltos de numeração causados por falhas de sistema, problemas de conexão, rejeições irreversíveis ou erros operacionais) devem ser obrigatoriamente comunicadas e homologadas junto à SEFAZ até o 10º dia do mês subsequente, através do procedimento de **Inutilização de Numeração**.

Atualmente, o ERP apresenta duas limitações centrais:
1. **Navegação e Escopo Misturados:** A visualização das notas fiscais emitidas fica aninhada como uma subpágina/situação dentro do menu de **Pedidos** (`/pedidos/Nota Fiscal`). Isso gera atrito operacional, pois a gestão de documentos fiscais atende a rotinas contábeis e fiscais independentes do funil de vendas.
2. **Ausência do Recurso de Inutilização:** O sistema não possui interface nem endpoint para envio do evento síncrono de inutilização para a SEFAZ. Se houver um salto de numeração, o usuário não tem como regularizar a faixa sem recorrer a ferramentas externas.

Este projeto visa:
- Mover a gestão de Notas Fiscais para um **item de primeiro nível na sidebar**, com rota dedicada `/notas_fiscais`.
- Remover a sub-etapa "Nota Fiscal" de dentro do funil de Pedidos.
- Disponibilizar um **modal padrão do sistema para Inutilização de Notas Fiscais**, que permita ao usuário inutilizar uma numeração ou faixa contínua sem depender de um pedido cadastrado no ERP, enviando a requisição à SEFAZ via `pynfe`, validando os requisitos tributários e persistindo o histórico com número de protocolo.

---

## 2. Objetivos, Não-Objetivos e Anti-Objetivos

### 2.1. Objetivos (Goals)
- **G-1: Item Dedicado na Sidebar:** Criar um item de menu principal chamado `"Notas Fiscais"` na barra lateral (`MainLayout.jsx`), removendo a subpágina `"Nota Fiscal"` da listagem do pipeline de `Pedidos`.
- **G-2: Rota Própria:** Configurar a rota `/notas_fiscais` (e suas permissões no controle de acesso de usuários), exibindo a listagem consolidada de documentos fiscais emitidos.
- **G-3: Modal de Inutilização Desacoplado:** Fornecer um modal na tela de Notas Fiscais para entrada dos parâmetros:
  - Modelo (55 - NF-e ou 65 - NFC-e, padrão 55).
  - Série (default carregado da configuração da empresa ativa).
  - Número Inicial.
  - Número Final (para nota avulsa, repete o número inicial; para faixas, número final >= número inicial).
  - Ano (2 dígitos ou padrão do ano corrente).
  - Justificativa (validação visual e de backend exigindo no mínimo 15 caracteres).
- **G-4: Comunicação Síncrona com a SEFAZ via PyNFe:** Implementar no backend o método de inutilização utilizando as credenciais (certificado digital A1 e senha) e ambiente (homologação/produção) da empresa ativa, invocando `ComunicacaoSefaz.inutilizacao(...)`.
- **G-5: Histórico de Inutilizações e Auditoria:** Criar tabela no banco de dados (`nfe_inutilizacoes`) para registrar cada homologação (ou rejeição), guardando: protocolo SEFAZ, data/hora de recebimento, faixa inutilizada, justificativa, cStat, xMotivo e XML de retorno.

### 2.2. Não-Objetivos (Non-Goals)
- Não será alterada a geração ou regras de emissão de NF-e para pedidos existentes que continuam seu fluxo regular (Orçamento -> Faturamento -> Emissão).
- Não haverá cancelamento automático de pedidos ao inutilizar um número (já que a inutilização é justamente para números onde **não houve** fato gerador de venda concluída no ERP).
- Não será modificado o layout dos DANFEs já existentes.

### 2.3. Anti-Objetivos (Anti-Goals)
- **Vínculo Obrigatório com Pedidos:** A inutilização não deve exigir nem forçar a existência de um `pedido_id` no banco de dados.
- **Quebra de Permissões RBAC:** Usuários sem permissão de acesso ao módulo fiscal não devem conseguir visualizar a rota nem disparar a inutilização.
- **Inutilização Sem Justificativa Válida:** O sistema nunca deve enviar à SEFAZ justificativas com menos de 15 caracteres (o que geraria a rejeição 256 da SEFAZ).

---

## 3. Decisões Acordadas com o Usuário e Resoluções Técnicas (Builder Check)

| Decisão | Definição Acordada | Detalhes |
|---|---|---|
| **Localização no Menu** | Item de primeiro nível na sidebar ("Notas Fiscais") | Movido para fora do menu expansível de Pedidos |
| **Pipeline de Pedidos** | Remoção de "Nota Fiscal" das etapas do pipeline | O funil de pedidos mantém Orçamento, Aprovação, Programação, Produção, Embalagem, Faturamento, Expedição, Despachado, Cancelado, Todos |
| **Acesso ao Modal** | Botão de ação na tela de Notas Fiscais | Botão estilizado no topo/barra de ferramentas da listagem |
| **Independência de Pedidos** | Sequência informada livremente no modal | Usuário digita série, número inicial e número final diretamente |
| **Preservação das Ações Fiscais** | DANFE, Cancelamento, Carta de Correção, Devolução e Complemento | Permanecem 100% disponíveis na nova visualização de Notas Fiscais, sem regressão de recursos |
| **Reaproveitamento de Componentes** | `GenericList` adaptado para `/notas_fiscais` | Reutiliza a robustez de paginação, filtros, colunas e modais já consolidados no sistema |
| **Navegação Pós-Faturamento** | Redirecionamento após faturar/conferir | Após faturar ou concluir embalagem, redireciona para `/pedidos/Expedição` (ou permanece na fila de faturamento), refletindo o fluxo real do funil de pedidos |
| **Migração Automática de Permissões** | Script de migração via Alembic | Todos os perfis com acesso a `pedidos` herdam automaticamente permissão para `notas_fiscais` |
| **Identidade Visual** | Padrão existente do ERP | Tailwind CSS, componentes de feedback (`ToastContainer`), modals existentes e tema escuro/claro |

---

## 4. O que foi deixado para o Desenvolvedor (Left to the Builder)

1. **Definição da Tabela de Persistência:** Nomeada `nfe_inutilizacoes`, com campos necessários para comprovação fiscal perante a Receita Estadual.
2. **Tratamento de Códigos de Retorno da SEFAZ:**
   - `cStat == 102`: Inutilização de número homologado (Sucesso).
   - `cStat == 206` ou `256`: Rejeições conhecidas da SEFAZ tratadas com mensagens amigáveis ao usuário.
3. **Consulta de Histórico:** Na tela de Notas Fiscais, fornecer uma aba ou visualização rápida para o usuário consultar as inutilizações já realizadas anteriormente pela empresa.
4. **Log Estruturado:** Instrumentação completa no backend utilizando `app.core.logger` e códigos de erro `ERR_NFE_INUTILIZACAO_*`.

---

## 5. Arquitetura Técnica Detalhada

### 5.1. Backend (FastAPI + SQLAlchemy + PyNFe)

#### 5.1.1. Modelo de Banco de Dados (`backend/app/core/db/models.py`)
Criar o modelo `NfeInutilizacao`:
```python
class NfeInutilizacao(Base):
    __tablename__ = "nfe_inutilizacoes"
    __label__ = "Inutilização de NF-e"
    __label_plural__ = "Inutilizações de NF-e"

    id = Column(Integer, primary_key=True, index=True)
    id_empresa = Column(Integer, ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False, index=True)
    modelo = Column(String(2), default="55", nullable=False) # 55: NF-e, 65: NFC-e
    serie = Column(Integer, nullable=False, default=1)
    numero_inicial = Column(Integer, nullable=False)
    numero_final = Column(Integer, nullable=False)
    ano = Column(Integer, nullable=False)
    justificativa = Column(String(255), nullable=False)
    
    # Retorno SEFAZ
    cstat = Column(String(10), nullable=True) # Ex: 102
    xmotivo = Column(String(255), nullable=True) # Ex: Inutilizacao de numero homologado
    protocolo = Column(String(50), nullable=True, index=True)
    data_recebimento = Column(DateTime, nullable=True)
    xml_retorno = Column(Text, nullable=True)
    sucesso = Column(Boolean, default=False, index=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    id_usuario = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)

    empresa = relationship("Empresa", backref="inutilizacoes")
    usuario = relationship("Usuario")
```

#### 5.1.2. Serviço Fiscal (`backend/app/core/service/nfe_service.py`)
Adicionar o método `inutilizar_numeracao`:
- Obtém os dados da empresa ativa (`cnpj`, `estado`, `certificado_arquivo`, `certificado_senha`, `ambiente_sefaz`).
- Validações prévias:
  - `len(justificativa.strip()) >= 15`.
  - `numero_final >= numero_inicial > 0`.
  - `serie >= 0`.
- Instancia `ComunicacaoSefaz` com certificado decodificado em arquivo temporário (conforme padrão já testado no serviço).
- Chama `comunicacao.inutilizacao(modelo="nfe", cnpj=empresa.cnpj, numero_inicial=num_ini, numero_final=num_fim, justificativa=justificativa, ano=ano, serie=str(serie))`.
- Faz o parse seguro do XML de resposta (`etree.fromstring` via `safe_xml_fromstring`):
  - Extrai `cStat`, `xMotivo`, `nProt`, `dhRecbto`.
  - Registra a entidade `NfeInutilizacao` no banco.
  - Se `cStat == 102`, retorna `status: "sucesso"` com protocolo e mensagem.
  - Caso contrário, levanta `HTTPException` ou retorna resposta com status de rejeição detalhado.

#### 5.1.3. Endpoints da API (`backend/app/api/v1/endpoints/nfe.py`)
```python
class InutilizarNFeRequest(BaseModel):
    modelo: Optional[str] = "55" # 55 ou 65
    serie: int
    numero_inicial: int
    numero_final: int
    ano: Optional[int] = None # Se omitido, assume o ano atual
    justificativa: str # Mínimo 15 caracteres

@router.post("/nfe/inutilizar")
def inutilizar_nfe(
    payload: InutilizarNFeRequest,
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    service = NFeService(db, current_user.id_empresa)
    return service.inutilizar_numeracao(
        modelo=payload.modelo,
        serie=payload.serie,
        numero_inicial=payload.numero_inicial,
        numero_final=payload.numero_final,
        justificativa=payload.justificativa,
        ano=payload.ano,
        id_usuario=current_user.id
    )

@router.get("/nfe/inutilizacoes")
def listar_inutilizacoes(
    db: Session = Depends(get_db),
    current_user: models.Usuario = Depends(get_current_active_user)
):
    service = NFeService(db, current_user.id_empresa)
    return service.listar_inutilizacoes()
```

---

### 5.2. Frontend (React + Tailwind CSS + Lucide Icons)

#### 5.2.1. Ajuste da Sidebar (`frontend/src/components/layout/MainLayout.jsx`)
1. **Adicionar Item Principal:**
   ```javascript
   { name: 'Notas Fiscais', path: '/notas_fiscais', icon: FileText, module: 'notas_fiscais' }
   ```
2. **Remover do Pipeline de Pedidos:**
   Remover o item `{ name: 'Nota Fiscal', path: '/pedidos/Nota Fiscal' }` do array `pipelineStatus`.

#### 5.2.2. Ajuste de Rotas e Redirecionamentos (`frontend/src/App.jsx` e `frontend/src/pages/GenericList.jsx`)
1. Incluir `'notas_fiscais'` na lista de verificação de permissão e módulos acessíveis em `App.jsx`.
2. Registrar a rota dedicada `/notas_fiscais` renderizando `GenericList` com contexto e filtros de notas fiscais emitidas (`modelName="pedidos"`, exibindo pedidos com notas fiscais geradas e ações fiscais ativas).
3. Atualizar os redirecionamentos pós-faturamento e pós-conferência em `GenericList.jsx`:
   - Ao faturar pedido ou concluir embalagem, redirecionar para `/pedidos/Expedição` (ou manter na fila), eliminando a referência quebrada a `/pedidos/Nota Fiscal`.

#### 5.2.3. Modal de Inutilização e Histórico
1. **Ação na Interface:**
   - Botão destacado no topo da visualização de Notas Fiscais: **"Inutilizar Numeração"** (ícone `FileX` ou `AlertTriangle`).
   - Botão auxiliar para visualizar o histórico de faixas inutilizadas da empresa (`/nfe/inutilizacoes`).
2. **Componente `ModalInutilizarNFe.jsx`:**
   - Campos:
     - Modelo: Seleção entre NF-e (55) e NFC-e (65).
     - Série: Campo numérico (carrega default `nfe_serie` da empresa logada).
     - Faixa: Número Inicial e Número Final (com opção ou preenchimento automático para nota única).
     - Justificativa: Campo de texto multilinhas com feedback em tempo real de caracteres (mínimo de 15 caracteres obrigatório pela SEFAZ).
   - Ação de envio com `LoadingSpinner` e desabilitação durante a requisição síncrona com a SEFAZ.
   - Tratamento de sucesso com exibição do número de protocolo retornado e atualização automática da listagem.
3. **Preservação de Todas as Ações Fiscais Existentes:**
   - Visualização e download de DANFE (`/nfe/danfe/:id`).
   - Download de XML assinado/autorizado.
   - Cancelamento de NF-e (`/nfe/cancelar/:id`).
   - Carta de Correção Eletrônica - CC-e (`/nfe/corrigir/:id`).
   - Devolução e Complemento de NF-e.

---

## 6. Validação e Testes Automatizados

1. **Testes Unitários de Backend:**
   - Validação de entrada: rejeitar justificativas com menos de 15 caracteres antes da chamada à SEFAZ.
   - Validação de faixa: rejeitar `numero_final < numero_inicial`.
   - Mock da chamada `ComunicacaoSefaz.inutilizacao`: testar retorno com `cStat 102` (sucesso), conferindo a persistência do protocolo na tabela `nfe_inutilizacoes`.
   - Testar retorno com `cStat 256` / `563` (rejeição), garantindo que o erro seja devolvido de forma clara sem quebrar o servidor.
2. **Testes de Integração e Interface:**
   - Conferir se o item "Nota Fiscal" não aparece mais sob o menu de Pedidos.
   - Conferir se o item "Notas Fiscais" aparece na sidebar e direciona para `/notas_fiscais`.
   - Abrir o modal, validar contagem de caracteres e disparar requisição.

