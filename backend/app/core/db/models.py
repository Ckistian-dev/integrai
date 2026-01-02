import enum
from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String, Enum as SQLAlchemyEnum,
    DateTime, Numeric, JSON, Text, Date
)
from sqlalchemy.orm import relationship
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.sql import func
from .database import Base

# --- Definição de Enums ---
# (Centralizando todos os Enums definidos nas planilhas)

# Para Empresa 
class EmpresaCRTEnum(str, enum.Enum):
    simples_nacional = "simples nacional"
    lucro_presumido = "lucro presumido"
    lucro_real = "lucro real"

class EmpresaEmissaoEnum(str, enum.Enum):
    desenvolvimento = "desenvolvimento"
    producao = "producao"

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
    
class CadastroIndicadorIEEnum(str, enum.Enum):
    nao_se_aplica = "0"
    contribuinte_icms = "1"
    isento = "2"
    nao_contribuinte = "9"

# Para Produto 
class ProdutoUnidadeEnum(str, enum.Enum):
    un = "un"
    pc = "pc"
    kg = "kg"
    mt = "mt"
    cx = "cx"

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
    disponivel = "Disponivel"
    reservado = "Reservado"
    indisponivel = "Indisponível"

# Para Pedido 
class PedidoSituacaoEnum(str, enum.Enum):
    orcamento = "Orçamento"
    aprovacao = "Aprovação"
    programacao = "Programação"
    producao = "Produção"
    embalagem = "Embalagem"
    faturamento = "Faturamento"
    expedicao = "Expedição"
    cancelado = "Cancelado"

class PedidoModalidadeFreteEnum(str, enum.Enum):
    cif = "0"
    fob = "1"
    terceiros = "2"
    proprio_remetente = "3"
    proprio_destinatario = "4"
    sem_frete = "9"

# Para Tributacao 
class RegraRegimeEmitenteEnum(str, enum.Enum):
    simples_nacional = "Simples Nacional"
    lucro_presumido = "Lucro Presumido"
    lucro_real = "Lucro Real"

class RegraTipoOperacaoEnum(str, enum.Enum):
    venda = "Venda"
    devolucao = "Devolucao"
    remessa = "Remessa"

class RegraTipoClienteEnum(str, enum.Enum):
    pf = "PF"
    pj_contribuinte = "PJ_Contribuinte"
    pj_isento = "PJ_Isento"
    pj_nao_contribuinte = "PJ_NaoContribuinte"

class RegraLocalizacaoDestinoEnum(str, enum.Enum):
    interna = "Interna"
    interestadual = "Interestadual"
    exterior = "Exterior"


# --- Tipos Customizados ---
class Currency(Numeric):
    """Tipo customizado para valores monetários (BRL)."""
    def __init__(self, precision=15, scale=2, asdecimal=True, **kwargs):
        super().__init__(precision=precision, scale=scale, asdecimal=asdecimal, **kwargs)

# --- Modelos (Tabelas) ---

class Empresa(Base):
    """
    Modelo do Tenant (Empresa). Esta é a tabela central.
    """
    __tablename__ = "empresas"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    cnpj = Column(String(18), unique=True, nullable=False, index=True, 
                  info={'format_mask': 'cnpj', 'tab': 'Dados Gerais'})
    razao = Column(String, nullable=False, 
                   info={'tab': 'Dados Gerais'})
    fantasia = Column(String, 
                      info={'tab': 'Dados Gerais'})
    url_logo = Column(String, 
                      info={'tab': 'Dados Gerais', 'label': 'URL do Logo'})
    inscricao_estadual = Column(String, 
                                info={'tab': 'Dados Gerais'})
    telefone = Column(String, 
                      info={'format_mask': 'phone', 'tab': 'Dados Gerais'})
    
    # --- Aba: Endereço ---
    cep = Column(String(9), nullable=False, 
                 info={'format_mask': 'cep', 'tab': 'Endereço'})
    estado = Column(String(2), 
                    info={'tab': 'Endereço'})
    cidade = Column(String, 
                    info={'tab': 'Endereço'})
    bairro = Column(String, 
                    info={'tab': 'Endereço'})
    logradouro = Column(String, 
                        info={'tab': 'Endereço'})
    numero = Column(String, 
                    info={'tab': 'Endereço'})
    complemento = Column(String, 
                         info={'tab': 'Endereço'})
    
    # --- Aba: Configurações ---
    cnae = Column(String, 
                  info={'tab': 'Configurações'})
    crt = Column(SQLAlchemyEnum(EmpresaCRTEnum, native_enum=False), nullable=False, default=EmpresaCRTEnum.simples_nacional, 
                 info={'tab': 'Configurações'})
    emissao = Column(SQLAlchemyEnum(EmpresaEmissaoEnum, native_enum=False), nullable=False, default=EmpresaEmissaoEnum.desenvolvimento, 
                     info={'tab': 'Configurações'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Configurações'})

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


class Usuario(Base):
    """
    Modelo de Usuário do sistema.
    """
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    nome = Column(String, nullable=False, 
                  info={'tab': 'Dados Gerais'})
    email = Column(String, unique=True, index=True, nullable=False, 
                   info={'tab': 'Dados Gerais'})
    senha = Column(String, nullable=False, 
                   info={'tab': 'Dados Gerais'}) # Hashed password
    perfil = Column(SQLAlchemyEnum(UsuarioPerfilEnum, native_enum=False), nullable=False, default=UsuarioPerfilEnum.vendedor, 
                    info={'tab': 'Dados Gerais'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais'})

    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chave estrangeira para o multi-tenancy
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)
    
    # Relacionamento (Many-to-One)
    empresa = relationship("Empresa", back_populates="usuarios")


class Cadastro(Base):
    """
    Modelo de Cadastros (Super-modelo).
    Pode ser Cliente, Fornecedor, Transportadora, Vendedor.
    """
    __tablename__ = "cadastros"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    cpf_cnpj = Column(String(18), nullable=False, index=True, 
                      info={'format_mask': 'cnpj_cpf', 'tab': 'Dados Gerais'})
    nome_razao = Column(String, nullable=False, index=True, 
                        info={'tab': 'Dados Gerais'})
    fantasia = Column(String, 
                      info={'tab': 'Dados Gerais'})
    tipo_pessoa = Column(SQLAlchemyEnum(CadastroTipoPessoaEnum, native_enum=False), nullable=False, default=CadastroTipoPessoaEnum.fisica, 
                         info={'tab': 'Dados Gerais'})
    tipo_cadastro = Column(SQLAlchemyEnum(CadastroTipoCadastroEnum, native_enum=False), nullable=False, default=CadastroTipoCadastroEnum.cliente, 
                           info={'tab': 'Dados Gerais'})
    
    # Fiscal (ainda em Dados Gerais)
    indicador_ie = Column( SQLAlchemyEnum( CadastroIndicadorIEEnum, native_enum=False, values_callable=lambda x: [e.value for e in x] ),
        nullable=True, default=CadastroIndicadorIEEnum.nao_contribuinte,
        info={'tab': 'Dados Gerais'} )
    inscricao_estadual = Column(String, 
                                info={'tab': 'Dados Gerais'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais'})

    # --- Aba: Contato ---
    email = Column(String, index=True, 
                   info={'tab': 'Contato'})
    telefone = Column(String, 
                      info={'format_mask': 'phone', 'tab': 'Contato'}) 
    celular = Column(String, 
                     info={'format_mask': 'phone', 'tab': 'Contato'})
    
    # --- Aba: Endereço ---
    cep = Column(String(9), nullable=False, 
                 info={'format_mask': 'cep', 'tab': 'Endereço'})
    estado = Column(String(2), 
                    info={'tab': 'Endereço'})
    cidade = Column(String, 
                    info={'tab': 'Endereço'})
    bairro = Column(String, 
                    info={'tab': 'Endereço'})
    logradouro = Column(String, 
                        info={'tab': 'Endereço'})
    numero = Column(String, 
                    info={'tab': 'Endereço'})
    complemento = Column(String, 
                         info={'tab': 'Endereço'})
    
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
    
    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    descricao = Column(String, nullable=False, 
                       info={'tab': 'Dados Gerais'})
    regras = Column(JSON,
                    info={'tab': 'Regras de Empacotamento'}) # JSON para flexibilidade
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais'})

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

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Dados Gerais ---
    sku = Column(String, nullable=False, unique=True, index=True, 
                 info={'tab': 'Dados Gerais'})
    gtin = Column(String, index=True, 
                  info={'tab': 'Dados Gerais'})
    descricao = Column(String, nullable=False, index=True, 
                       info={'tab': 'Dados Gerais'})
    unidade = Column(SQLAlchemyEnum(ProdutoUnidadeEnum, native_enum=False), default=ProdutoUnidadeEnum.un, 
                     info={'tab': 'Dados Gerais'})
    tipo_produto = Column(SQLAlchemyEnum(ProdutoTipoEnum, native_enum=False), default=ProdutoTipoEnum.mercadoria_revenda, 
                          info={'tab': 'Dados Gerais'})
    url_imagem = Column(String, 
                        info={'tab': 'Dados Gerais'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Dados Gerais'})
    id_embalagem = Column(Integer, ForeignKey("embalagens.id"), nullable=True, 
                          info={'tab': 'Dados Gerais'})
    id_fornecedor = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                           info={'tab': 'Dados Gerais'}) # Referencia Cadastro (tipo_cadastro=fornecedor)

    # --- Aba: Categorização ---
    grupo = Column(String, 
                   info={'tab': 'Categorização'})
    subgrupo1 = Column(String, 
                       info={'tab': 'Categorização'})
    subgrupo2 = Column(String, 
                       info={'tab': 'Categorização'})
    subgrupo3 = Column(String, 
                       info={'tab': 'Categorização'})
    subgrupo4 = Column(String, 
                       info={'tab': 'Categorização'})
    subgrupo5 = Column(String, 
                       info={'tab': 'Categorização'})
    
    # --- Aba: Fiscal ---
    classificacao_fiscal = Column(String, 
                                  info={'tab': 'Fiscal'})
    origem = Column(SQLAlchemyEnum(ProdutoOrigemEnum, native_enum=False), default=ProdutoOrigemEnum.nacional, 
                    info={'tab': 'Fiscal'})
    ncm = Column(String(8), 
                 info={'format_mask': 'ncm', 'tab': 'Fiscal'})
    
    # --- Aba: Valores e Dimensões ---
    preco = Column(Currency(), 
                   info={'tab': 'Valores e Dimensões'}) 
    custo = Column(Currency(), 
                   info={'tab': 'Valores e Dimensões'})
    estoque_negativo = Column(Boolean, default=False, 
                              info={'tab': 'Valores e Dimensões'})
    
    peso = Column(Numeric(10, 3), 
                  info={'format_mask': 'decimal:3', 'tab': 'Valores e Dimensões'})
    altura = Column(Numeric(10, 2), 
                    info={'tab': 'Valores e Dimensões'})
    largura = Column(Numeric(10, 2), 
                     info={'tab': 'Valores e Dimensões'})
    comprimento = Column(Numeric(10, 2), 
                         info={'tab': 'Valores e Dimensões'})
    
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

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Principal ---
    tipo_conta = Column(SQLAlchemyEnum(ContaTipoEnum, native_enum=False), nullable=False, default=ContaTipoEnum.a_receber, 
                        info={'tab': 'Principal'})
    situacao = Column(SQLAlchemyEnum(ContaSituacaoEnum, native_enum=False), nullable=False, default=ContaSituacaoEnum.em_aberto, 
                      info={'tab': 'Principal'})
    descricao = Column(String, 
                       info={'tab': 'Principal'})
    numero_conta = Column(Integer, 
                          info={'tab': 'Principal'})
    id_fornecedor = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                           info={'tab': 'Principal'}) # Ref. Cadastro (tipo_cadastro=fornecedor)

    # --- Aba: Financeiro ---
    valor = Column(Currency(), nullable=False, 
                   info={'tab': 'Financeiro'})
    plano_contas = Column(String, 
                 info={'tab': 'Financeiro', 'component': 'creatable_select'})
    caixa_destino_origem = Column(String, 
                 info={'tab': 'Financeiro', 'component': 'creatable_select'})
    pagamento = Column(String, 
                 info={'tab': 'Financeiro', 'component': 'creatable_select'})

    # --- Aba: Datas ---
    data_emissao = Column(Date, 
                          info={'tab': 'Datas'})
    data_vencimento = Column(Date, 
                             info={'tab': 'Datas'})
    data_baixa = Column(Date, nullable=True, 
                        info={'tab': 'Datas'})
    
    # --- Aba: Outros ---
    observacoes = Column(Text, 
                         info={'tab': 'Outros'})

    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chaves Estrangeiras
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    # Relacionamentos (Many-to-One)
    empresa = relationship("Empresa", back_populates="contas")
    fornecedor = relationship("Cadastro", back_populates="contas_como_fornecedor", foreign_keys=[id_fornecedor])


class Estoque(Base):
    """
    Modelo de Estoque (Lotes).
    """
    __tablename__ = "estoque"

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Principal ---
    id_produto = Column(Integer, ForeignKey("produtos.id"), nullable=False, 
                        info={'tab': 'Principal'}) # TODO: Isso deveria ser um Select/Busca
    lote = Column(String, 
                  info={'tab': 'Principal'})
    quantidade = Column(Integer, nullable=False, 
                        info={'tab': 'Principal'})
    situacao = Column(SQLAlchemyEnum(EstoqueSituacaoEnum, native_enum=False), nullable=False, default=EstoqueSituacaoEnum.disponivel, 
                      info={'tab': 'Principal'})

    # --- Aba: Localização ---
    deposito = Column(String, 
                      info={'tab': 'Localização', 'component': 'creatable_select'})
    rua = Column(String, 
                 info={'tab': 'Localização', 'component': 'creatable_select'})
    nivel = Column(String, 
                   info={'tab': 'Localização', 'component': 'creatable_select'})
    cor = Column(String, 
                 info={'tab': 'Localização', 'component': 'creatable_select'}) # Pode ser usado para variante
    
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

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Principal ---
    id_cliente = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                        info={'tab': 'Principal'}) # Ref. Cadastro (tipo_cadastro=cliente)
    id_vendedor = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                         info={'tab': 'Principal'}) # Ref. Cadastro (tipo_cadastro=vendedor)
    id_transportadora = Column(Integer, ForeignKey("cadastros.id"), nullable=True, 
                               info={'tab': 'Frete'}) # Ref. Cadastro (tipo_cadastro=transportadora)
    origem_venda = Column(String, 
                          info={'tab': 'Principal', 'component': 'creatable_select'})
    situacao = Column(SQLAlchemyEnum(PedidoSituacaoEnum, native_enum=False), nullable=False, default=PedidoSituacaoEnum.orcamento, 
                      info={'tab': 'Principal'})

    # --- Aba: Datas e Prazos ---
    data_emissao = Column(Date, default=func.current_date(), 
                          info={'tab': 'Datas e Prazos'})
    data_validade = Column(Date, 
                           info={'tab': 'Datas e Prazos'})
    data_finalizacao = Column(Date, 
                              info={'tab': 'Datas e Prazos'})
    prazo_entrega = Column(Integer, 
                           info={'tab': 'Datas e Prazos'}) # Ex: 10
    
    # --- Aba: Itens e Observações ---
    itens = Column(JSON, 
                   info={'tab': 'Itens'}) # Armazena os itens do pedido como JSON
    
    # --- Aba: Valores ---
    total = Column(Currency(), 
                   info={'tab': 'Valores'})
    desconto = Column(Currency(), 
                      info={'tab': 'Valores'})
    total_desconto = Column(Currency(), 
                            info={'tab': 'Valores'})
    pagamento = Column(String, 
                       info={'tab': 'Valores', 'component': 'creatable_select'})

    # --- Aba: Frete ---
    modalidade_frete = Column(SQLAlchemyEnum(PedidoModalidadeFreteEnum, native_enum=False, values_callable=lambda x: [e.value for e in x]), default=PedidoModalidadeFreteEnum.sem_frete, 
                              info={'tab': 'Frete'})
    valor_frete = Column(Currency(), 
                         info={'tab': 'Frete'})

    
    # --- Aba: Fiscal ---
    natureza_operacao = Column(String, 
                               info={'tab': 'Fiscal'})
    cfop = Column(String, 
                  info={'tab': 'Fiscal'})
    icms_cst = Column(String, 
                      info={'tab': 'Fiscal'})
    icms_aliquota = Column(Numeric(5, 2), 
                           info={'tab': 'Fiscal', 'format_mask': 'percent:2'})
    icms_reducao_bc_perc = Column(Numeric(5, 2), 
                                  info={'tab': 'Fiscal', 'format_mask': 'percent:2'})
    icms_st_cst = Column(String, 
                         info={'tab': 'Fiscal'})
    icms_st_mva_perc = Column(Numeric(5, 2), 
                              info={'tab': 'Fiscal', 'format_mask': 'percent:2'})
    icms_st_aliquota = Column(Numeric(5, 2), 
                              info={'tab': 'Fiscal', 'format_mask': 'percent:2'})
    ipi_cst = Column(String, 
                     info={'tab': 'Fiscal'})
    ipi_aliquota = Column(Numeric(5, 2), 
                          info={'tab': 'Fiscal', 'format_mask': 'percent:2'})
    pis_cst = Column(String, 
                     info={'tab': 'Fiscal'})
    pis_aliquota = Column(Numeric(5, 2), 
                          info={'tab': 'Fiscal', 'format_mask': 'percent:2'})
    cofins_cst = Column(String, 
                        info={'tab': 'Fiscal'})
    cofins_aliquota = Column(Numeric(5, 2), 
                             info={'tab': 'Fiscal', 'format_mask': 'percent:2'})

    # --- Aba: Outros ---
    ordem_finalizacao = Column(Numeric(5, 1), 
                               info={'tab': 'Datas e Prazos'})
    
    observacao = Column(Text, 
                        info={'tab': 'Observações'})
    
    
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

    id = Column(Integer, primary_key=True, index=True)
    
    # --- Aba: Configuração ---
    descricao = Column(String, 
                       info={'tab': 'Configuração'})
    prioridade = Column(Integer, default=10, 
                        info={'tab': 'Configuração'})
    situacao = Column(Boolean, nullable=False, default=True, 
                      info={'tab': 'Configuração'})
    
    # --- Aba: Regras (Chaves) ---
    regime_emitente = Column(SQLAlchemyEnum(RegraRegimeEmitenteEnum, native_enum=False), 
                             info={'tab': 'Regras (Chaves)'})
    tipo_operacao = Column(SQLAlchemyEnum(RegraTipoOperacaoEnum, native_enum=False), 
                           info={'tab': 'Regras (Chaves)'})
    tipo_cliente = Column(SQLAlchemyEnum(RegraTipoClienteEnum, native_enum=False), 
                          info={'tab': 'Regras (Chaves)'})
    localizacao_destino = Column(SQLAlchemyEnum(RegraLocalizacaoDestinoEnum, native_enum=False), 
                                 info={'tab': 'Regras (Chaves)'})
    origem_produto = Column(String, 
                            info={'tab': 'Regras (Chaves)'}) # Usado como string '0', '1', etc.
    ncm_chave = Column(String, 
                       info={'tab': 'Regras (Chaves)'}) # Pode ser '6109.10.00', 'Geral', '*'
    
    # Campos Internos
    criado_em = Column(DateTime(timezone=True), server_default=func.now())
    atualizado_em = Column(DateTime(timezone=True), onupdate=func.now())

    # Chave Estrangeira
    id_empresa = Column(Integer, ForeignKey("empresas.id"), nullable=False)

    # Relacionamento (Many-to-One)
    empresa = relationship("Empresa", back_populates="regras_tributarias")