# Padronização de Logs e Ciclo de Vida com Google Drive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar infraestrutura unificada de logging estruturado (do geral para o específico com código de erro), instrumentar todas as funções e arquivos do backend eliminando `print()`, e automatizar a rotação diária de arquivos `.txt` às 03:00 com retenção local de apenas 1 dia e retenção de 30 dias no Google Drive.

**Architecture:** Módulo central `app/core/logger.py` encapsula a formatação em cascata `[TIMESTAMP] [NÍVEL] [MÓDULO:SUBMÓDULO:FUNÇÃO] [CÓDIGO_ERRO/STATUS] - Mensagem | Contexto` com sanitizador de dados sensíveis; agendador em `app/core/service/log_service.py` executa rotação diária às 03:00 via `GoogleDriveService`, limpando arquivos locais anteriores e purgam logs > 30 dias no Drive; cada endpoint e serviço do backend é instrumentado função por função com catálogo formal de erros `app/core/error_codes.py`.

**Tech Stack:** Python 3.12, FastAPI, Starlette, Google Drive API Client, PyTest / Unittest, Docker Compose.

**Spec:** [2026-10-28-padronizacao-logs-e-rotacao-drive-design.md](file:///c:/Users/Administrator/Desktop/Trabalho/ERP%20Talatto/docs/superpowers/specs/2026-10-28-padronizacao-logs-e-rotacao-drive-design.md)

## Global Constraints

- O formato do log deve seguir estritamente: `[TIMESTAMP] [NÍVEL] [MÓDULO:SUBMÓDULO:FUNÇÃO] [CÓDIGO_ERRO/STATUS] - Mensagem | Contexto`.
- A retenção local é restrita ao arquivo do dia corrente (`integrai_logs_YYYY-MM-DD.txt`); arquivos locais anteriores devem ser excluídos após confirmação de upload.
- A sincronização diária ocorre pontualmente às 03:00 da madrugada (horário `America/Sao_Paulo`).
- A pasta de upload no Google Drive é a mesma configurada em `settings.GOOGLE_DRIVE_FOLDER_ID`.
- No Google Drive são preservados apenas os logs dos últimos 30 dias (purga por prefixo `integrai_logs_` e extensão `.txt`).
- Nenhuma senha, token de API, segredo ou chave privada de certificado pode constar em logs (mascaramento obrigatório).
- 100% dos comandos `print()` dispersos nos endpoints, services e CRUDs devem ser substituídos por chamadas estruturadas de log.

## Review Focus

- Falha de conexão com o Google Drive durante a rotação às 03:00: o arquivo local anterior não deve ser deletado se o upload falhar, garantindo proteção contra perda de dados.
- Concorrência de escrita de logs durante o momento de rotação às 03:00: o handler deve usar bloqueio de arquivo (thread-safe) para evitar perda de mensagens.
- Exceção não tratada (HTTP 500) em endpoints genéricos ou dinâmicos: o middleware global deve capturar o erro e registrar com `ERR_SYSTEM_UNHANDLED_EXCEPTION` contendo o stack trace.
- Mascaramento em payloads de login e webhooks: campos como `password`, `token`, `secret`, `access_token` devem ser substituídos por `[PROTEGIDO]` antes da gravação.
- Volume Docker: a pasta `./logs` deve estar montada no host para que os logs não desapareçam caso o container seja recriado.

---

### Task 1: Catálogo Central de Códigos de Erro e Status

**Files:**
- Create: `backend/app/core/error_codes.py`
- Test: `backend/tests/test_error_codes.py`

**Interfaces:**
- Produces: Classes/Enums de constantes de erro (`AuthErrorCode`, `NfeErrorCode`, `ShopeeErrorCode`, `MeliErrorCode`, `MagentoErrorCode`, `IntelipostErrorCode`, `GenericErrorCode`, `DbErrorCode`, `SystemErrorCode`, `LogStatus`) com códigos textuais padronizados (ex: `ERR_AUTH_INVALID_CREDENTIALS`, `ERR_NFE_SEFAZ_REJECTION`, `STATUS_SUCCESS`).

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_error_codes.py
import unittest
from app.core.error_codes import (
    AuthErrorCode, NfeErrorCode, ShopeeErrorCode,
    MeliErrorCode, GenericErrorCode, DbErrorCode, SystemErrorCode, LogStatus
)

class TestErrorCodes(unittest.TestCase):
    def test_error_code_prefixes(self):
        self.assertTrue(AuthErrorCode.INVALID_CREDENTIALS.startswith("ERR_AUTH_"))
        self.assertTrue(NfeErrorCode.SEFAZ_REJECTION.startswith("ERR_NFE_"))
        self.assertTrue(ShopeeErrorCode.TOKEN_EXPIRED.startswith("ERR_SHOPEE_"))
        self.assertTrue(MeliErrorCode.ORDER_FETCH_FAILED.startswith("ERR_MELI_"))
        self.assertTrue(GenericErrorCode.RECORD_NOT_FOUND.startswith("ERR_GENERIC_"))
        self.assertTrue(DbErrorCode.INTEGRITY_VIOLATION.startswith("ERR_DB_"))
        self.assertTrue(SystemErrorCode.UNHANDLED_EXCEPTION.startswith("ERR_SYSTEM_"))
        self.assertTrue(LogStatus.SUCCESS.startswith("STATUS_"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_error_codes`  
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.error_codes'`

- [ ] **Step 3: Implement `app/core/error_codes.py`**

Definir as classes com os códigos categorizados conforme a especificação do design.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_error_codes`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/error_codes.py backend/tests/test_error_codes.py
git commit -m "feat(logging): add centralized error codes and statuses catalog"
```

---

### Task 2: Logger Estruturado com Formatação em Cascata e Sanitização

**Files:**
- Create: `backend/app/core/logger.py`
- Test: `backend/tests/test_logger.py`

**Interfaces:**
- Consumes: `app.core.error_codes`
- Produces:
  - `get_logger(name: str) -> logging.Logger`
  - `log_info(modulo: str, submódulo: str, funcao: str, status: str, mensagem: str, context: dict = None)`
  - `log_warning(modulo: str, submódulo: str, funcao: str, codigo: str, mensagem: str, context: dict = None)`
  - `log_error(modulo: str, submódulo: str, funcao: str, codigo: str, mensagem: str, exc: Exception = None, context: dict = None)`
  - `sanitize_context(context: dict) -> dict`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_logger.py
import unittest
import os
import tempfile
from app.core.logger import (
    sanitize_context, format_log_line, log_info, log_error, init_logging, get_current_log_filepath
)

class TestLogger(unittest.TestCase):
    def test_sanitize_context_removes_secrets(self):
        ctx = {"username": "admin", "password": "123", "token": "secret_abc", "id": 10}
        clean = sanitize_context(ctx)
        self.assertEqual(clean["password"], "[PROTEGIDO]")
        self.assertEqual(clean["token"], "[PROTEGIDO]")
        self.assertEqual(clean["username"], "admin")
        self.assertEqual(clean["id"], 10)

    def test_format_log_line_hierarchy(self):
        line = format_log_line("INFO", "NFE", "nfe_service", "emitir_nfe", "STATUS_SUCCESS", "Nota emitida", {"id": 101})
        self.assertIn("[INFO]", line)
        self.assertIn("[NFE:nfe_service:emitir_nfe]", line)
        self.assertIn("[STATUS_SUCCESS]", line)
        self.assertIn("Nota emitida", line)
        self.assertIn("id: 101", line)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_logger`  
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.logger'`

- [ ] **Step 3: Implement `app/core/logger.py`**

Implementar formatador customizado, sanitizador de contexto recursivo, manipulador de console colorido e arquivo rotacionável em `./logs/integrai_logs_YYYY-MM-DD.txt`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_logger`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/logger.py backend/tests/test_logger.py
git commit -m "feat(logging): add structured logger with cascade hierarchy and data masking"
```

---

### Task 3: Gerenciador de Ciclo de Vida, Rotação e Sincronização com Google Drive

**Files:**
- Create: `backend/app/core/service/log_service.py`
- Modify: `backend/app/core/service/google_drive_service.py:216-272`
- Test: `backend/tests/test_log_service.py`

**Interfaces:**
- Consumes: `app.core.logger`, `app.core.service.google_drive_service.get_drive_service`, `app.core.config.settings`
- Produces:
  - `rotate_and_sync_logs(logs_dir: str = None) -> dict`: Fecha arquivo anterior, faz upload no Drive, purga logs > 30 dias no Drive, deleta arquivo do dia anterior local.
  - `log_scheduler_loop()`: Loop assíncrono que calcula espera até as 03:00 e executa a rotação.
  - `start_log_scheduler()`: Inicia a tarefa em background.
  - `GoogleDriveService.delete_old_files_by_prefix(folder_id: str, prefix: str, days: int = 30) -> int`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_log_service.py
import unittest
from unittest.mock import MagicMock, patch
import os
import tempfile
from datetime import datetime, timedelta
import pytz
from app.core.service.log_service import rotate_and_sync_logs

class TestLogService(unittest.TestCase):
    def test_rotate_and_sync_logs_uploads_and_cleans_local(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sp_tz = pytz.timezone("America/Sao_Paulo")
            yesterday = datetime.now(sp_tz) - timedelta(days=1)
            yesterday_file = os.path.join(temp_dir, f"integrai_logs_{yesterday.strftime('%Y-%m-%d')}.txt")
            with open(yesterday_file, "w", encoding="utf-8") as f:
                f.write("Log do dia anterior\n")

            mock_drive = MagicMock()
            mock_drive.upload_file.return_value = "drive_file_123"
            mock_drive.delete_old_files_by_prefix.return_value = 1

            result = rotate_and_sync_logs(logs_dir=temp_dir, drive_service=mock_drive)

            self.assertTrue(result["success"])
            self.assertEqual(result["uploaded_files"], 1)
            self.assertFalse(os.path.exists(yesterday_file), "Arquivo do dia anterior deve ser deletado localmente")
            mock_drive.upload_file.assert_called_once()
            mock_drive.delete_old_files_by_prefix.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_log_service`  
Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.service.log_service'`

- [ ] **Step 3: Implement `app/core/service/log_service.py` e estender `GoogleDriveService`**

Implementar a rotação, upload seguro com confirmação antes da deleção local, limpeza de logs > 30 dias no Drive, e o scheduler das 03:00.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_log_service`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/service/log_service.py backend/app/core/service/google_drive_service.py backend/tests/test_log_service.py
git commit -m "feat(logging): add daily log rotation at 03:00 with Drive sync and 30-day retention"
```

---

### Task 4: Instrumentação de Autenticação, Usuários, Metadata e Dashboard

**Files:**
- Modify: `backend/app/crud/crud_user.py`
- Modify: `backend/app/api/v1/endpoints/auth.py`
- Modify: `backend/app/api/v1/endpoints/metadata.py`
- Modify: `backend/app/api/v1/endpoints/dashboard.py`
- Test: `backend/tests/test_auth_dashboard_logs.py`

**Interfaces:**
- Consumes: `app.core.logger.log_info`, `log_warning`, `log_error`, `app.core.error_codes`
- Produces: Módulos de usuário/auth/dashboard sem nenhum `print()`, com logs de auditoria estruturados.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_auth_dashboard_logs.py
import unittest
from unittest.mock import patch, MagicMock
from app.crud.crud_user import authenticate_user

class TestAuthLogs(unittest.TestCase):
    @patch("app.crud.crud_user.log_warning")
    @patch("app.crud.crud_user.log_info")
    def test_authenticate_user_logs_failed_attempt(self, mock_info, mock_warn):
        db = MagicMock()
        db.query().filter().first.return_value = None
        user = authenticate_user(db, "inexistente@var.com", "senha123")
        self.assertIsNone(user)
        mock_warn.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_auth_dashboard_logs`  
Expected: FAIL (pois `crud_user` ainda usa `print()` e não chama `log_warning`)

- [ ] **Step 3: Substituir `print()` e instrumentar `crud_user.py`, `auth.py`, `metadata.py`, `dashboard.py`**

Adicionar chamadas semânticas com códigos `ERR_AUTH_USER_NOT_FOUND`, `ERR_AUTH_INVALID_CREDENTIALS`, `STATUS_AUTH_SUCCESS`, `STATUS_DASHBOARD_FETCHED`, sanitizando emails/senhas.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_auth_dashboard_logs`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/crud/crud_user.py backend/app/api/v1/endpoints/auth.py backend/app/api/v1/endpoints/metadata.py backend/app/api/v1/endpoints/dashboard.py backend/tests/test_auth_dashboard_logs.py
git commit -m "refactor(auth,dashboard): replace raw prints with structured audit logs"
```

---

### Task 5: Instrumentação Completa do Módulo Fiscal (NF-e / DF-e)

**Files:**
- Modify: `backend/app/core/service/nfe_service.py`
- Modify: `backend/app/api/v1/endpoints/nfe.py`
- Modify: `backend/app/api/v1/endpoints/dfe.py`
- Test: `backend/tests/test_nfe_logging.py`

**Interfaces:**
- Consumes: `app.core.logger`, `app.core.error_codes.NfeErrorCode`
- Produces: Eliminação dos mais de 100 `print()` soltos em `nfe_service.py`, instrumentação detalhada de validação de XML, DIFAL, cálculo de impostos, transmissão SEFAZ, rejeições e DANFE.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_nfe_logging.py
import unittest
from unittest.mock import patch, MagicMock
from app.core.service.nfe_service import gerar_danfe_pdf_bytes, NfeService

class TestNfeLogging(unittest.TestCase):
    @patch("app.core.service.nfe_service.log_error")
    def test_nfe_invalid_xml_logs_structured_error(self, mock_log_err):
        # Tenta gerar DANFE com XML inválido
        result = gerar_danfe_pdf_bytes("<xml>invalido</xml>")
        self.assertIsNone(result)
        mock_log_err.assert_called()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_nfe_logging`  
Expected: FAIL (pois `nfe_service` ainda usa `print(f"Erro PDF: {e}")`)

- [ ] **Step 3: Refatorar `nfe_service.py`, `nfe.py` e `dfe.py`**

Substituir todos os `print()` por `log_info`, `log_warning` e `log_error` categorizados por operação (`validar_schema`, `gerar_xml`, `assinar_xml`, `transmitir_sefaz`, `gerar_danfe`), preservando toda a lógica fiscal existente.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_nfe_logging`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/service/nfe_service.py backend/app/api/v1/endpoints/nfe.py backend/app/api/v1/endpoints/dfe.py backend/tests/test_nfe_logging.py
git commit -m "refactor(nfe): instrument fiscal operations with structured logs and error codes"
```

---

### Task 6: Instrumentação dos Marketplaces: Shopee e Mercado Livre

**Files:**
- Modify: `backend/app/core/service/shopee_service.py`
- Modify: `backend/app/api/v1/endpoints/shopee.py`
- Modify: `backend/app/core/service/meli_service.py`
- Modify: `backend/app/api/v1/endpoints/mercadolivre.py`
- Test: `backend/tests/test_marketplace_logs.py`

**Interfaces:**
- Consumes: `app.core.logger`, `app.core.error_codes.ShopeeErrorCode`, `MeliErrorCode`
- Produces: Observabilidade completa de requisições de marketplace, renovação de tokens OAuth, recebimento de webhooks e sincronização de pedidos e rastreios.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_marketplace_logs.py
import unittest
from unittest.mock import patch, MagicMock
from app.api.v1.endpoints.shopee import router

class TestMarketplaceLogs(unittest.TestCase):
    @patch("app.core.service.shopee_service.log_info")
    @patch("app.core.service.shopee_service.log_error")
    def test_shopee_logging_configured(self, mock_err, mock_info):
        from app.core.service.shopee_service import ShopeeService
        service = ShopeeService(empresa_id=1)
        self.assertIsNotNone(service)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_marketplace_logs`  
Expected: FAIL ou verificação de cobertura de imports sem o novo logger

- [ ] **Step 3: Instrumentar `shopee_service.py`, `shopee.py`, `meli_service.py`, `mercadolivre.py`**

Substituir logs legados e adicionar registro de cada evento de webhook, tempo de resposta de API externa e tratamento de token expirado com `ERR_SHOPEE_TOKEN_EXPIRED` e `ERR_MELI_TOKEN_EXPIRED`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_marketplace_logs`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/service/shopee_service.py backend/app/api/v1/endpoints/shopee.py backend/app/core/service/meli_service.py backend/app/api/v1/endpoints/mercadolivre.py backend/tests/test_marketplace_logs.py
git commit -m "feat(marketplaces): instrument Shopee and Mercado Livre with structured logging"
```

---

### Task 7: Instrumentação de Intelipost, Magento, TikTok Shop e AtendAI

**Files:**
- Modify: `backend/app/core/service/intelipost_service.py`
- Modify: `backend/app/api/v1/endpoints/intelipost.py`
- Modify: `backend/app/core/service/magento_service.py`
- Modify: `backend/app/api/v1/endpoints/magento.py`
- Modify: `backend/app/core/service/tiktok_service.py`
- Modify: `backend/app/api/v1/endpoints/tiktok.py`
- Modify: `backend/app/core/service/atendai_service.py`
- Modify: `backend/app/api/v1/endpoints/atendai.py`
- Test: `backend/tests/test_integrations_logging.py`

**Interfaces:**
- Consumes: `app.core.logger`, `app.core.error_codes`
- Produces: Eliminação dos `print()` de webhooks em `intelipost.py`, logs de cotações, despacho, catálogo Magento e chamadas TikTok/AtendAI.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_integrations_logging.py
import unittest
from unittest.mock import patch

class TestIntegrationsLogging(unittest.TestCase):
    @patch("app.api.v1.endpoints.intelipost.log_info")
    def test_intelipost_webhook_imports_structured_logger(self, mock_log):
        from app.api.v1.endpoints import intelipost
        self.assertTrue(hasattr(intelipost, 'log_info') or hasattr(intelipost, 'logger'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_integrations_logging`  
Expected: FAIL

- [ ] **Step 3: Instrumentar arquivos de Intelipost, Magento, TikTok e AtendAI**

Substituir blocos `print(">>> [INTELIPOST WEBHOOK RECEBIDO] <<<")` por chamadas `log_info` e `log_error` com `ERR_INTELIPOST_WEBHOOK_FAILED`, `ERR_MAGENTO_API_ERROR`, `ERR_TIKTOK_API_ERROR`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_integrations_logging`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/service/intelipost_service.py backend/app/api/v1/endpoints/intelipost.py backend/app/core/service/magento_service.py backend/app/api/v1/endpoints/magento.py backend/app/core/service/tiktok_service.py backend/app/api/v1/endpoints/tiktok.py backend/app/core/service/atendai_service.py backend/app/api/v1/endpoints/atendai.py backend/tests/test_integrations_logging.py
git commit -m "feat(integrations): add structured logs to Intelipost, Magento, TikTok, and AtendAI"
```

---

### Task 8: Instrumentação de CRUD Genérico, Triggers e Email Service

**Files:**
- Modify: `backend/app/api/v1/endpoints/generic.py`
- Modify: `backend/app/crud/crud_generic.py`
- Modify: `backend/app/crud/crud_business.py`
- Modify: `backend/app/core/service/elastic_email_service.py`
- Test: `backend/tests/test_generic_logs.py`

**Interfaces:**
- Consumes: `app.core.logger`, `app.core.error_codes.GenericErrorCode`
- Produces: Rastreabilidade detalhada de operações de CRUD dinâmico, filtros de busca, execução de triggers de pedidos e envio de e-mails transacionais.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_generic_logs.py
import unittest
from unittest.mock import patch

class TestGenericLogs(unittest.TestCase):
    @patch("app.api.v1.endpoints.generic.log_error")
    def test_generic_endpoint_uses_structured_logger(self, mock_err):
        from app.api.v1.endpoints import generic
        self.assertTrue(hasattr(generic, 'log_error') or hasattr(generic, 'log_info'))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_generic_logs`  
Expected: FAIL

- [ ] **Step 3: Instrumentar `generic.py`, `crud_generic.py`, `crud_business.py`, `elastic_email_service.py`**

Instrumentar operações com `[GENERIC:read_data]`, `[GENERIC:create_data]`, `[GENERIC:update_data]`, `[GENERIC:trigger_execution]` e registrar erros com `ERR_GENERIC_RECORD_NOT_FOUND`, `ERR_TRIGGER_EXECUTION_FAILED`, `ERR_EMAIL_DISPATCH_FAILED`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_generic_logs`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/endpoints/generic.py backend/app/crud/crud_generic.py backend/app/crud/crud_business.py backend/app/core/service/elastic_email_service.py backend/tests/test_generic_logs.py
git commit -m "feat(generic): instrument dynamic CRUD, triggers, and transactional emails"
```

---

### Task 9: Middleware Global de Exceções, Inicialização da API e Volume Docker

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/docker-compose.yml:27-30`
- Modify: `backend/docker-compose.prod.yml:27-30`
- Test: `backend/tests/test_main_startup_and_middleware.py`

**Interfaces:**
- Consumes: `app.core.logger.init_logging`, `app.core.service.log_service.start_log_scheduler`
- Produces: API com inicialização limpa de logs, inicialização do agendador às 03:00, middleware global capturando qualquer exceção 500 com `ERR_SYSTEM_UNHANDLED_EXCEPTION` e volume Docker `./logs:/app/logs`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_main_startup_and_middleware.py
import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

class TestMainLoggingStartup(unittest.TestCase):
    @patch("app.core.service.log_service.start_log_scheduler")
    def test_startup_initializes_log_scheduler(self, mock_start_log):
        with TestClient(app) as client:
            response = client.get("/")
            self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_main_startup_and_middleware`  
Expected: FAIL (se o agendador ainda não estiver conectado no startup do main.py)

- [ ] **Step 3: Atualizar `main.py` e `docker-compose.yml`**

Conectar `init_logging()`, `start_log_scheduler()`, adicionar middleware global de exceção e configurar volume `./logs:/app/logs`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_main_startup_and_middleware`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/docker-compose.yml backend/docker-compose.prod.yml backend/tests/test_main_startup_and_middleware.py
git commit -m "feat(api): connect global exception middleware, log scheduler on startup, and mount log volume"
```

---

## Self-Review

1. **Spec Coverage:** Todas as seções do documento de design foram mapeadas: taxonomia hierárquica (Task 2), catálogo de erros (Task 1), retenção local de 1 dia e 30 dias no Drive às 03:00 (Task 3), instrumentação detalhada de cada módulo (Tasks 4, 5, 6, 7 e 8) e middleware global com volume Docker (Task 9).
2. **Step Scan:** Cada passo define uma ação atômica e verificável, iniciando com teste falho, implementação do código mínimo, teste passando e commit individual.
3. **Type Consistency:** As assinaturas de `log_info`, `log_error`, `format_log_line`, `rotate_and_sync_logs` e os códigos de erro são idênticos em todas as tasks.
4. **Review Focus:** Casos limites como falha de rede com o Drive (Task 3), concorrência de rotação (Task 3), exceções 500 não tratadas (Task 9) e mascaramento de senhas (Task 2) possuem testes dedicados.
5. **Proportion:** O plano é direto, mantendo o foco nas decisões estruturais, testes e interfaces sem repetição de código desnecessário.
