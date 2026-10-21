# Plano de Implementação: Importação de Inscrição Estadual e Indicador de Contribuinte ICMS no Magento

> **Para executores:** SUB-SKILL NECESSÁRIA: Use `superpowers:executing-plans` para implementar este plano tarefa por tarefa. Os passos utilizam a sintaxe de caixas de seleção (`- [ ]`) para acompanhamento.

**Objetivo:** Implementar a detecção e atribuição automática da Inscrição Estadual (IE) e do Indicador de Contribuinte do ICMS (`indicador_ie`) durante a importação de pedidos do Magento, integrando com consulta cadastral oficial na SEFAZ (CadConsultaCadastro4) para clientes Pessoa Jurídica (PJ), sem herança de dados entre empresas, e atualizando cadastros pré-existentes na empresa atual.

**Arquitetura:**
1. Criação do método de consulta cadastral oficial SEFAZ (`consultar_cadastro_sefaz`) no `NFeService`, utilizando o certificado digital A1 da empresa e a biblioteca `pynfe.processamento.comunicacao.ComunicacaoSefaz`.
2. Atualização do `MagentoService._find_or_create_customer`:
   - Extração de possíveis campos customizados de IE do payload do Magento (`billing_address` / `order`).
   - Se for Pessoa Jurídica (CNPJ de 14 dígitos) e a IE não estiver presente, consulta automática à SEFAZ da UF do cliente.
   - Aplicação da regra fiscal do `indicador_ie` (`"1"` para Contribuinte habilitado com IE, `"2"` para Isento, `"9"` para Não Contribuinte).
   - Atualização automática de clientes já existentes na empresa caso a IE seja descoberta e estivesse nula ou desatualizada.
3. Alertas preventivos na importação de pedidos caso um PJ seja registrado como Não Contribuinte (`indicador_ie = 9`), prevenindo a Rejeição 232 da SEFAZ na emissão da NF-e.

**Stack Tecnológica:** Python 3.12, FastAPI, SQLAlchemy, PyNFe, lxml, PostgreSQL.

---

## Restrições Globais

- **Sem herança entre empresas:** A busca e criação de clientes deve operar estritamente dentro da empresa do pedido (`id_empresa == self.id_empresa`). Não transferir nem copiar dados de cadastros de outras empresas.
- **Resiliência a falhas:** Caso a SEFAZ do estado do destinatário esteja indisponível, a importação do pedido NÃO pode falhar; deve prosseguir como Não Contribuinte (`indicador_ie = 9`) e registrar aviso no pedido.
- **Caso base:** O cliente `Tolehidro Mangueiras e Hidráulicos LTDA` (CNPJ `33.615.973/0001-94`, UF `PR`), vinculado ao pedido Magento `1386`, deve obter IE `9081417927` e `indicador_ie = "1"`.

---

## Foco de Revisão

1. **Cliente PJ com mais de uma IE no estado:** SEFAZ pode retornar múltiplos nós `infCad`. O sistema deve selecionar o estabelecimento habilitado (`cSit = 1`) coincidente com o CNPJ.
2. **Cliente PJ sem IE na UF (Não Contribuinte real):** SEFAZ retorna `cStat = 259` ("CNPJ não cadastrado como contribuinte"). O sistema deve gravar `indicador_ie = 9` e `inscricao_estadual = None` sem gerar exceção.
3. **Certificado da empresa ausente ou expirado:** A consulta SEFAZ deve interceptar o erro e não abortar a importação do pedido Magento.
4. **IE contendo formatação no Magento (pontos e traços):** A IE deve ser sanitizada mantendo apenas dígitos (ou a palavra literal "ISENTO").
5. **Cliente existente na empresa com cadastro incompleto:** Clientes já salvos com `indicador_ie = 9` e sem IE devem ter seus dados atualizados para `indicador_ie = 1` e a IE preenchida ao receber novo pedido com IE identificada.

---

### Tarefa 1: Método de Consulta Cadastral SEFAZ (`consultar_cadastro_sefaz`)

**Arquivos:**
- Modificar: `backend/app/core/service/nfe_service.py:180-220`
- Teste: `backend/tests/test_sefaz_consulta_cadastro.py`

**Interfaces:**
- Produz: `NFeService.consultar_cadastro_sefaz(documento: str, uf: str) -> Optional[Dict[str, Any]]`
  - Retorno: Dict contendo `{"ie": str, "habilitado": bool, "razao_social": str, "nome_fantasia": str, "cidade_ibge": str}` ou `None` se não encontrado/erro.

- [ ] **Passo 1: Escrever teste de unidade para o método de consulta cadastral**
Criar teste mockando a resposta SOAP da SEFAZ para validar o parsing dos nós `retConsCad`, `infCad`, `IE`, `cSit`, `xNome`, `xFant`, `cMun`.

- [ ] **Passo 2: Executar o teste para verificar falha inicial**
Comando: `pytest backend/tests/test_sefaz_consulta_cadastro.py -v`

- [ ] **Passo 3: Implementar `consultar_cadastro_sefaz` em `NFeService`**
Adicionar o método que recupera o certificado da empresa, instancia `ComunicacaoSefaz`, chama `con.consulta_cadastro(modelo='nfe', documento=clean_doc, tipo='CNPJ', uf=uf.upper())` e faz o parse do XML de retorno.

- [ ] **Passo 4: Executar o teste para verificar aprovação**
Comando: `pytest backend/tests/test_sefaz_consulta_cadastro.py -v`

---

### Tarefa 2: Extração de IE e Atribuição do `indicador_ie` no `MagentoService`

**Arquivos:**
- Modificar: `backend/app/core/service/magento_service.py:658-729`
- Modificar: `backend/app/core/service/magento_service.py:421-460`
- Teste: `backend/tests/test_magento_customer_ie.py`

**Interfaces:**
- Modifica: `MagentoService._find_or_create_customer(order_data: dict) -> models.Cadastro`
- Modifica: `MagentoService.import_order(magento_entity_id: int)`

- [ ] **Passo 1: Escrever teste automatizado para `_find_or_create_customer`**
Validar:
1. Extração de IE de custom_attributes (se existir).
2. Consulta SEFAZ quando não houver IE e for PJ.
3. Atribuição de `indicador_ie = 1` quando houver IE ativa.
4. Atribuição de `indicador_ie = 9` quando não houver IE.
5. Atualização de cadastro existente se IE for descoberta.

- [ ] **Passo 2: Implementar extração de atributos de IE no Magento**
Verificar campos em `billing.custom_attributes`, `order.custom_attributes`, `billing.vat_id`, etc.

- [ ] **Passo 3: Integrar consulta SEFAZ no fluxo do cliente PJ**
Se o documento for CNPJ (14 dígitos) e não tiver IE informada, instanciar `NFeService` da mesma empresa e invocar `consultar_cadastro_sefaz`.
Se retornar IE ativa (`habilitado == True`), gravar `inscricao_estadual` e `indicador_ie = CadastroIndicadorIEEnum.contribuinte_icms`.
Preencher também `fantasia` e `cidade_ibge` se retornados pela SEFAZ.

- [ ] **Passo 4: Atualizar cadastro existente na empresa se dados fiscais foram enriquecidos**
Se o cliente já existir na empresa com `indicador_ie = 9` ou `inscricao_estadual` vazia, atualizar os campos fiscais com os dados obtidos e salvar.

- [ ] **Passo 5: Adicionar alerta preventivo no pedido para PJ Não Contribuinte**
Em `import_order`, se o cliente for PJ e `indicador_ie == "9"`, adicionar mensagem informativa de aviso nos `import_warning` do pedido.

- [ ] **Passo 6: Executar os testes de importação de cliente**
Comando: `pytest backend/tests/test_magento_customer_ie.py -v`

---

### Tarefa 3: Validação com o Caso Real (Tolehidro - Pedido 1386)

**Arquivos:**
- Script de Validação / Teste E2E: `scratch/validate_tolehidro_import.py`
- Banco de dados: Empresa 3, Cliente 5656, Pedido 8119 / Pedido Magento 1386

- [ ] **Passo 1: Executar script de validação para reprocessar o cliente Tolehidro**
Verificar que a chamada ao `_find_or_create_customer` com os dados do pedido 1386 na Empresa 3:
1. Consulta a SEFAZ PR.
2. Atualiza o cliente 5656 na Empresa 3 com IE `9081417927` e `indicador_ie = 1`.
3. Preenche nome fantasia `TOLEHIDRO MANGUEIRAS E HIDRAULICOS`.
4. Mantém o cliente na Empresa 3 sem tocar nos dados da Empresa 1.

- [ ] **Passo 2: Verificar a classificação tributária para NF-e**
Simular a classificação tributária em `nfe_service.py` para o cliente 5656:
- Confirmar que `tipo_cliente` passa a ser `RegraTipoClienteEnum.pj_contribuinte`.
- Confirmar que `ind_ie` da NFe passa a ser `1`.
- Confirmar que a NF-e não sofre rejeição 232.
