import enum
from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, Enum as SQLAlchemyEnum,
    BigInteger, DateTime, Numeric, JSON, Text, Date, LargeBinary, TypeDecorator,
    UniqueConstraint, event
)
from sqlalchemy.orm import relationship, Mapper
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import func
from .database import Base
from .types import IntEnum, SafeStrEnum, Currency, EncryptedString, EncryptedJSON


# --- Definição de Enums ---
# (Centralizando todos os Enums definidos nas planilhas)

class EstadoEnum(str, enum.Enum):
    AC = "AC"
    AL = "AL"
    AP = "AP"
    AM = "AM"
    BA = "BA"
    CE = "CE"
    DF = "DF"
    ES = "ES"
    GO = "GO"
    MA = "MA"
    MT = "MT"
    MS = "MS"
    MG = "MG"
    PA = "PA"
    PB = "PB"
    PR = "PR"
    PE = "PE"
    PI = "PI"
    RJ = "RJ"
    RN = "RN"
    RS = "RS"
    RO = "RO"
    RR = "RR"
    SC = "SC"
    SP = "SP"
    SE = "SE"
    TO = "TO"
    EX = "EX"

# Para Empresa 
class EmpresaCRTEnum(int, enum.Enum):
    simples_nacional = 1
    simples_excesso = 2
    lucro_presumido = 3
    lucro_real = 4

class EmpresaAmbienteSefazEnum(int, enum.Enum):
    producao = 1
    homologacao = 2

    @property
    def description(self):
        return "Produção" if self == 1 else "Homologação"

# Para Usuario 
class UsuarioPerfilEnum(str, enum.Enum):
    admin = "admin"
    vendedor = "vendedor"
    financeiro = "financeiro"
    estoquista = "estoquista"

# Para Cadastro 
class CadastroTipoPessoaEnum(str, enum.Enum):
    fisica = "fisica"
    juridica = "juridica"

class CadastroTipoCadastroEnum(str, enum.Enum):
    cliente = "cliente"
    fornecedor = "fornecedor"
    transportadora = "transportadora"
    vendedor = "vendedor"
    colaborador = "colaborador"
    
class CadastroIndicadorIEEnum(str, enum.Enum):
    contribuinte_icms = "1"
    nao_contribuinte = "9"

# Para Produto 
class ProdutoUnidadeEnum(str, enum.Enum):
    un = "un"
    pc = "pc"
    kg = "kg"
    mt = "mt"
    cx = "cx"
    lt = "lt"
    par = "par"
    m2 = "m2"
    m3 = "m3"

class ProdutoTipoEnum(str, enum.Enum):
    mercadoria_revenda = "mercadoria de revenda"
    materia_prima = "materia prima"
    produto_acabado = "produto acabado"
    servico = "servico"

class ProdutoOrigemEnum(str, enum.Enum):
    nacional = "nacional"
    estrangeira_import_direta = "estrangeira_import_direta"
    estrangeira_adq_merc_interno = "estrangeira_adq_merc_interno"
    nacional_conteudo_import_40 = "nacional_conteudo_import_40"
    nacional_conteudo_import_70 = "nacional_conteudo_import_70"
    nacional_producao_basica = "nacional_producao_basica"
    
# Para Conta 
class ContaTipoEnum(str, enum.Enum):
    a_receber = "A Receber"
    a_pagar = "A Pagar"

class ContaSituacaoEnum(str, enum.Enum):
    em_aberto = "Em Aberto"
    pago = "Pago"
    vencido = "Vencido"
    cancelado = "Cancelado"


# Para Estoque 
class EstoqueSituacaoEnum(str, enum.Enum):
    entrada = "Entrada"
    saida = "Saída"
    inventario = "Inventário"

# Para Pedido 
class PedidoSituacaoEnum(str, enum.Enum):
    orcamento = "Orçamento"
    aprovacao = "Aprovação"
    programacao = "Programação"
    producao = "Produção"
    embalagem = "Embalagem"
    faturamento = "Faturamento"
    expedicao = "Expedição"
    despachado = "Despachado"
    cancelado = "Cancelado"

class PedidoModalidadeFreteEnum(str, enum.Enum):
    cif = "0"
    fob = "1"
    terceiros = "2"
    proprio_remetente = "3"
    proprio_destinatario = "4"
    sem_frete = "9"

class PedidoIndicadorPresencaEnum(int, enum.Enum):
    nao_se_aplica = 0
    presencial = 1
    internet = 2
    teleatendimento = 3
    nfce_entrega = 4
    presencial_fora = 5
    outros = 9


# Para Tributacao 
class RegraRegimeEmitenteEnum(str, enum.Enum):
    simples_nacional = "Simples Nacional"
    lucro_presumido = "Lucro Presumido"
    lucro_real = "Lucro Real"

class RegraTipoOperacaoEnum(str, enum.Enum):
    venda_mercadoria = "Venda de Mercadoria"
    venda_producao = "Venda de Produção"
    revenda = "Revenda de Mercadoria"
    devolucao_entrada = "Devolução - Entrada"
    devolucao_saida = "Devolução - Saída"
    remessa_conserto = "Remessa para Conserto"
    remessa_demonstracao = "Remessa para Demonstração"
    retorno_conserto = "Retorno de Conserto"
    transferencia = "Transferência"
    bonificacao = "Bonificação"
    outras = "Outras"

class RegraTipoClienteEnum(str, enum.Enum):
    pf = "PF"
    pj_contribuinte = "PJ_Contribuinte"
    pj_isento = "PJ_Isento"
    pj_nao_contribuinte = "PJ_NaoContribuinte"

class RegraLocalizacaoDestinoEnum(str, enum.Enum):
    interna = "Interna"
    interestadual = "Interestadual"
    exterior = "Exterior"

class FiscalOrigemEnum(str, enum.Enum):
    origem_0 = "0"
    origem_1 = "1"
    origem_2 = "2"
    origem_3 = "3"
    origem_4 = "4"
    origem_5 = "5"
    origem_6 = "6"
    origem_7 = "7"
    origem_8 = "8"

    @property
    def description(self):
        descriptions = {
            "0": "0 - Nacional",
            "1": "1 - Estrangeira (Importação direta)",
            "2": "2 - Estrangeira (Adquirida no mercado interno)",
            "3": "3 - Nacional (Conteúdo de Importação > 40% e <= 70%)",
            "4": "4 - Nacional (Produção em conformidade com processos produtivos básicos)",
            "5": "5 - Nacional (Conteúdo de Importação <= 40%)",
            "6": "6 - Estrangeira (Importação direta, sem similar nacional)",
            "7": "7 - Estrangeira (Adquirida no mercado interno, sem similar nacional)",
            "8": "8 - Nacional (Importação > 70%)"
        }
        return descriptions.get(self.value, self.value)

# Para Fiscal (CSTs)
class FiscalICMSCSTEnum(str, enum.Enum):
    # Regime Normal
    cst_00 = "00"
    cst_10 = "10"
    cst_20 = "20"
    cst_30 = "30"
    cst_40 = "40"
    cst_41 = "41"
    cst_50 = "50"
    cst_51 = "51"
    cst_60 = "60"
    cst_70 = "70"
    cst_90 = "90"
    # Simples Nacional (CSOSN)
    csosn_101 = "101"
    csosn_102 = "102"
    csosn_103 = "103"
    csosn_201 = "201"
    csosn_202 = "202"
    csosn_203 = "203"
    csosn_300 = "300"
    csosn_400 = "400"
    csosn_500 = "500"
    csosn_900 = "900"

    @property
    def description(self):
        descriptions = {
            "00": "00 - Tributada integralmente",
            "10": "10 - Tributada e com cobrança do ICMS por ST",
            "20": "20 - Com redução de base de cálculo",
            "30": "30 - Isenta ou não tributada e com cobrança do ICMS por ST",
            "40": "40 - Isenta",
            "41": "41 - Não tributada",
            "50": "50 - Suspensão",
            "51": "51 - Diferimento",
            "60": "60 - ICMS cobrado anteriormente por ST",
            "70": "70 - Com redução de BC e cobrança do ICMS por ST",
            "90": "90 - Outras",
            "101": "101 - Tributada pelo Simples Nacional com permissão de crédito",
            "102": "102 - Tributada pelo Simples Nacional sem permissão de crédito",
            "103": "103 - Isenção do ICMS no Simples Nacional para faixa de receita bruta",
            "201": "201 - Tributada pelo Simples Nacional com permissão de crédito e com cobrança do ICMS por ST",
            "202": "202 - Tributada pelo Simples Nacional sem permissão de crédito e com cobrança do ICMS por ST",
            "203": "203 - Isenção do ICMS no Simples Nacional para faixa de receita bruta e com cobrança do ICMS por ST",
            "300": "300 - Imune",
            "400": "400 - Não tributada pelo Simples Nacional",
            "500": "500 - ICMS cobrado anteriormente por ST (substituído) ou por antecipação",
            "900": "900 - Outros"
        }
        return descriptions.get(self.value, self.value)

class FiscalIPICSTEnum(str, enum.Enum):
    ipi_00 = "00"
    ipi_01 = "01"
    ipi_02 = "02"
    ipi_03 = "03"
    ipi_04 = "04"
    ipi_05 = "05"
    ipi_49 = "49"
    ipi_50 = "50"
    ipi_51 = "51"
    ipi_52 = "52"
    ipi_53 = "53"
    ipi_54 = "54"
    ipi_55 = "55"
    ipi_99 = "99"

    @property
    def description(self):
        descriptions = {
            "00": "00 - Entrada com recuperação de crédito",
            "01": "01 - Entrada tributada com alíquota zero",
            "02": "02 - Entrada isenta",
            "03": "03 - Entrada não-tributada",
            "04": "04 - Entrada imune",
            "05": "05 - Entrada com suspensão",
            "49": "49 - Outras entradas",
            "50": "50 - Saída tributada",
            "51": "51 - Saída tributada com alíquota zero",
            "52": "52 - Saída isenta",
            "53": "53 - Saída não-tributada",
            "54": "54 - Saída imune",
            "55": "55 - Saída com suspensão",
            "99": "99 - Outras saídas"
        }
        return descriptions.get(self.value, self.value)

class FiscalPISCOFINSCSTEnum(str, enum.Enum):
    cst_01 = "01"
    cst_02 = "02"
    cst_03 = "03"
    cst_04 = "04"
    cst_05 = "05"
    cst_06 = "06"
    cst_07 = "07"
    cst_08 = "08"
    cst_09 = "09"
    cst_49 = "49"
    cst_50 = "50"
    cst_51 = "51"
    cst_52 = "52"
    cst_53 = "53"
    cst_54 = "54"
    cst_55 = "55"
    cst_56 = "56"
    cst_60 = "60"
    cst_61 = "61"
    cst_62 = "62"
    cst_63 = "63"
    cst_64 = "64"
    cst_65 = "65"
    cst_66 = "66"
    cst_67 = "67"
    cst_70 = "70"
    cst_71 = "71"
    cst_72 = "72"
    cst_73 = "73"
    cst_74 = "74"
    cst_75 = "75"
    cst_98 = "98"
    cst_99 = "99"

class FiscalPagamentoEnum(str, enum.Enum):
    dinheiro = "01"
    cheque = "02"
    cartao_credito = "03"
    cartao_debito = "04"
    credito_loja = "05"
    vale_alimentacao = "10"
    vale_refeicao = "11"
    vale_presente = "12"
    vale_combustivel = "13"
    duplicata_mercantil = "14"
    boleto_bancario = "15"
    deposito_bancario = "16"
    pix = "17"
    debito_em_conta = "18"
    sem_pagamento = "90"
    outros = "99"

    @property
    def description(self):
        descriptions = {
            "01": "DINHEIRO",
            "02": "CHEQUE",
            "03": "CARTÃO DE CRÉDITO",
            "04": "CARTÃO DE DÉBITO",
            "05": "CRÉDITO LOJA",
            "10": "VALE ALIMENTAÇÃO",
            "11": "VALE REFEIÇÃO",
            "12": "VALE PRESENTE",
            "13": "VALE COMBUSTÍVEL",
            "14": "DUPLICATA MERCANTIL",
            "15": "BOLETO BANCÁRIO",
            "16": "DEPÓSITO BANCÁRIO",
            "17": "PIX",
            "18": "DÉBITO EM CONTA",
            "90": "SEM PAGAMENTO",
            "99": "OUTROS"
        }
        return descriptions.get(self.value, self.value)

# --- Tipos Customizados ---
# --- Tipos customizados centralizados em types.py ---

# --- Validação Global: Trim em Strings ---
@event.listens_for(Mapper, "before_insert")
@event.listens_for(Mapper, "before_update")
def trim_strings(mapper, connection, target):
    """Remove espaços em branco no início e fim de todos os campos de texto."""
    for column in mapper.columns:
        if isinstance(column.type, (String, Text)):
            value = getattr(target, column.key)
            if isinstance(value, str):
                setattr(target, column.key, value.strip())

# --- Modelos (Tabelas) ---

class Empresa(Base):
    """
    Modelo do Tenant (Empresa). Esta é a tabela central.
    """
    __tablename__ = "empresas"
    __label__ = "Dados da Empresa"
    __label_plural__ = "Empresas"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    cnpj = Column(String(18), unique=True, nullable=False, index=True, 
                  info={'format_mask': 'cnpj', 'tab': 'Dados Gerais', 'label': 'CNPJ', 'placeholder': '00.000.000/0000-00'})
    razao = Column(String, nullable=False, index=True,
                   info={'tab': 'Dados Gerais', 'label': 'Razão Social', 'placeholder': 'Ex: Minha Empresa Ltda'})
    fantasia = Column(String, 
                      info={'tab': 'Dados Gerais', 'label': 'Nome Fantasia', 'placeholder': 'Ex: Loja do Centro'})
    url_logo = Column(String, 
                      info={'tab': 'Dados Gerais', 'label': 'URL do Logo', 'placeholder': 'https://...'})
    inscricao_estadual = Column(String, 
                                info={'tab': 'Dados Gerais', 'label': 'Inscrição Estadual', 'placeholder': 'Ex: 123.456.789.111 (ou vazio para Isento)'})
    inscricao_municipal = Column(String, 
                                info={'tab': 'Dados Gerais', 'label': 'Inscrição Municipal', 'placeholder': 'Ex: 123456'})
    telefone = Column(String, 
                      info={'format_mask': 'phone', 'tab': 'Dados Gerais', 'label': 'Telefone', 'placeholder': '(00) 0000-0000'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais', 'label': 'Situação', 'placeholder': ''})
    cor_sidebar = Column(String, default="#1f2937", 
                         info={'tab': 'Dados Gerais', 'label': 'Cor da Sidebar', 'placeholder': '#1f2937', 'type': 'color'})
    
    # --- Aba: Endereço ---
    cep = Column(String(9), nullable=False, 
                 info={'format_mask': 'cep', 'tab': 'Endereço', 'label': 'CEP', 'placeholder': '00000-000'})
    estado = Column(SafeStrEnum(EstadoEnum), nullable=False,
                    info={'tab': 'Endereço', 'label': 'Estado (UF)', 'placeholder': 'Selecione...'})
    cidade = Column(String, 
                    info={'tab': 'Endereço', 'label': 'Cidade', 'placeholder': 'Ex: São Paulo'})
    cidade_ibge = Column(String(7), 
                    info={'tab': 'Endereço', 'label': 'Código IBGE', 'placeholder': 'Ex: 3550308'})
    bairro = Column(String, 
                    info={'tab': 'Endereço', 'label': 'Bairro', 'placeholder': 'Ex: Centro'})
    logradouro = Column(String, 
                        info={'tab': 'Endereço', 'label': 'Logradouro', 'placeholder': 'Rua, Avenida, etc.'})
    numero = Column(String, 
                    info={'tab': 'Endereço', 'label': 'Número', 'placeholder': '123'})
    complemento = Column(String, 
                         info={'tab': 'Endereço', 'label': 'Complemento', 'placeholder': 'Apto 101, Bloco B'})
    
    # --- Aba: Fiscal    ---
    cnae = Column(String,
                  info={'tab': 'Fiscal', 'label': 'CNAE', 'placeholder': 'Código CNAE principal'})
    crt = Column(IntEnum(EmpresaCRTEnum), nullable=False, default=EmpresaCRTEnum.simples_nacional, 
                 info={
                     'tab': 'Fiscal', 
                     'label': 'Regime Tributário (CRT)', 
                     'placeholder': 'Selecione...',
                     'component': 'select',
                     'options': [
                         {'label': 'Simples Nacional', 'value': 1}, 
                         {'label': 'Simples Nacional (Excesso Sublimite)', 'value': 2},
                         {'label': 'Lucro Presumido', 'value': 3}, 
                         {'label': 'Lucro Real', 'value': 4}
                     ]
                 })
    certificado_arquivo = Column(LargeBinary, info={'tab': 'Fiscal', 'label': 'Certificado Digital (.pfx)', 'placeholder': '', 'filename_field': 'certificado_nome_arquivo'}) # O arquivo .pfx em bytes
    certificado_senha = Column(EncryptedString, info={'tab': 'Fiscal', 'ui_type': 'password', 'label': 'Senha do Certificado', 'placeholder': 'Senha do arquivo .pfx'})
    nfe_serie = Column(Integer, default=1, info={'tab': 'Fiscal', 'label': 'Série NFe', 'placeholder': '1'})
    nfe_numero_sequencial = Column(Integer, default=1, info={'tab': 'Fiscal', 'label': 'Próxima NFe', 'placeholder': '1', 'read_only': True})
    nfe_ultimo_nsu = Column(String, default="0", info={'tab': 'Fiscal', 'label': 'Último NSU SEFAZ', 'placeholder': '0', 'read_only': True})
    nfce_serie = Column(Integer, default=1, info={'tab': 'Fiscal', 'label': 'Série NFCe', 'placeholder': '1'})
    nfce_numero_sequencial = Column(Integer, default=1, info={'tab': 'Fiscal', 'label': 'Próxima NFCe', 'placeholder': '1', 'read_only': True})
    ambiente_sefaz = Column(IntEnum(EmpresaAmbienteSefazEnum), nullable=False, default=EmpresaAmbienteSefazEnum.homologacao, info={
        'tab': 'Fiscal', 
        'label': 'Ambiente SEFAZ', 
        'component': 'select',
        'placeholder': 'Selecione...',
        'options': [{'label': 'Produção', 'value': 1}, {'label': 'Homologação', 'value': 2}]
    })
    
    id_classificacao_contabil_padrao = Column(Integer, ForeignKey("classificacao_contabil.id"), nullable=True, 
                                              info={'tab': 'Fiscal', 'label': 'Plano de Contas Padrão (Vendas)', 'placeholder': 'Selecione...', 'foreign_key_model': 'classificacao_contabil', 'foreign_key_label_field': 'descricao'})
    id_classificacao_contabil_cancelamento = Column(Integer, ForeignKey("classificacao_contabil.id"), nullable=True, 
                                              info={'tab': 'Fiscal', 'label': 'Plano de Contas (Cancelamento de Venda)', 'placeholder': 'Selecione...', 'foreign_key_model': 'classificacao_contabil', 'foreign_key_label_field': 'descricao'})
    validade_orcamento = Column(Integer, default=7, 
                                info={'tab': 'Fiscal', 'label': 'Validade do Orçamento (Dias)', 'placeholder': '7'})
    certificado_nome_arquivo = Column(String, info={'tab': 'Fiscal', 'label': 'Nome do Arquivo', 'type': 'hidden'})

    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    @hybrid_property
    def id_empresa(self):
        return self.id

    @id_empresa.expression
    def id_empresa(cls):
        return cls.id

    # Relacionamentos (One-to-Many para todos os outros modelos)
    usuarios = relationship("Usuario", back_populates="empresa")
    cadastros = relationship("Cadastro", back_populates="empresa")
    produtos = relationship("Produto", back_populates="empresa")
    embalagens = relationship("Embalagem", back_populates="empresa")
    contas = relationship("Conta", back_populates="empresa")
    estoques = relationship("Estoque", back_populates="empresa")
    pedidos = relationship("Pedido", back_populates="empresa")
    regras_tributarias = relationship("Tributacao", back_populates="empresa")
    classificacoes_contabeis = relationship("ClassificacaoContabil", back_populates="empresa", foreign_keys="ClassificacaoContabil.id_empresa")
    perfil = relationship("Perfil", back_populates="empresa")
    classificacao_contabil_padrao_rel = relationship("ClassificacaoContabil", foreign_keys=[id_classificacao_contabil_padrao])
    classificacao_contabil_cancelamento_rel = relationship("ClassificacaoContabil", foreign_keys=[id_classificacao_contabil_cancelamento])


class Perfil(Base):
    """
    Modelo de Perfis de Acesso (RBAC).
    Controla acesso a páginas, subpáginas, botões e colunas visíveis.
    """
    __tablename__ = "perfil"
    __label__ = "Perfil de Acesso"
    __label_plural__ = "Perfis de Acesso"

    id = Column(Integer, primary_key=True, index=True)
    
    nome = Column(String, nullable=False, 
                  info={'tab': 'Geral', 'label': 'Nome do Perfil', 'placeholder': 'Ex: Gerente de Vendas'})
    descricao = Column(String, 
                       info={'tab': 'Geral', 'label': 'Descrição', 'placeholder': 'Descrição das atribuições'})
    
    # Armazena a configuração de acesso (JSON):
    # Ex: { "pedidos": { "acesso": true, "subpaginas": ["embalagem"], "acoes": ["editar"], "colunas": ["id", "total"] } }
    permissoes = Column(JSON, default={}, info={
        'tab': 'Permissões', 
        'label': 'Matriz de Acesso', 
        'component': 'permissions_builder', # Componente visual no frontend
        'placeholder': '',
        'col_span': 2 # Ocupa duas colunas no formulário
    })
    
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Geral', 'label': 'Ativo?', 'placeholder': ''})

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    empresa = relationship("Empresa", back_populates="perfil")
    usuarios = relationship("Usuario", back_populates="perfil_rel")


class Usuario(Base):
    """
    Modelo de Usuário do sistema.
    """
    __tablename__ = "usuarios"
    __label__ = "Usuário"
    __label_plural__ = "Usuários"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    nome = Column(String, nullable=False, 
                  info={'tab': 'Dados Gerais', 'label': 'Nome Completo', 'placeholder': 'Ex: João da Silva'})
    email = Column(String, unique=True, index=True, nullable=False, 
                   info={'tab': 'Dados Gerais', 'label': 'E-mail', 'placeholder': 'usuario@empresa.com'})
    senha = Column(String, nullable=False, 
                   info={'tab': 'Dados Gerais', 'label': 'Senha', 'placeholder': 'Mínimo 8 caracteres'}) # Hashed password

    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais', 'label': 'Ativo?', 'placeholder': ''})

    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chave estrangeira para o multi-tenancy
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    # Novo campo para vínculo com a tabela de Perfis
    id_perfil = Column(Integer, ForeignKey("perfil.id"), nullable=True, 
                       info={'tab': 'Dados Gerais', 'label': 'Perfil de Acesso', 'placeholder': 'Selecione...', 'foreign_key_model': 'perfil', 'foreign_key_label_field': 'nome'})
    
    # Relacionamento (Many-to-One)
    empresa = relationship("Empresa", back_populates="usuarios")
    perfil_rel = relationship("Perfil", back_populates="usuarios")


class Cadastro(Base):
    """
    Modelo de Cadastros (Super-modelo).
    Pode ser Cliente, Fornecedor, Transportadora, Vendedor.
    """
    __tablename__ = "cadastros"
    __label__ = "Cadastro (Pessoas)"
    __label_plural__ = "Clientes e Fornecedores"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    cpf_cnpj = Column(String(18), nullable=False, index=True, 
                      info={'format_mask': 'cnpj_cpf', 'tab': 'Dados Gerais', 'label': 'CPF/CNPJ', 'placeholder': 'Digite apenas números'})
    nome_razao = Column(String, nullable=False, index=True, 
                        info={'tab': 'Dados Gerais', 'label': 'Nome / Razão Social', 'placeholder': 'Ex: João Silva ou Empresa X Ltda'})
    fantasia = Column(String, 
                      info={'tab': 'Dados Gerais', 'label': 'Nome Fantasia', 'placeholder': 'Ex: Mercado Central'})
    tipo_pessoa = Column(SQLAlchemyEnum(CadastroTipoPessoaEnum, native_enum=False), nullable=False, default=CadastroTipoPessoaEnum.fisica, 
                         info={'tab': 'Dados Gerais', 'label': 'Tipo de Pessoa', 'placeholder': 'Selecione...'})
    tipo_cadastro = Column(SQLAlchemyEnum(CadastroTipoCadastroEnum, native_enum=False), nullable=False, default=CadastroTipoCadastroEnum.cliente, 
                           info={'tab': 'Dados Gerais', 'label': 'Tipo de Cadastro', 'placeholder': 'Selecione...'})
    
    # Fiscal (ainda em Dados Gerais)
    indicador_ie = Column( SQLAlchemyEnum( CadastroIndicadorIEEnum, native_enum=False, values_callable=lambda x: [e.value for e in x] ),
        nullable=True, default=CadastroIndicadorIEEnum.nao_contribuinte,
        info={'tab': 'Dados Gerais', 'label': 'Indicador da IE', 'placeholder': 'Selecione...'} )
    inscricao_estadual = Column(String, 
                                info={'tab': 'Dados Gerais', 'label': 'Inscrição Estadual', 'placeholder': 'Ex: 123.456.789.111 (ou vazio para ISENTO)'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais', 'label': 'Ativo?', 'placeholder': ''})

    # --- Aba: Contato ---
    email = Column(String, index=True, 
                   info={'tab': 'Contato', 'label': 'E-mail de Contato', 'placeholder': 'Ex: financeiro@cliente.com'})
    telefone = Column(String, 
                      info={'format_mask': 'phone', 'tab': 'Contato', 'label': 'Telefone Fixo', 'placeholder': '(00) 0000-0000'}) 
    celular = Column(String, 
                     info={'format_mask': 'phone', 'tab': 'Contato', 'label': 'Celular / WhatsApp', 'placeholder': '(00) 90000-0000'})
    
    # --- Aba: Endereço ---
    cep = Column(String(9), nullable=False, 
                 info={'format_mask': 'cep', 'tab': 'Endereço', 'label': 'CEP', 'placeholder': '00000-000'})
    estado = Column(SafeStrEnum(EstadoEnum), 
                    info={'tab': 'Endereço', 'label': 'Estado (UF)', 'placeholder': 'Selecione...'})
    cidade = Column(String, 
                    info={'tab': 'Endereço', 'label': 'Cidade', 'placeholder': 'Nome da cidade'})
    cidade_ibge = Column(String(7), 
                    info={'tab': 'Endereço', 'label': 'Código IBGE', 'placeholder': 'Ex: 3550308'})
    bairro = Column(String, 
                    info={'tab': 'Endereço', 'label': 'Bairro', 'placeholder': 'Nome do bairro'})
    logradouro = Column(String, 
                        info={'tab': 'Endereço', 'label': 'Logradouro', 'placeholder': 'Rua, Avenida, etc.'})
    numero = Column(String, 
                    info={'tab': 'Endereço', 'label': 'Número', 'placeholder': '123'})
    complemento = Column(String, 
                         info={'tab': 'Endereço', 'label': 'Complemento', 'placeholder': 'Apto 101, Bloco B'})
    
    delivery_method_id_intelipost = Column(String, nullable=True, info={'tab': 'Integrações', 'label': 'ID Método Entrega (Intelipost)'})
    
    # --- Campos Internos (sem aba) ---
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chave estrangeira para o multi-tenancy
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    # Relacionamento (Many-to-One)
    empresa = relationship("Empresa", back_populates="cadastros")
    
    # Relacionamentos (One-to-Many) para Pedidos
    pedidos_como_cliente = relationship("Pedido", back_populates="cliente", foreign_keys="Pedido.id_cliente")
    pedidos_como_vendedor = relationship("Pedido", back_populates="vendedor", foreign_keys="Pedido.id_vendedor")
    pedidos_como_transportadora = relationship("Pedido", back_populates="transportadora", foreign_keys="Pedido.id_transportadora")
    
    # Relacionamentos (One-to-Many) para outros modelos
    produtos_como_fornecedor = relationship("Produto", back_populates="fornecedor")
    contas_como_fornecedor = relationship("Conta", back_populates="fornecedor")


class Embalagem(Base):
    """
    Modelo de Embalagens.
    """
    __tablename__ = "embalagens"
    __label__ = "Embalagem"
    __label_plural__ = "Embalagens"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    descricao = Column(String, nullable=False, 
                       info={'tab': 'Dados Gerais', 'label': 'Descrição da Embalagem', 'placeholder': 'Ex: Caixa Padrão Correios'})
    regras = Column(JSON,
                    info={'tab': 'Regras de Empacotamento', 'label': 'Regras', 'placeholder': '', 'col_span': 2}) # JSON para flexibilidade
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais', 'label': 'Ativo?', 'placeholder': ''})

    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chave estrangeira para o multi-tenancy
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    # Relacionamento (Many-to-One)
    empresa = relationship("Empresa", back_populates="embalagens")
    
    # Relacionamento (One-to-Many)
    produtos = relationship("Produto", back_populates="embalagem")


class Produto(Base):
    """
    Modelo de Produtos.
    """
    __tablename__ = "produtos"
    __label__ = "Produto"
    __label_plural__ = "Produtos"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    sku = Column(String, nullable=False, unique=True, index=True, 
                 info={'tab': 'Dados Gerais', 'label': 'SKU', 'placeholder': 'Código único do produto'})
    gtin = Column(String, index=True, 
                  info={'tab': 'Dados Gerais', 'label': 'GTIN / EAN', 'placeholder': 'Ex: 7890000000000'})
    variacoes = Column(JSON, default=[], info={'tab': 'Dados Gerais', 'label': 'Variações (SKUs Fornecedores)', 'placeholder': 'Adicione SKUs externos'})
    descricao = Column(String, nullable=False, index=True, 
                       info={'tab': 'Dados Gerais', 'label': 'Descrição do Produto', 'placeholder': 'Ex: Camiseta Algodão Azul G'})
    unidade = Column(SQLAlchemyEnum(ProdutoUnidadeEnum, native_enum=False), default=ProdutoUnidadeEnum.un, 
                     info={'tab': 'Dados Gerais', 'label': 'Unidade de Medida', 'placeholder': 'Selecione...'})
    tipo_produto = Column(SQLAlchemyEnum(ProdutoTipoEnum, native_enum=False), default=ProdutoTipoEnum.mercadoria_revenda, 
                          info={'tab': 'Dados Gerais', 'label': 'Tipo do Item', 'placeholder': 'Selecione...'})
    url_imagem = Column(String, 
                        info={'tab': 'Dados Gerais', 'label': 'URL da Imagem', 'placeholder': 'https://...'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais', 'label': 'Ativo?', 'placeholder': ''})
    id_embalagem = Column(Integer, ForeignKey("embalagens.id"), nullable=True, 
                          info={'tab': 'Dados Gerais', 'label': 'Embalagem Padrão', 'placeholder': 'Selecione...'})
    id_fornecedor = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                           info={'tab': 'Dados Gerais', 'label': 'Fornecedor Principal', 'placeholder': 'Selecione...'}) # Referencia Cadastro (tipo_cadastro=fornecedor)

    # --- Aba: Categorização ---
    grupo = Column(String, 
                   info={'tab': 'Categorização', 'component': 'creatable_select', 'label': 'Grupo / Categoria', 'placeholder': 'Ex: Eletrônicos'})
    subgrupo1 = Column(String, 
                       info={'tab': 'Categorização', 'component': 'creatable_select', 'label': 'Subgrupo 1', 'placeholder': 'Ex: Celulares'})
    subgrupo2 = Column(String, 
                       info={'tab': 'Categorização', 'component': 'creatable_select', 'label': 'Subgrupo 2', 'placeholder': 'Ex: Acessórios'})
    subgrupo3 = Column(String, 
                       info={'tab': 'Categorização', 'label': 'Subgrupo 3', 'placeholder': ''})
    subgrupo4 = Column(String, 
                       info={'tab': 'Categorização', 'label': 'Subgrupo 4', 'placeholder': ''})
    subgrupo5 = Column(String, 
                       info={'tab': 'Categorização', 'label': 'Subgrupo 5', 'placeholder': ''})
    
    # --- Aba: Fiscal ---
    classificacao_fiscal = Column(String, 
                                  info={'tab': 'Fiscal', 'label': 'Classificação / Gênero', 'placeholder': 'Código interno ou Gênero'})
    origem = Column(SQLAlchemyEnum(ProdutoOrigemEnum, native_enum=False), default=ProdutoOrigemEnum.nacional, 
                    info={'tab': 'Fiscal', 'label': 'Origem da Mercadoria', 'placeholder': 'Selecione...'})
    ncm = Column(String(8), 
                 info={'format_mask': 'ncm', 'tab': 'Fiscal', 'label': 'NCM', 'placeholder': 'Ex: 6109.10.00'})
    cest = Column(String(7), info={'tab': 'Fiscal', 'label': 'CEST', 'placeholder': 'Ex: 28.038.00'}) # Código Especificador da Substituição Tributária
    anp = Column(String, info={'tab': 'Fiscal', 'label': 'Código ANP', 'placeholder': 'Para combustíveis/lubrificantes'}) # Para combustíveis/lubrificantes
    escala_relevante = Column(Boolean, default=True, info={'tab': 'Fiscal', 'label': 'Escala Relevante?', 'placeholder': ''})
    cnpj_fabricante = Column(String, info={'tab': 'Fiscal', 'label': 'CNPJ Fabricante', 'placeholder': ''}) # Para rastreabilidade
    ipi_aliquota = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Fiscal', 'format_mask': 'percent:2', 'label': 'Alíquota IPI', 'placeholder': '0,00'})
    
    # --- Aba: Valores e Dimensões ---
    preco = Column(Currency(), 
                   info={'tab': 'Valores e Dimensões', 'label': 'Preço de Venda', 'placeholder': '0,00'}) 
    custo = Column(Currency(), 
                   info={'tab': 'Valores e Dimensões', 'label': 'Preço de Custo', 'placeholder': '0,00'})
    estoque_negativo = Column(Boolean, default=False, 
                              info={'tab': 'Valores e Dimensões', 'label': 'Permitir Estoque Negativo?', 'placeholder': ''})
    
    peso = Column(Numeric(10, 3), 
                  info={'format_mask': 'decimal:3', 'tab': 'Valores e Dimensões', 'label': 'Peso Bruto (kg)', 'placeholder': '0,000'})
    altura = Column(Numeric(10, 2), 
                    info={'tab': 'Valores e Dimensões', 'label': 'Altura (cm)', 'placeholder': '0,00'})
    largura = Column(Numeric(10, 2), 
                     info={'tab': 'Valores e Dimensões', 'label': 'Largura (cm)', 'placeholder': '0,00'})
    comprimento = Column(Numeric(10, 2), 
                         info={'tab': 'Valores e Dimensões', 'label': 'Comprimento (cm)', 'placeholder': '0,00'})
    
    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chaves Estrangeiras (id_empresa é interno)
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    # Relacionamentos (Many-to-One)
    empresa = relationship("Empresa", back_populates="produtos")
    embalagem = relationship("Embalagem", back_populates="produtos")
    fornecedor = relationship("Cadastro", back_populates="produtos_como_fornecedor", foreign_keys=[id_fornecedor])
    
    # Relacionamento (One-to-Many)
    estoques = relationship("Estoque", back_populates="produto")


class Conta(Base):
    """
    Modelo de Contas a Pagar/Receber.
    """
    __tablename__ = "contas"
    __label__ = "Lançamento Financeiro"
    __label_plural__ = "Contas a Pagar e Receber"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Principal ---
    tipo_conta = Column(SQLAlchemyEnum(ContaTipoEnum, native_enum=False), nullable=False, default=ContaTipoEnum.a_receber, 
                        info={'tab': 'Principal', 'label': 'Tipo de Lançamento', 'placeholder': 'Selecione...'})
    situacao = Column(SQLAlchemyEnum(ContaSituacaoEnum, native_enum=False), nullable=False, default=ContaSituacaoEnum.em_aberto, 
                      info={'tab': 'Principal', 'label': 'Situação', 'placeholder': 'Selecione...'})
    descricao = Column(String, 
                       info={'tab': 'Principal', 'label': 'Descrição', 'placeholder': 'Ex: Conta de Luz Referente Mês 05'})
    numero_conta = Column(String, 
                          info={'tab': 'Principal', 'label': 'Número do Documento', 'placeholder': ''})
    id_fornecedor = Column(Integer, ForeignKey("cadastros.id"), nullable=False, 
                           info={'tab': 'Principal', 'label': 'Fornecedor / Cliente', 'placeholder': 'Selecione...'}) # Ref. Cadastro (tipo_cadastro=fornecedor)

    # --- Aba: Financeiro ---
    pagamento = Column(SQLAlchemyEnum(FiscalPagamentoEnum, native_enum=False), 
                 info={'tab': 'Financeiro', 'label': 'Forma de Pagamento', 'placeholder': 'Selecione...'})
    valor = Column(Currency(), nullable=False, 
                   info={'tab': 'Financeiro', 'label': 'Valor Total', 'placeholder': '0,00'})
    id_classificacao_contabil = Column(Integer, ForeignKey("classificacao_contabil.id"), nullable=False,
                                       info={'tab': 'Financeiro', 'label': 'Plano de Contas', 'placeholder': 'Selecione...'})
    caixa_destino_origem = Column(String, 
                 info={'tab': 'Financeiro', 'component': 'creatable_select', 'label': 'Conta Bancária / Caixa', 'placeholder': 'Ex: Caixa Geral ou Banco Itaú'})
    
    
    # --- Aba: Datas ---
    data_emissao = Column(Date, default=func.current_date(),
                          info={'tab': 'Datas', 'label': 'Data de Emissão', 'placeholder': ''})
    data_vencimento = Column(Date, 
                             info={'tab': 'Datas', 'label': 'Data de Vencimento', 'placeholder': ''})
    data_baixa = Column(Date, nullable=True, 
                        info={'tab': 'Datas', 'label': 'Data de Pagamento/Baixa', 'placeholder': ''})
    
    # --- Aba: Outros ---
    observacoes = Column(Text, 
                         info={'tab': 'Outros', 'label': 'Observações', 'placeholder': ''})

    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chaves Estrangeiras
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    # Relacionamentos (Many-to-One)
    empresa = relationship("Empresa", back_populates="contas")
    fornecedor = relationship("Cadastro", back_populates="contas_como_fornecedor", foreign_keys=[id_fornecedor])
    classificacao_contabil = relationship("ClassificacaoContabil")


class Estoque(Base):
    """
    Modelo de Estoque (Lotes).
    """
    __tablename__ = "estoque"
    __label__ = "Movimentação de Estoque"
    __label_plural__ = "Movimentações de Estoque"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Principal ---
    id_produto = Column(Integer, ForeignKey("produtos.id"), nullable=False, 
                        info={'tab': 'Principal', 'label': 'Produto', 'placeholder': 'Selecione...'})
    lote = Column(String, 
                  info={'tab': 'Principal', 'label': 'Lote / Série', 'placeholder': ''})
    quantidade = Column(Integer, nullable=False, 
                        info={'tab': 'Principal', 'label': 'Quantidade', 'placeholder': '0'})
    situacao = Column(String, nullable=False, default="Entrada", 
                      info={
                          'tab': 'Principal', 
                          'label': 'Tipo de Movimentação', 
                          'placeholder': 'Selecione...',
                          'component': 'select',
                          'options': [
                              {'label': 'Entrada', 'value': 'Entrada'},
                              {'label': 'Saída', 'value': 'Saída'},
                              {'label': 'Inventário', 'value': 'Inventário'},
                          ]
                      })
    observacoes = Column(Text, 
                         info={'tab': 'Principal', 'label': 'Observações', 'placeholder': 'Ex: Retirada para pedido 123, Adição de estoque referente a nota 456...'})

    # --- Aba: Localização ---
    deposito = Column(String, 
                      info={'tab': 'Localização', 'component': 'creatable_select', 'label': 'Depósito', 'placeholder': 'Ex: Geral'})
    rua = Column(String, 
                 info={'tab': 'Localização', 'component': 'creatable_select', 'label': 'Rua / Corredor', 'placeholder': ''})
    nivel = Column(String, 
                   info={'tab': 'Localização', 'component': 'creatable_select', 'label': 'Nível / Prateleira', 'placeholder': ''})
    cor = Column(String, 
                 info={'tab': 'Localização', 'component': 'creatable_select', 'label': 'Cor / Variante', 'placeholder': ''}) # Pode ser usado para variante
    
    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chaves Estrangeiras
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    # Relacionamentos (Many-to-One)
    empresa = relationship("Empresa", back_populates="estoques")
    produto = relationship("Produto", back_populates="estoques")


class Pedido(Base):
    """
    Modelo de Pedidos de Venda.
    """
    __tablename__ = "pedidos"
    __label__ = "Pedido de Venda"
    __label_plural__ = "Pedidos de Venda"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Principal ---
    id_cliente = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                        info={'tab': 'Principal', 'label': 'Cliente', 'placeholder': 'Busque o cliente...'}) # Ref. Cadastro (tipo_cadastro=cliente)
    id_vendedor = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                         info={'tab': 'Principal', 'label': 'Vendedor', 'placeholder': 'Busque o vendedor...'}) # Ref. Cadastro (tipo_cadastro=vendedor)
    origem_venda = Column(String, 
                          info={'tab': 'Principal', 'component': 'creatable_select', 'label': 'Canal de Venda', 'placeholder': 'Ex: Site, Balcão'})
    situacao = Column(SQLAlchemyEnum(PedidoSituacaoEnum, native_enum=True), nullable=False, default=PedidoSituacaoEnum.orcamento, 
                      info={'tab': 'Principal', 'label': 'Situação do Pedido', 'placeholder': 'Selecione...'})
    
    # --- Aba: Datas e Prazos ---
    data_orcamento = Column(Date, default=func.current_date(), 
                          info={'tab': 'Datas e Prazos', 'label': 'Data do Orçamento', 'placeholder': ''})
    data_validade = Column(Date, 
                           info={'tab': 'Datas e Prazos', 'label': 'Validade do Orçamento', 'placeholder': ''})
    data_pedido = Column(Date, 
                         info={'tab': 'Datas e Prazos', 'label': 'Data do Pedido', 'placeholder': ''})
    data_entrega = Column(Date, 
                              info={'tab': 'Datas e Prazos', 'label': 'Data de Entrega Prevista', 'placeholder': ''})
    data_finalizacao = Column(Date, 
                              info={'tab': 'Datas e Prazos', 'label': 'Data de Finalização', 'placeholder': ''})
    data_despacho = Column(Date,
                           info={'tab': 'Datas e Prazos', 'label': 'Data de Despacho', 'placeholder': ''})
    ordem_finalizacao = Column(Numeric(5, 1), 
                               info={'tab': 'Datas e Prazos', 'label': 'Ordem de Finalização', 'placeholder': ''})
    data_nf = Column(Date, info={'tab': 'Datas e Prazos', 'label': 'Data NFe', 'placeholder': ''})
    
    # --- Aba: Itens e Observações ---
    itens = Column(JSON, 
                   info={'tab': 'Itens', 'label': 'Itens do Pedido', 'placeholder': '', 'col_span': 2}) # Armazena os itens do pedido como JSON

    # --- Aba: Endereço de Entrega ---
    endereco_cep = Column(String(9), info={'format_mask': 'cep', 'tab': 'Endereço de Entrega', 'label': 'CEP', 'placeholder': '00000-000'})
    endereco_estado = Column(SafeStrEnum(EstadoEnum), info={'tab': 'Endereço de Entrega', 'label': 'Estado (UF)', 'placeholder': 'Selecione...'})
    endereco_cidade = Column(String, info={'tab': 'Endereço de Entrega', 'label': 'Cidade', 'placeholder': 'Ex: São Paulo'})
    endereco_bairro = Column(String, info={'tab': 'Endereço de Entrega', 'label': 'Bairro', 'placeholder': 'Ex: Centro'})
    endereco_logradouro = Column(String, info={'tab': 'Endereço de Entrega', 'label': 'Logradouro', 'placeholder': 'Rua, Avenida, etc.'})
    endereco_numero = Column(String, info={'tab': 'Endereço de Entrega', 'label': 'Número', 'placeholder': '123'})
    endereco_complemento = Column(String, info={'tab': 'Endereço de Entrega', 'label': 'Complemento', 'placeholder': 'Apto 101, Bloco B'})

    # --- Aba: Frete ---
    id_transportadora = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                               info={'tab': 'Frete', 'label': 'Transportadora', 'placeholder': 'Busque a transportadora...'}) # Ref. Cadastro (tipo_cadastro=transportadora)
    modalidade_frete = Column(SQLAlchemyEnum(PedidoModalidadeFreteEnum, native_enum=False, values_callable=lambda x: [e.value for e in x]), default=PedidoModalidadeFreteEnum.cif, 
                              info={'tab': 'Frete', 'label': 'Modalidade de Frete', 'placeholder': 'Selecione...'})
    valor_frete = Column(Currency(), 
                         info={'tab': 'Frete', 'label': 'Valor do Frete', 'placeholder': '0,00'})
    ipi_frete = Column(Currency(), default=0, info={'tab': 'Frete', 'label': 'Valor IPI Frete', 'placeholder': '0,00'})
    total_frete = Column(Currency(), info={'tab': 'Frete', 'label': 'Total Frete (c/ IPI)', 'placeholder': '0,00'})
    
    

    # --- Aba: Frete (Veículo) ---
    veiculo_placa = Column(String, info={'tab': 'Frete', 'label': 'Placa do Veículo', 'placeholder': 'ABC-1234', 'visible': False})
    veiculo_uf = Column(SafeStrEnum(EstadoEnum), info={'tab': 'Frete', 'label': 'UF do Veículo', 'placeholder': 'UF', 'visible': False})
    veiculo_antt = Column(String, info={'tab': 'Frete', 'label': 'RNTC (ANTT)', 'placeholder': '', 'visible': False})

    # --- Aba: Frete (Volumes) ---
    volumes_quantidade = Column(Integer, info={'tab': 'Frete', 'label': 'Qtd. Volumes', 'placeholder': '0'})
    volumes_especie = Column(String, default="VOLUMES", info={'tab': 'Frete', 'label': 'Espécie', 'placeholder': 'Ex: CAIXA'})
    volumes_marca = Column(String, info={'tab': 'Frete', 'label': 'Marca', 'placeholder': '', 'visible': False})
    volumes_numeracao = Column(String, info={'tab': 'Frete', 'label': 'Numeração', 'placeholder': '', 'visible': False})
    volumes_peso_bruto = Column(Numeric(10, 3), info={'tab': 'Frete', 'format_mask': 'decimal:3', 'label': 'Peso Bruto (kg)', 'placeholder': '0,000'})
    volumes_peso_liquido = Column(Numeric(10, 3), info={'tab': 'Frete', 'format_mask': 'decimal:3', 'label': 'Peso Líquido (kg)', 'placeholder': '0,000'})

    # --- Aba: Valores ---
    total = Column(Currency(), 
                   info={'tab': 'Valores', 'label': 'Valor Total', 'placeholder': '0,00'})
    desconto = Column(Currency(), 
                      info={'tab': 'Valores', 'label': 'Desconto (Valor)', 'placeholder': '0,00'})
    total_desconto = Column(Currency(), 
                            info={'tab': 'Valores', 'label': 'Total com Descontos', 'placeholder': '0,00'})
    pagamento = Column(SQLAlchemyEnum(FiscalPagamentoEnum, native_enum=False), 
                       info={'tab': 'Valores', 'label': 'Forma de Pagamento', 'placeholder': 'Selecione...'})
    pagamento_descricao = Column(String, nullable=True,
                                 info={'tab': 'Valores', 'label': 'Descrição do Pagamento (Outros)', 'placeholder': 'Ex: Saldo em Conta, Vale-Presente'})
    
    caixa_destino_origem = Column(String, 
                 info={'tab': 'Valores', 'component': 'creatable_select', 'label': 'Conta Bancária / Caixa', 'placeholder': 'Ex: Caixa Geral ou Banco Itaú'})

    # --- Aba: Fiscal ---
    tipo_operacao = Column(SQLAlchemyEnum(RegraTipoOperacaoEnum, native_enum=False), default=RegraTipoOperacaoEnum.venda_mercadoria,
                           info={'tab': 'Fiscal', 'label': 'Tipo de Operação', 'placeholder': 'Selecione...'})
    numero_nf = Column(String, info={'tab': 'Fiscal', 'label': 'Número NFe', 'placeholder': ''})
    chave_acesso = Column(String(44), index=True, info={'tab': 'Fiscal', 'label': 'Chave de Acesso NFe', 'placeholder': ''})
    chave_nfe_referencia = Column(String(44), info={'tab': 'Fiscal', 'label': 'Chave NFe Referenciada', 'placeholder': ''})
    protocolo_autorizacao = Column(String, info={'tab': 'Fiscal', 'label': 'Protocolo', 'placeholder': ''})
    status_sefaz = Column(String, info={'tab': 'Fiscal', 'label': 'Status SEFAZ', 'placeholder': ''}) # Ex: 100 (Autorizada), 101 (Cancelada)
    xml_autorizado = Column(Text, info={'tab': 'Fiscal', 'label': 'XML Autorizado', 'component': 'file', 'placeholder': ''}) # XML completo assinado e protocolado
    pdf_danfe = Column(Text, info={'tab': 'Fiscal', 'label': 'PDF DANFE', 'component': 'file', 'placeholder': ''}) # Base64 do PDF (opcional, ou gera na hora)
    pdf_cce = Column(Text, info={'tab': 'Fiscal', 'label': 'PDF CC-e', 'component': 'file', 'placeholder': ''}) # Base64 do PDF da Carta de Correção
    indicador_presenca = Column(IntEnum(PedidoIndicadorPresencaEnum), default=PedidoIndicadorPresencaEnum.internet,
                                info={
                                    'tab': 'Fiscal', 
                                    'label': 'Indicador de Presença', 
                                    'placeholder': 'Selecione...',
                                    'component': 'select',
                                    'options': [
                                        {'label': '0 - Não se aplica', 'value': 0},
                                        {'label': '1 - Operação presencial', 'value': 1},
                                        {'label': '2 - Operação não presencial, pela Internet', 'value': 2},
                                        {'label': '3 - Operação não presencial, Teleatendimento', 'value': 3},
                                        {'label': '4 - NFC-e em operação com entrega a domicílio', 'value': 4},
                                        {'label': '5 - Operação presencial, fora do estabelecimento', 'value': 5},
                                        {'label': '9 - Operação não presencial, outros', 'value': 9}
                                    ]
                                })
    

    # URL pública ou caminho do arquivo se preferir não salvar no banco
    modelo_fiscal = Column(Integer, info={
        'tab': 'Fiscal', 
        'label': 'Modelo Fiscal', 
        'placeholder': 'Selecione...',
        'component': 'select',
        'options': [
            {'label': '55 - Nota Fiscal Eletrônica (NF-e)', 'value': 55},
            {'label': '65 - Nota Fiscal de Consumidor Eletrônica (NFC-e)', 'value': 65}
        ]
    }, default=55) # 55=NFe, 65=NFCe

    # Campos Integração Intelipost
    delivery_method_id_intelipost = Column(String, nullable=True, info={'tab': 'Integrações', 'label': 'ID Método Entrega (Intelipost)'})
    quote_id = Column(String, nullable=True, info={'tab': 'Integrações', 'label': 'ID Cotação (Intelipost)'})
    intelipost_id = Column(String, nullable=True, info={'tab': 'Integrações', 'label': 'ID Ordem Envio (Intelipost)'})
    
    # Campos de Status de Integração
    meli_xml_enviado = Column(Boolean, default=False, info={'tab': 'Integrações', 'label': 'XML enviado ML?'})
    intelipost_criado = Column(Boolean, default=False, info={'tab': 'Integrações', 'label': 'Criado Intelipost?'})
    email_enviado = Column(Boolean, default=False, info={'tab': 'Integrações', 'label': 'E-mail enviado?'})
    
    # --- Aba: Observações ---
    observacao = Column(Text, info={'tab': 'Observações', 'label': 'Observações Internas', 'placeholder': '', 'col_span': 2})
    observacoes_nf = Column(Text, info={'tab': 'Observações', 'label': 'Observações na NF (infCpl)', 'placeholder': 'Texto que sairá na Nota Fiscal', 'col_span': 2})
    
    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chave Estrangeira
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    # Relacionamentos (Many-to-One)
    empresa = relationship("Empresa", back_populates="pedidos")
    cliente = relationship("Cadastro", back_populates="pedidos_como_cliente", foreign_keys=[id_cliente])
    vendedor = relationship("Cadastro", back_populates="pedidos_como_vendedor", foreign_keys=[id_vendedor])
    transportadora = relationship("Cadastro", back_populates="pedidos_como_transportadora", foreign_keys=[id_transportadora])


class Tributacao(Base):
    """
    Modelo de Regras Tributárias.
    """
    __tablename__ = "regras_tributarias"
    __label__ = "Regra de Imposto"
    __label_plural__ = "Regras Tributárias"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Configuração ---
    descricao = Column(String, 
                       info={'tab': 'Configuração', 'label': 'Nome da Regra', 'placeholder': 'Ex: Venda Dentro do Estado'})
    prioridade = Column(Integer, default=10, 
                        info={'tab': 'Configuração', 'label': 'Prioridade (Maior = Mais forte)', 'placeholder': '10'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Configuração', 'label': 'Ativa?', 'placeholder': ''})
    
    # --- Aba: Regras (Chaves) ---
    regime_emitente = Column(SQLAlchemyEnum(RegraRegimeEmitenteEnum, native_enum=False), 
                             info={'tab': 'Regras (Chaves)', 'label': 'Regime da Empresa', 'placeholder': 'Selecione...'})
    tipo_operacao = Column(SQLAlchemyEnum(RegraTipoOperacaoEnum, native_enum=False), 
                           info={'tab': 'Regras (Chaves)', 'label': 'Tipo de Operação', 'placeholder': 'Selecione...'})
    tipo_cliente = Column(SQLAlchemyEnum(RegraTipoClienteEnum, native_enum=False), 
                          info={'tab': 'Regras (Chaves)', 'label': 'Tipo de Cliente', 'placeholder': 'Selecione...'})
    localizacao_destino = Column(SQLAlchemyEnum(RegraLocalizacaoDestinoEnum, native_enum=False), 
                                 info={'tab': 'Regras (Chaves)', 'label': 'Destino', 'placeholder': 'Selecione...'})
    origem_produto = Column(SQLAlchemyEnum(FiscalOrigemEnum, native_enum=False), 
                            info={'tab': 'Regras (Chaves)', 'label': 'Origem do Produto', 'placeholder': 'Selecione...'})
    ncm_chave = Column(String, 
                       info={'tab': 'Regras (Chaves)', 'label': 'NCM (Filtro)', 'placeholder': 'Ex: 6109.* ou 6109.10.00'}) # Pode ser '6109.10.00', 'Geral', '*'
    
    # --- Aba: Tributos (Valores) ---
    cfop = Column(String, info={'tab': 'Tributos', 'label': 'CFOP', 'placeholder': 'Ex: 5102'})
    
    # ICMS
    icms_cst = Column(SQLAlchemyEnum(FiscalICMSCSTEnum, native_enum=False), info={'tab': 'Tributos', 'label': 'CST/CSOSN ICMS', 'placeholder': 'Selecione...'})
    cbenef = Column(String, info={'tab': 'Tributos', 'label': 'Cód. Benefício (cBenef)', 'placeholder': 'Ex: PR850000'})
    icms_reducao_bc_perc = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Tributos', 'format_mask': 'percent:2', 'label': 'Redução BC ICMS', 'placeholder': '0,00'})
    icms_p_dif = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Tributos', 'format_mask': 'percent:2', 'label': 'Percentual Diferimento ICMS', 'placeholder': '0,00'})
    
    # ICMS ST
    icms_st_cst = Column(SQLAlchemyEnum(FiscalICMSCSTEnum, native_enum=False), info={'tab': 'Tributos', 'label': 'CST ICMS ST', 'placeholder': 'Selecione...'})
    icms_st_mva_perc = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Tributos', 'format_mask': 'percent:2', 'label': 'MVA ICMS ST', 'placeholder': '0,00'})
    icms_st_aliquota = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Tributos', 'format_mask': 'percent:2', 'label': 'Alíquota ICMS ST', 'placeholder': '0,00'})
    fcp_aliquota = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Tributos', 'format_mask': 'percent:2', 'label': 'Alíquota FCP', 'placeholder': '0,00'})
    
    # IPI / PIS / COFINS
    ipi_cst = Column(SQLAlchemyEnum(FiscalIPICSTEnum, native_enum=False), info={'tab': 'Tributos', 'label': 'CST IPI', 'placeholder': 'Selecione...'})
    ipi_codigo_enquadramento = Column(String(3), default='999', info={'tab': 'Tributos', 'label': 'Cód. Enquadramento IPI', 'placeholder': 'Ex: 999'})
    pis_cst = Column(SQLAlchemyEnum(FiscalPISCOFINSCSTEnum, native_enum=False), info={'tab': 'Tributos', 'label': 'CST PIS', 'placeholder': 'Selecione...'})
    pis_aliquota = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Tributos', 'format_mask': 'percent:2', 'label': 'Alíquota PIS', 'placeholder': '0,00'})
    cofins_cst = Column(SQLAlchemyEnum(FiscalPISCOFINSCSTEnum, native_enum=False), info={'tab': 'Tributos', 'label': 'CST COFINS', 'placeholder': 'Selecione...'})
    cofins_aliquota = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Tributos', 'format_mask': 'percent:2', 'label': 'Alíquota COFINS', 'placeholder': '0,00'})
    
    # --- Aba: Reforma Tributária 2026 ---
    ibs_aliquota = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Reforma 2026', 'format_mask': 'percent:2', 'label': 'Alíquota IBS', 'placeholder': '0,00'})
    cbs_aliquota = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Reforma 2026', 'format_mask': 'percent:2', 'label': 'Alíquota CBS', 'placeholder': '0,00'})
    is_aliquota = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Reforma 2026', 'format_mask': 'percent:2', 'label': 'Imposto Seletivo (IS)', 'placeholder': '0,00'})
    reforma_cst = Column(String, default='000', info={'tab': 'Reforma 2026', 'label': 'CST Reforma (IBS/CBS)', 'placeholder': 'Ex: 000'})
    reforma_c_class_trib = Column(String, default='000001', info={'tab': 'Reforma 2026', 'label': 'Cód. Classificação Tributária', 'placeholder': 'Ex: 000001'})
    
    # --- DIFAL (EC 87/2015) ---
    fcp_aliquota_destino = Column(Numeric(5, 2), default=0, nullable=False, info={'tab': 'Tributos', 'format_mask': 'percent:2', 'label': 'Alíq. FCP Destino', 'placeholder': '0,00'})

    # --- Adicione este campo ---
    # Armazena JSON: { "SP": { "aliq_inter": 12, "aliq_intra": 18, "fcp": 0, "ie_st": "123..." }, ... }
    regras_uf = Column(JSON, default={}, info={
        'tab': 'Regras por Estado', 
        'label': 'Exceções por Estado (ICMS/ST)', 
        'component': 'state_tax_rules',  # <--- Nome do componente React que criaremos
        'placeholder': ''
    })

    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chave Estrangeira
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    # Relacionamento (Many-to-One)
    empresa = relationship("Empresa", back_populates="regras_tributarias")
    
    
class ClassificacaoContabil(Base):
    """
    Modelo de Classificação Contábil.
    """
    __tablename__ = "classificacao_contabil"
    __label__ = "Plano de Contas"
    __label_plural__ = "Plano de Contas"

    id = Column(Integer, primary_key=True, index=True)
    
    grupo = Column(String, nullable=False, 
                   info={'tab': 'Geral', 'component': 'creatable_select', 'label': 'Grupo', 'placeholder': 'Ex: Despesas'})
    descricao = Column(String, nullable=False, 
                       info={'tab': 'Geral', 'label': 'Descrição', 'placeholder': 'Ex: Material de Escritório'})
    tipo = Column(String, nullable=False, 
                  info={'tab': 'Geral', 'component': 'creatable_select', 'label': 'Tipo', 'placeholder': 'Ex: Variável'})
    tipo_movimentacao = Column(String, nullable=False, default="Saída", 
                               info={
                                   'tab': 'Geral', 
                                   'label': 'Tipo de Movimentação', 
                                   'component': 'select',
                                   'placeholder': 'Selecione...',
                                   'options': [
                                       {'label': 'Entrada', 'value': 'Entrada'},
                                       {'label': 'Saída', 'value': 'Saída'},
                                   ]
                               })
    considerar = Column(Boolean, nullable=False, default=True, 
                        info={'tab': 'Geral', 'label': 'Considerar?', 'placeholder': ''})

    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    empresa = relationship("Empresa", back_populates="classificacoes_contabeis", foreign_keys=[id_empresa])

    
class IntelipostConfiguracao(Base):
    """
    Modelo para armazenar as configurações da integração Intelipost.
    """
    __tablename__ = "intelipost_configuracoes"
    __label__ = "Configuração Intelipost"
    __label_plural__ = "Configurações Intelipost"

    id = Column(Integer, primary_key=True, index=True)
    api_key = Column(EncryptedString, nullable=False, info={'tab': 'Dados Gerais', 'ui_type': 'password', 'label': 'Chave de API (Intelipost)', 'placeholder': 'Cole sua chave aqui'})
    origin_zip_code = Column(String(9), nullable=False, info={'tab': 'Dados Gerais', 'format_mask': 'cep', 'label': 'CEP de Origem', 'placeholder': '00000-000'})
    origin_warehouse_code = Column(String, nullable=True, info={'tab': 'Dados Gerais', 'label': 'Código do CD (Warehouse)', 'placeholder': 'Ex: CD01'})
    
    # Controle interno
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Multi-tenancy
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    empresa = relationship("Empresa", backref="intelipost_config")

# Aliases para compatibilidade com o dispatcher que tenta encontrar o modelo
# baseando-se na URL (ex: 'intelipost_configuracoes' -> 'Intelipost_configuracoes')
Intelipost_configuracao = IntelipostConfiguracao
Intelipost_configuracoes = IntelipostConfiguracao


class MeliConfiguracao(Base):
    __tablename__ = "meli_configuracoes"
    __label__ = "Configuração Mercado Livre"
    __label_plural__ = "Configurações Mercado Livre"

    id = Column(Integer, primary_key=True, index=True)
    
    # Aba: Geral
    app_id = Column(String, nullable=True, info={'tab': 'Geral', 'label': 'App ID', 'placeholder': ''})
    client_secret = Column(EncryptedString, nullable=True, info={'tab': 'Geral', 'ui_type': 'password', 'label': 'Client Secret', 'placeholder': ''})
    redirect_uri = Column(String, nullable=True, info={'tab': 'Geral', 'label': 'Redirect URI', 'placeholder': ''})
    
    # Aba: Preferências
    cliente_padrao_id = Column(Integer, ForeignKey("cadastros.id"), nullable=True, info={'tab': 'Preferências', 'label': 'Cliente Padrão (Fallback)', 'placeholder': 'Selecione...'})
    vendedor_padrao_id = Column(Integer, ForeignKey("cadastros.id"), nullable=True, info={'tab': 'Preferências', 'label': 'Vendedor Padrão', 'placeholder': 'Selecione...'})
    situacao_pedido_inicial = Column(SQLAlchemyEnum(PedidoSituacaoEnum, native_enum=True), nullable=False, default=PedidoSituacaoEnum.orcamento, 
                      info={'tab': 'Preferências', 'label': 'Situação ao Importar', 'placeholder': 'Selecione...'})
    caixa_padrao = Column(String, nullable=True, 
                 info={'tab': 'Preferências', 'component': 'creatable_select', 'label': 'Caixa/Banco Padrão', 'placeholder': 'Ex: Banco Itaú'})

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    # Relacionamentos
    empresa = relationship("Empresa", backref="meli_config")

Meli_configuracao = MeliConfiguracao
Meli_configuracoes = MeliConfiguracao


class MeliCredentials(Base):
    __tablename__ = "meli_credentials"

    id = Column(Integer, primary_key=True, index=True)
    user_id_ml = Column(BigInteger, unique=True, nullable=False)
    access_token = Column(EncryptedString, nullable=False)
    refresh_token = Column(EncryptedString, nullable=False)
    expires_in = Column(Integer, nullable=False)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    
class MagentoConfiguracao(Base):
    """
    Modelo para armazenar as configurações da integração Adobe Commerce (Magento 2).
    """
    __tablename__ = "magento_configuracoes"
    __label__ = "Configuração Magento"
    __label_plural__ = "Configurações Magento"

    id = Column(Integer, primary_key=True, index=True)
    
    # Aba: Conexão
    base_url = Column(String, nullable=False, info={'tab': 'Conexão', 'label': 'URL da Loja (Base URL)', 'placeholder': 'https://minhaloja.com.br'})
    consumer_key = Column(String, nullable=False, info={'tab': 'Conexão', 'label': 'Consumer Key', 'placeholder': ''})
    consumer_secret = Column(EncryptedString, nullable=False, info={'tab': 'Conexão', 'ui_type': 'password', 'label': 'Consumer Secret', 'placeholder': ''})
    access_token = Column(EncryptedString, nullable=False, info={'tab': 'Conexão', 'ui_type': 'password', 'label': 'Access Token', 'placeholder': ''})
    token_secret = Column(EncryptedString, nullable=False, info={'tab': 'Conexão', 'ui_type': 'password', 'label': 'Token Secret', 'placeholder': ''})
    store_view_code = Column(String, default='default', info={'tab': 'Conexão', 'label': 'Código da Store View (ex: default)', 'placeholder': 'default'})
    
    # Aba: Preferências
    vendedor_padrao_id = Column(Integer, ForeignKey("cadastros.id"), nullable=True, info={'tab': 'Preferências', 'label': 'Vendedor Padrão', 'placeholder': 'Selecione...'})
    situacao_pedido_inicial = Column(SQLAlchemyEnum(PedidoSituacaoEnum, native_enum=True), nullable=False, default=PedidoSituacaoEnum.orcamento, 
                      info={'tab': 'Preferências', 'label': 'Situação ao Importar', 'placeholder': 'Selecione...'})
    
    payment_method_contains = Column(String, nullable=True, info={'tab': 'Preferências', 'label': 'Filtrar Método de Pagamento (Contém)', 'placeholder': 'Ex: credit_card, pix'})
    filtros_padrao = Column(JSON, nullable=True, default=[], info={'tab': 'Preferências', 'label': 'Filtros Padrão de Importação', 'component': 'default_filters'})

    # Controle
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    # Relacionamentos
    empresa = relationship("Empresa", backref="magento_config")

# Alias para compatibilidade com o dispatcher
Magento_configuracao = MagentoConfiguracao
Magento_configuracoes = MagentoConfiguracao

class TiktokConfiguracao(Base):
    __tablename__ = "tiktok_configuracoes"
    __label__ = "Configuração Tiktok Shop"
    __label_plural__ = "Configurações Tiktok Shop"

    id = Column(Integer, primary_key=True, index=True)
    
    # Aba: Conexão
    app_key = Column(String, nullable=False, info={'tab': 'Conexão', 'label': 'App Key', 'placeholder': ''})
    app_secret = Column(EncryptedString, nullable=False, info={'tab': 'Conexão', 'ui_type': 'password', 'label': 'App Secret', 'placeholder': ''})
    access_token = Column(EncryptedString, nullable=True, info={'tab': 'Conexão', 'ui_type': 'password', 'label': 'Access Token', 'placeholder': ''})
    refresh_token = Column(EncryptedString, nullable=True, info={'tab': 'Conexão', 'ui_type': 'password', 'label': 'Refresh Token', 'placeholder': ''})
    shop_id = Column(String, nullable=True, info={'tab': 'Conexão', 'label': 'Shop ID', 'placeholder': ''})
    
    # Aba: Preferências
    vendedor_padrao_id = Column(Integer, ForeignKey("cadastros.id"), nullable=True, info={'tab': 'Preferências', 'label': 'Vendedor Padrão', 'placeholder': 'Selecione...'})
    situacao_pedido_inicial = Column(SQLAlchemyEnum(PedidoSituacaoEnum, native_enum=True), nullable=False, default=PedidoSituacaoEnum.orcamento, 
                      info={'tab': 'Preferências', 'label': 'Situação ao Importar', 'placeholder': 'Selecione...'})
    
    filtros_padrao = Column(JSON, nullable=True, default=[], info={'tab': 'Preferências', 'label': 'Filtros Padrão de Importação', 'component': 'default_filters'})

    # Controle
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    # Relacionamentos
    empresa = relationship("Empresa", backref="tiktok_config")

# Alias para compatibilidade com o dispatcher
Tiktok_configuracao = TiktokConfiguracao
Tiktok_configuracoes = TiktokConfiguracao

# Alias para ClassificacaoContabil
Classificacao_contabil = ClassificacaoContabil

class ElasticEmailConfiguracao(Base):
    """
    Configurações globais para envio de e-mails via Elastic Email (credenciais da API).
    """
    __tablename__ = "elastic_email_configuracoes"
    __label__ = "Configuração Elastic Email"
    __label_plural__ = "Configurações Elastic Email"

    id = Column(Integer, primary_key=True, index=True)
    api_key = Column(EncryptedString, nullable=False, info={'tab': 'Geral', 'ui_type': 'password', 'label': 'API Key (Elastic Email)', 'placeholder': 'Sua API Key'})
    from_email = Column(String, nullable=False, info={'tab': 'Geral', 'label': 'E-mail do Remetente', 'placeholder': 'exemplo@suaempresa.com.br'})
    from_name = Column(String, info={'tab': 'Geral', 'label': 'Nome do Remetente', 'placeholder': 'Minha Loja'})

    ativo = Column(Boolean, default=True, info={'tab': 'Geral', 'label': 'Integração Ativa?'})

    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    empresa = relationship("Empresa", backref="elastic_email_config")

# Aliases para o dispatcher
Elastic_email_configuracao = ElasticEmailConfiguracao
Elastic_email_configuracoes = ElasticEmailConfiguracao


class OutrasEmpresasConfiguracao(Base):
    __tablename__ = "outras_empresas_configuracoes"
    __label__ = "Configuração Outras Empresas"
    __label_plural__ = "Configurações Outras Empresas"

    id = Column(Integer, primary_key=True, index=True)
    nome = Column(String, nullable=False, info={'tab': 'Geral', 'label': 'Nome de Identificação', 'placeholder': 'Ex: Filial SP'})
    email = Column(String, nullable=False, info={'tab': 'Geral', 'label': 'E-mail da Empresa', 'placeholder': 'email@empresa.com'})
    senha = Column(EncryptedString, nullable=False, info={'tab': 'Geral', 'ui_type': 'password', 'label': 'Senha', 'placeholder': 'Senha de acesso'})
    
    ativo = Column(Boolean, default=True, info={'tab': 'Geral', 'label': 'Integração Ativa?'})
    token = Column(EncryptedString, nullable=True, info={'tab': 'Acesso', 'label': 'Token de Acesso (Auto)', 'read_only': True, 'ui_type': 'password'})
    token_expiracao = Column(DateTime(timezone=True), nullable=True, info={'tab': 'Acesso', 'label': 'Expira em', 'read_only': True})

    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    empresa = relationship("Empresa", backref="outras_empresas_config")

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

Outra_empresa_configuracao = OutrasEmpresasConfiguracao
Outras_empresas_configuracoes = OutrasEmpresasConfiguracao
Outras_empresas_configuracao = OutrasEmpresasConfiguracao


class EmailRegra(Base):
    """
    Regras de disparo de e-mail automático baseadas em mudança de situação do Pedido.
    A config de credenciais (API Key) é resolvida automaticamente pela empresa.
    """
    __tablename__ = "email_regras"
    __label__ = "Regra de Automação de E-mail"
    __label_plural__ = "Regras de E-mail"

    # Transições disponíveis no fluxo de pedidos
    TRIGGERS = [
        'Orçamento → Aprovação',
        'Aprovação → Programação',
        'Programação → Produção',
        'Produção → Embalagem',
        'Embalagem → Faturamento',
        'Faturamento → Expedição',
        'Expedição → Despachado',
        'Qualquer → Cancelado',
        'Qualquer → Faturamento',
        'Qualquer → Despachado',
    ]

    id = Column(Integer, primary_key=True, index=True)

    # Identificação da regra
    nome = Column(String, nullable=False,
                  info={'tab': 'Geral', 'label': 'Nome da Regra', 'placeholder': 'Ex: E-mail de Faturamento'})

    # Trigger: transição de situação como campo único (ex: "Orçamento → Aprovação")
    trigger = Column(String, nullable=False,
                     info={
                         'tab': 'Gatilho', 'label': 'Gatilho (Transição de Status)',
                         'component': 'select',
                         'col_span': 2,
                         'placeholder': 'Selecione a transição...',
                         'options': [
                             {'label': 'Orçamento → Aprovação', 'value': 'Orçamento → Aprovação'},
                             {'label': 'Aprovação → Programação', 'value': 'Aprovação → Programação'},
                             {'label': 'Programação → Produção', 'value': 'Programação → Produção'},
                             {'label': 'Produção → Embalagem', 'value': 'Produção → Embalagem'},
                             {'label': 'Embalagem → Faturamento', 'value': 'Embalagem → Faturamento'},
                             {'label': 'Faturamento → Expedição', 'value': 'Faturamento → Expedição'},
                             {'label': 'Expedição → Despachado', 'value': 'Expedição → Despachado'},
                             {'label': 'Qualquer → Cancelado', 'value': 'Qualquer → Cancelado'},
                             {'label': 'Qualquer → Faturamento', 'value': 'Qualquer → Faturamento'},
                             {'label': 'Qualquer → Despachado', 'value': 'Qualquer → Despachado'},
                         ]
                     })

    # Conteúdo do e-mail
    subject = Column(String, nullable=False, default="Atualização do Pedido {pedido_id}",
                     info={'tab': 'Conteúdo', 'label': 'Assunto', 'placeholder': 'Use {pedido_id}, {cliente_nome}, {situacao}, {valor_total}', 'col_span': 2})
    body_html = Column(Text, nullable=True,
                       info={'tab': 'Conteúdo', 'label': 'Corpo do E-mail (HTML)', 'type': 'textarea',
                             'placeholder': 'Olá {cliente_nome}, seu pedido {pedido_id} foi atualizado para {situacao}.', 'col_span': 2})

    # Opções de Anexos (Multiselect)
    anexos = Column(JSON, default=list,
                    info={
                        'tab': 'Opções', 
                        'label': 'Anexos a enviar',
                        'component': 'multiselect',
                        'options': [
                            {'label': 'DANFE (PDF)', 'value': 'danfe'},
                            {'label': 'XML da NFe', 'value': 'xml'},
                        ]
                    })
    ativo = Column(Boolean, default=True,
                   info={'tab': 'Geral', 'label': 'Regra Ativa?'})

    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    empresa = relationship("Empresa", backref="email_regras")

    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    @property
    def situacao_de(self):
        """Extrai o status de origem do trigger (ex: 'Orçamento → Aprovação' -> 'Orçamento')."""
        if self.trigger and '→' in self.trigger:
            parte = self.trigger.split('→')[0].strip()
            return None if parte.lower() == 'qualquer' else parte
        return None

    @property
    def situacao_para(self):
        """Extrai o status destino do trigger (ex: 'Orçamento → Aprovação' -> 'Aprovação')."""
        if self.trigger and '→' in self.trigger:
            return self.trigger.split('→')[1].strip()
        return self.trigger

# Aliases para o dispatcher
Email_regra = EmailRegra
Email_regras = EmailRegra


class OpcaoCampo(Base):
    """
    Tabela para armazenar opções dinâmicas de campos (Selects).
    """
    __tablename__ = "opcoes_campos"

    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String, nullable=False, index=True)
    field_name = Column(String, nullable=False, index=True)
    valor = Column(String, nullable=False)
    
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

class UsuarioPreferencia(Base):
    """
    Armazena preferências de visualização de listagens por usuário (Filtros, Colunas, Ordenação).
    """
    __tablename__ = "usuario_preferencias"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    model_name = Column(String, nullable=False, index=True) # Ex: 'pedidos', 'produtos'
    
    # Armazena JSON com: { visible_columns: [], sort_by: str, sort_order: str, filters: [] }
    config = Column(JSON, nullable=False, default={})

    usuario = relationship("Usuario", backref="preferencias")

class DashboardPreferencia(Base):
    """
    Armazena o layout do grid e as configurações dos cards dinâmicos por usuário.
    """
    __tablename__ = "dashboard_preferencias"

    id = Column(Integer, primary_key=True, index=True)
    id_usuario = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    # O layout exato exigido pelo react-grid-layout (x, y, w, h, i)
    layout = Column(JSON, nullable=False, default=[]) 
    
    # Configurações de dados e visual de cada card 
    cards_config = Column(JSON, nullable=False, default={})
    
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

class Relatorio(Base):
    """
    Modelo para salvar configurações de relatórios personalizados.
    """
    __tablename__ = "relatorios"
    __label__ = "Relatório Personalizado"
    __label_plural__ = "Relatórios Personalizados"

    id = Column(Integer, primary_key=True, index=True)
    
    nome = Column(String, nullable=False, info={'tab': 'Geral', 'label': 'Nome do Relatório', 'placeholder': 'Ex: Vendas por Estado'})
    descricao = Column(String, info={'tab': 'Geral', 'label': 'Descrição', 'placeholder': 'Ex: Relatório mensal de vendas agrupado por UF'})
    
    # O modelo base do relatório (ex: 'pedidos', 'produtos')
    modelo = Column(String, nullable=False, info={'tab': 'Geral', 'label': 'Tabela Principal', 'component': 'select', 'options': [
        {'label': 'Pedidos', 'value': 'pedidos'},
        {'label': 'Produtos', 'value': 'produtos'},
        {'label': 'Clientes/Cadastros', 'value': 'cadastros'},
        {'label': 'Contas a Pagar/Receber', 'value': 'contas'},
        {'label': 'Estoque', 'value': 'estoque'}
    ]})
    
    # Armazena a configuração completa: colunas, filtros, ordenação, joins
    config = Column(JSON, default={}, info={'tab': 'Configuração', 'label': 'Construtor', 'component': 'report_builder', 'col_span': 2})

    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

class NotaFiscalRecebida(Base):
    """Modelo para notas emitidas contra o CNPJ da empresa (DF-e)."""
    __tablename__ = "nfe_recebidas"
    __label__ = "Nota Fiscal Recebida"
    __label_plural__ = "Notas Fiscais Recebidas (DF-e)"
    id = Column(Integer, primary_key=True, index=True)
    chave_acesso = Column(String(44), index=True, nullable=True, info={'label': 'Chave de Acesso'})
    nsu = Column(String, index=True, info={'label': 'NSU'})
    tipo_documento = Column(String, index=True, info={'label': 'Tipo do Documento'})
    cnpj_emitente = Column(String(14), index=True, nullable=True, info={'label': 'CNPJ Emitente', 'format_mask': 'cnpj'})
    nome_emitente = Column(String, info={'label': 'Emitente'})
    valor_total = Column(Numeric(15, 2), nullable=True, info={'label': 'Valor Total', 'format_mask': 'currency'})
    data_emissao = Column(DateTime, nullable=True, info={'label': 'Data Emissão'})
    situacao_manifestacao = Column(String, default="Pendente", info={'label': 'Situação'}) 
    xml_completo = Column(Text, nullable=True, info={'visible': False}) 
    ja_importado = Column(Boolean, default=False, info={'label': 'Importado'})
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    empresa = relationship("Empresa")

# Aliases para o dispatcher (mapeamento nfe_recebidas -> Nfe_recebida)
Nfe_recebida = NotaFiscalRecebida
Nfe_recebidas = NotaFiscalRecebida
Nota_fiscal_recebida = NotaFiscalRecebida