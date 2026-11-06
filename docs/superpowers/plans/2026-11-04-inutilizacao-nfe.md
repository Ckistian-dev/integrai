# Inutilização de NF-e e Módulo Dedicado de Notas Fiscais Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mover a gestão de Notas Fiscais de dentro do funil de Pedidos para um item principal na sidebar (`/notas_fiscais`), preservando todas as ações fiscais de pós-emissão existentes e implementando a rotina de Inutilização de Numeração junto à SEFAZ via PyNFe com persistência de histórico e modal dedicado.

**Architecture:** No backend, o modelo `NfeInutilizacao` persiste as homologações de quebra de numeração no PostgreSQL; `NFeService` orquestra a assinatura A1 e comunicação SOAP síncrona com os webservices da SEFAZ via `ComunicacaoSefaz.inutilizacao` da biblioteca `pynfe`, exposto via endpoints REST em `/api/v1/nfe/inutilizar` e `/api/v1/nfe/inutilizacoes`. No frontend, `MainLayout.jsx` promove "Notas Fiscais" a item de primeiro nível e remove a subpágina de `pedidos`; `GenericList.jsx` é adaptado para responder pela rota `/notas_fiscais` preservando DANFE, XML, cancelamento e CC-e, incorporando botões para acionar o novo `ModalInutilizarNFe.jsx` e o `ModalHistoricoInutilizacoes.jsx`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy, Alembic, PyNFe, lxml, React (Vite), Tailwind CSS, Lucide Icons, PyTest.

**Spec:** [docs/superpowers/specs/2026-11-04-inutilizacao-nfe-design.md](file:///c:/Users/Administrator/Desktop/Trabalho/ERP%20Talatto/docs/superpowers/specs/2026-11-04-inutilizacao-nfe-design.md)

## Global Constraints

- A justificativa de inutilização enviada à SEFAZ deve conter obrigatoriamente no mínimo 15 caracteres (validação no frontend e backend).
- `numero_final` deve ser sempre maior ou igual a `numero_inicial`, e ambos maiores que zero.
- A inutilização não deve exigir vínculo com pedidos no ERP (`pedido_id` não é foreign key de `nfe_inutilizacoes`).
- A remoção de `/pedidos/Nota Fiscal` não pode quebrar o faturamento nem a conferência de pedidos; os redirecionamentos devem apontar para `/pedidos/Expedição`.
- Todas as ações existentes de NF-e (DANFE, XML, Cancelar NFe, Carta de Correção, Devolução, Complemento) devem permanecer funcionais na nova rota `/notas_fiscais`.
- Perfis existentes com acesso ao módulo de pedidos devem ter a permissão de `notas_fiscais` concedida automaticamente na migração.
- A comunicação com a SEFAZ deve usar o certificado A1 da empresa ativa e respeitar o ambiente configurado (`homologacao` ou `producao`).

## Review Focus

- Rejeição da SEFAZ por justificativa curta ou numeração já utilizada: o retorno deve capturar o `cStat` (ex: 206, 256) e `xMotivo` da SEFAZ, persistir a tentativa e exibir alerta descritivo ao usuário sem lançar erro 500 no backend.
- Concorrência ou certificado vencido/ausente: retornar mensagem amigável instruindo verificação do certificado digital em vez de falhas crípticas de OpenSSL.
- Redirecionamento quebrado em faturamento/embalagem: conferir se nenhum ponto do frontend continua navegando para `/pedidos/Nota Fiscal`.
- Perda de acesso de operadores: conferir se perfis não-admin mantêm acesso à tela de notas fiscais após o deploy.
- Parsing seguro de XML de retorno: utilizar `safe_xml_fromstring` para extração do protocolo de homologação (`cStat == 102`).

---

### Task 1: Modelo de Dados `NfeInutilizacao` e Migração de Permissões RBAC

**Files:**
- Modify: `backend/app/core/db/models.py:1880-1889`
- Create: `backend/alembic/versions/20261104_add_nfe_inutilizacao_and_rbac.py`
- Create: `backend/tests/test_nfe_inutilizacao_model.py`

**Interfaces:**
- Produces: Modelo `NfeInutilizacao` com colunas `(id, id_empresa, modelo, serie, numero_inicial, numero_final, ano, justificativa, cstat, xmotivo, protocolo, data_recebimento, xml_retorno, sucesso, created_at, id_usuario)`.
- Produces: Migração de banco que cria a tabela `nfe_inutilizacoes` e atualiza `perfis.permissoes` para incluir `notas_fiscais: {"acesso": True}` em perfis com acesso a `pedidos`.

- [x] **Step 1: Escrever teste de unidade para o modelo `NfeInutilizacao`**

```python
# backend/tests/test_nfe_inutilizacao_model.py
import unittest
from datetime import datetime
from app.core.db.models import NfeInutilizacao, Empresa, Usuario

class TestNfeInutilizacaoModel(unittest.TestCase):
    def test_model_fields_and_tablename(self):
        self.assertEqual(NfeInutilizacao.__tablename__, "nfe_inutilizacoes")
        
        inut = NfeInutilizacao(
            id_empresa=1,
            modelo="55",
            serie=1,
            numero_inicial=100,
            numero_final=105,
            ano=2026,
            justificativa="Quebra de numeracao por falha de transmissao",
            cstat="102",
            xmotivo="Inutilizacao de numero homologado",
            protocolo="135260000000001",
            data_recebimento=datetime.utcnow(),
            sucesso=True
        )
        self.assertEqual(inut.id_empresa, 1)
        self.assertEqual(inut.modelo, "55")
        self.assertEqual(inut.serie, 1)
        self.assertEqual(inut.numero_inicial, 100)
        self.assertEqual(inut.numero_final, 105)
        self.assertEqual(inut.ano, 2026)
        self.assertTrue(inut.sucesso)
        self.assertEqual(inut.cstat, "102")
```

- [x] **Step 2: Executar teste para confirmar falha**

Run: `pytest backend/tests/test_nfe_inutilizacao_model.py`  
Expected: FAIL com `ImportError: cannot import name 'NfeInutilizacao' from 'app.core.db.models'`

- [x] **Step 3: Implementar `NfeInutilizacao` em `backend/app/core/db/models.py`**

Adicionar a classe `NfeInutilizacao` ao final de `models.py` com relacionamentos com `Empresa` e `Usuario`.

- [x] **Step 4: Criar script de migração Alembic**

Gerar migração criando a tabela `nfe_inutilizacoes` e adicionando cláusula de atualização de JSON em `perfis.permissoes` para espelhar a permissão `pedidos` em `notas_fiscais`.

- [x] **Step 5: Executar teste para confirmar sucesso**

Run: `pytest backend/tests/test_nfe_inutilizacao_model.py`  
Expected: PASS

- [x] **Step 6: Commit**

```bash
git add backend/app/core/db/models.py backend/alembic/versions/ backend/tests/test_nfe_inutilizacao_model.py
git commit -m "feat(nfe): adicionar modelo NfeInutilizacao e migracao de permissoes"
```

---

### Task 2: Serviço de Inutilização de NF-e no Backend (`NFeService`)

**Files:**
- Modify: `backend/app/core/service/nfe_service.py`
- Modify: `backend/app/core/error_codes.py`
- Create: `backend/tests/test_nfe_inutilizacao_service.py`

**Interfaces:**
- Produces: `NFeService.inutilizar_numeracao(modelo, serie, numero_inicial, numero_final, justificativa, ano, id_usuario) -> Dict[str, Any]`
- Produces: `NFeService.listar_inutilizacoes(limit=100, offset=0) -> List[Dict[str, Any]]`

- [x] **Step 1: Escrever testes unitários com mocks para `inutilizar_numeracao`**

```python
# backend/tests/test_nfe_inutilizacao_service.py
import unittest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from app.core.service.nfe_service import NFeService
from app.core.db.models import Empresa, EmpresaAmbienteSefazEnum

class TestNfeInutilizacaoService(unittest.TestCase):
    def setUp(self):
        self.mock_db = MagicMock()
        self.mock_empresa = MagicMock()
        self.mock_empresa.id = 1
        self.mock_empresa.cnpj = "12345678000195"
        self.mock_empresa.estado = "SP"
        self.mock_empresa.nfe_serie = 1
        self.mock_empresa.ambiente_sefaz = EmpresaAmbienteSefazEnum.homologacao
        self.mock_empresa.certificado_arquivo = b"fake-cert"
        self.mock_empresa.certificado_senha = "fake-password"
        self.mock_db.query(Empresa).filter().first.return_value = self.mock_empresa

    def test_valida_justificativa_curta(self):
        service = NFeService(self.mock_db, id_empresa=1)
        with self.assertRaises(HTTPException) as ctx:
            service.inutilizar_numeracao(modelo="55", serie=1, numero_inicial=1, numero_final=1, justificativa="Curta", id_usuario=1)
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("15 caracteres", ctx.exception.detail)

    def test_valida_faixa_invalida(self):
        service = NFeService(self.mock_db, id_empresa=1)
        with self.assertRaises(HTTPException) as ctx:
            service.inutilizar_numeracao(modelo="55", serie=1, numero_inicial=10, numero_final=5, justificativa="Justificativa com mais de 15 caracteres", id_usuario=1)
        self.assertEqual(ctx.exception.status_code, 400)

    @patch("app.core.service.nfe_service.ComunicacaoSefaz")
    @patch("tempfile.NamedTemporaryFile")
    def test_inutilizacao_sucesso_homologado_102(self, mock_tmp, mock_sefaz_cls):
        mock_sefaz = MagicMock()
        mock_sefaz_cls.return_value = mock_sefaz
        # XML de retorno com cStat 102
        xml_retorno = """<retInutNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
            <infInut>
                <cStat>102</cStat>
                <xMotivo>Inutilizacao de numero homologado</xMotivo>
                <nProt>135260000000001</nProt>
                <dhRecbto>2026-11-04T14:30:00-03:00</dhRecbto>
            </infInut>
        </retInutNFe>"""
        mock_sefaz.inutilizacao.return_value = xml_retorno.encode('utf-8')

        service = NFeService(self.mock_db, id_empresa=1)
        res = service.inutilizar_numeracao(
            modelo="55", serie=1, numero_inicial=100, numero_final=102,
            justificativa="Quebra de sequencia devido a falha de conexao", id_usuario=1
        )
        self.assertEqual(res["cstat"], "102")
        self.assertEqual(res["protocolo"], "135260000000001")
        self.assertTrue(res["sucesso"])
```

- [x] **Step 2: Executar teste para verificar falha**

Run: `pytest backend/tests/test_nfe_inutilizacao_service.py`  
Expected: FAIL com `AttributeError: 'NFeService' object has no attribute 'inutilizar_numeracao'`

- [x] **Step 3: Implementar `inutilizar_numeracao` e `listar_inutilizacoes` em `nfe_service.py`**

1. Adicionar validação de justificativa (`len(justificativa.strip()) >= 15`) e de faixa (`numero_final >= numero_inicial > 0`).
2. Configurar extração temporária do certificado `.pfx` com limpeza segura (`tempfile`).
3. Instanciar `ComunicacaoSefaz(uf=empresa.estado, certificado=cert_path, certificado_senha=empresa.certificado_senha, homologacao=(empresa.ambiente_sefaz == EmpresaAmbienteSefazEnum.homologacao))`.
4. Executar `comunicacao.inutilizacao(modelo="nfe" if modelo == "55" else "nfce", cnpj=empresa.cnpj, numero_inicial=numero_inicial, numero_final=numero_final, justificativa=justificativa, ano=ano, serie=str(serie))`.
5. Processar resposta XML com `safe_xml_fromstring`, extraindo `cStat`, `xMotivo`, `nProt`, `dhRecbto`.
6. Gravar `NfeInutilizacao` no banco e logar evento com `log_info`/`log_warning`.

- [x] **Step 4: Executar testes para verificar aprovação**

Run: `pytest backend/tests/test_nfe_inutilizacao_service.py`  
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/core/service/nfe_service.py backend/tests/test_nfe_inutilizacao_service.py
git commit -m "feat(nfe): implementar metodo de inutilizacao no NFeService"
```

---

### Task 3: Endpoints REST de Inutilização (`/api/v1/nfe/inutilizar` e `/api/v1/nfe/inutilizacoes`)

**Files:**
- Modify: `backend/app/api/v1/endpoints/nfe.py`
- Create: `backend/tests/test_nfe_inutilizacao_endpoints.py`

**Interfaces:**
- Produces: `POST /api/v1/nfe/inutilizar` (payload: `InutilizarNFeRequest`)
- Produces: `GET /api/v1/nfe/inutilizacoes` (retorna histórico ordenado por `created_at DESC`)

- [x] **Step 1: Escrever teste de integração para os endpoints**

```python
# backend/tests/test_nfe_inutilizacao_endpoints.py
import unittest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from app.main import app
from app.api.dependencies import get_current_active_user
from app.core.db.database import get_db

class TestNfeInutilizacaoEndpoints(unittest.TestCase):
    def setUp(self):
        self.mock_user = MagicMock()
        self.mock_user.id = 1
        self.mock_user.id_empresa = 1
        self.mock_user.perfil = "admin"
        app.dependency_overrides[get_current_active_user] = lambda: self.mock_user
        app.dependency_overrides[get_db] = lambda: MagicMock()
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()

    @patch("app.core.service.nfe_service.NFeService.inutilizar_numeracao")
    def test_post_inutilizar_endpoint(self, mock_inut):
        mock_inut.return_value = {
            "sucesso": True,
            "cstat": "102",
            "xmotivo": "Inutilizacao de numero homologado",
            "protocolo": "135260000000001"
        }
        payload = {
            "modelo": "55",
            "serie": 1,
            "numero_inicial": 200,
            "numero_final": 200,
            "justificativa": "Pulo de numeracao devido a erro operacional"
        }
        res = self.client.post("/api/v1/nfe/inutilizar", json=payload)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["cstat"], "102")
```

- [x] **Step 2: Executar teste para verificar falha**

Run: `pytest backend/tests/test_nfe_inutilizacao_endpoints.py`  
Expected: FAIL com status 404 Not Found

- [x] **Step 3: Implementar endpoints em `backend/app/api/v1/endpoints/nfe.py`**

Adicionar schema Pydantic `InutilizarNFeRequest` e as rotas `POST /nfe/inutilizar` e `GET /nfe/inutilizacoes` chamando os métodos correspondentes de `NFeService`.

- [x] **Step 4: Executar teste para verificar aprovação**

Run: `pytest backend/tests/test_nfe_inutilizacao_endpoints.py`  
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/nfe.py backend/tests/test_nfe_inutilizacao_endpoints.py
git commit -m "feat(nfe): adicionar endpoints de inutilizacao e historico"
```

---

### Task 4: Reorganização da Sidebar, Rotas e Redirecionamentos no Frontend

**Files:**
- Modify: `frontend/src/components/layout/MainLayout.jsx:40-60, 145-160, 210-225`
- Modify: `frontend/src/App.jsx:20-40, 75-85`
- Modify: `frontend/src/pages/GenericList.jsx:2070-2075, 2190-2200`

**Interfaces:**
- Produces: Item de primeiro nível `"Notas Fiscais"` na sidebar com rota `/notas_fiscais`.
- Modifies: `pipelineStatus` no menu Pedidos, removendo a aba `"Nota Fiscal"`.
- Modifies: Redirecionamentos de pós-faturamento e conferência para `/pedidos/Expedição`.

- [x] **Step 1: Atualizar `MainLayout.jsx`**

1. Inserir `{ name: 'Notas Fiscais', path: '/notas_fiscais', icon: FileText, module: 'notas_fiscais' }` no array `menuItems` logo abaixo de `Pedidos`.
2. Remover o item `{ name: 'Nota Fiscal', path: '/pedidos/Nota Fiscal' }` de `pipelineStatus`.
3. Ajustar o highlighting ativo para que `/notas_fiscais` marque o item próprio da sidebar.

- [x] **Step 2: Atualizar `App.jsx`**

1. Adicionar `{ module: 'notas_fiscais', path: '/notas_fiscais' }` no array `modules` de prioridade de redirecionamento.
2. Garantir que a rota `/notas_fiscais` carregue `GenericDispatcher` / `GenericList` com contexto de notas fiscais emitidas e permissão conferida.

- [x] **Step 3: Corrigir redirecionamentos legados em `GenericList.jsx`**

1. Linha 2073: substituir `navigate('/pedidos/Nota Fiscal')` por `navigate('/pedidos/Expedição')`.
2. Linha 2194-2197: remover o alias que convertia `'Expedição'` em `'Nota Fiscal'`, mantendo a navegação pura para `/pedidos/${conferenciaConfig.newStatus}`.

- [x] **Step 4: Verificar compilação do frontend**

Run: `npm --prefix frontend run build` ou validação do Vite sem erros de sintaxe.

- [x] **Step 5: Commit**

```bash
git add frontend/src/components/layout/MainLayout.jsx frontend/src/App.jsx frontend/src/pages/GenericList.jsx
git commit -m "feat(frontend): promover Notas Fiscais a item principal e ajustar navegacao"
```

---

### Task 5: Componente Modal de Inutilização e Histórico de Inutilizações

**Files:**
- Create: `frontend/src/components/nfe/ModalInutilizarNFe.jsx`
- Create: `frontend/src/components/nfe/ModalHistoricoInutilizacoes.jsx`
- Modify: `frontend/src/pages/GenericList.jsx:240-300, 4600-4750`

**Interfaces:**
- Produces: `ModalInutilizarNFe` com campos de modelo, série, faixa inicial/final, justificativa com contador (>= 15 chars), validação e chamada à API `POST /nfe/inutilizar`.
- Produces: `ModalHistoricoInutilizacoes` com listagem e status das inutilizações já homologadas da empresa.
- Modifies: Barra de ferramentas de `GenericList` na visualização de Notas Fiscais com os botões de ação para abrir os novos modais.

- [x] **Step 1: Criar `frontend/src/components/nfe/ModalInutilizarNFe.jsx`**

Implementar o modal respeitando o design system do ERP (fundo escuro/claro, botões Tailwind, fechamento por `Escape`/backdrop, feedback visual de carregamento com `LoadingSpinner`, exibição do protocolo SEFAZ no retorno com Toast).

- [x] **Step 2: Criar `frontend/src/components/nfe/ModalHistoricoInutilizacoes.jsx`**

Implementar modal para listar as faixas inutilizadas da empresa, exibindo: Data, Modelo, Série, Faixa (de X até Y), Justificativa, Protocolo e Status (`cStat 102 - Homologado`).

- [x] **Step 3: Conectar os modais e botões na tela de Notas Fiscais em `GenericList.jsx`**

1. Quando na visualização de Notas Fiscais (`/notas_fiscais` ou contexto fiscal):
   - Renderizar o botão **"Inutilizar Numeração"** (ícone `FileX`) na barra superior de ações.
   - Renderizar o botão **"Histórico de Inutilizações"** (ícone `History`).
2. Vincular os disparadores aos estados `isModalInutilizarOpen` e `isModalHistoricoOpen`.

- [x] **Step 4: Verificar funcionamento e ausência de regressões nos botões existentes**

Garantir que os botões de **DANFE**, **Cancelar NFe**, **Carta de Correção**, **Devolução** e **Complemento** continuem sendo renderizados e disparados normalmente nas linhas da tabela de Notas Fiscais.

- [x] **Step 5: Commit**

```bash
git add frontend/src/components/nfe/ frontend/src/pages/GenericList.jsx
git commit -m "feat(frontend): adicionar ModalInutilizarNFe e historico na tela de notas fiscais"
```

---

### Task 6: Verificação de Ponta a Ponta e Validação de Regressão

**Files:**
- Test: `backend/tests/test_nfe_inutilizacao_*.py`
- Test: Todos os testes existentes de NFe (`backend/tests/test_nfe_logging.py`, etc.)

- [x] **Step 1: Executar suite completa de testes de backend**

Run: `pytest backend/tests/test_nfe_inutilizacao_model.py backend/tests/test_nfe_inutilizacao_service.py backend/tests/test_nfe_inutilizacao_endpoints.py backend/tests/test_nfe_logging.py`  
Expected: 100% PASS

- [x] **Step 2: Validar integridade da aplicação frontend**

Run: `npm --prefix frontend run build`  
Expected: Sucesso no build de produção sem erros de bundle.

- [x] **Step 3: Commit final de verificação**

```bash
git commit --allow-empty -m "chore(nfe): verificacao de suite de testes e integracao concluida"
```

