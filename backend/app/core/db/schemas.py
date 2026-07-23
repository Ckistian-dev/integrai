from pydantic import BaseModel as PydanticBaseModel, EmailStr, Field, field_serializer, ConfigDict
from typing import Optional, List, Any, Dict, Type

class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, from_attributes=True)
from datetime import datetime, date
from decimal import Decimal

# Importar Enums do models.py para garantir consistência
# Assumindo que os Enums estão acessíveis (via .models ou definidos localmente)
from .models import (
    EmpresaCRTEnum, EmpresaAmbienteSefazEnum, UsuarioPerfilEnum, 
    CadastroTipoPessoaEnum, CadastroTipoCadastroEnum, ProdutoUnidadeEnum,
    ProdutoTipoEnum, ProdutoOrigemEnum, ContaTipoEnum, ContaSituacaoEnum,
    EstoqueSituacaoEnum, PedidoSituacaoEnum, PedidoIndicadorPresencaEnum,
    RegraRegimeEmitenteEnum, RegraTipoOperacaoEnum, RegraTipoClienteEnum,
    RegraLocalizacaoDestinoEnum, CadastroIndicadorIEEnum, PedidoModalidadeFreteEnum, EstadoEnum, 
    FiscalICMSCSTEnum, FiscalIPICSTEnum, FiscalPISCOFINSCSTEnum, FiscalOrigemEnum, FiscalPagamentoEnum
)

# --- Schemas de Autenticação e Suporte ---
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """Schema do payload do JWT, atualizado para o modelo Usuario."""
    id_usuario: Optional[int] = None
    id_empresa: Optional[int] = None
    empresa_fantasia: Optional[str] = None
    perfil: Optional[str] = None
    email: Optional[str] = None
    permissoes: Optional[Dict[str, Any]] = None
    cor_sidebar: Optional[str] = None

class Page(BaseModel):
    """Schema genérico para paginação."""
    items: List[Any]
    total_count: int
    extra: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

# --- Schemas de Metadados ---
class FieldMetadata(BaseModel):
    name: str
    label: str
    placeholder: Optional[str] = None
    type: str
    required: bool
    options: Optional[List[Dict[str, Any]]] = None
    default_value: Optional[Any] = None
    format_mask: Optional[str] = None
    tab: Optional[str] = None
    foreign_key_model: Optional[str] = None # Modelo que a FK aponta (ex: "cadastros")
    foreign_key_label_field: Optional[str] = None # Campo de label (ex: "nome_razao")
    filename_field: Optional[str] = None
    col_span: Optional[int] = None
    read_only: bool = False
    visible: bool = True
    ui_type: Optional[str] = None

class ModelMetadata(BaseModel):
    model_name: str
    display_name: str
    display_name_singular: Optional[str] = None
    display_name_plural: Optional[str] = None
    display_field: Optional[str] = None # O campo principal de display do modelo (ex: "nome_razao")
    fields: List[FieldMetadata]


# --- 1. Schemas da Empresa ---

class EmpresaBase(BaseModel):
    cnpj: str = Field(..., max_length=18)
    razao: str
    fantasia: Optional[str] = None
    url_logo: Optional[str] = None
    inscricao_estadual: Optional[str] = None
    inscricao_municipal: Optional[str] = None
    telefone: Optional[str] = None
    cep: str = Field(..., max_length=9)
    estado: Optional[EstadoEnum] = None
    cidade: Optional[str] = None
    cidade_ibge: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    cnae: Optional[str] = None
    crt: EmpresaCRTEnum = EmpresaCRTEnum.simples_nacional
    situacao: bool = True
    cor_sidebar: Optional[str] = "#1f2937"
    # Campos Fiscais
    nfe_serie: Optional[int] = 1
    nfce_serie: Optional[int] = 1
    ambiente_sefaz: Optional[EmpresaAmbienteSefazEnum] = EmpresaAmbienteSefazEnum.homologacao
    certificado_senha: Optional[str] = None
    certificado_nome_arquivo: Optional[str] = None
    id_classificacao_contabil_padrao: Optional[int] = None
    id_classificacao_contabil_cancelamento: Optional[int] = None
    validade_orcamento: Optional[int] = 7

class EmpresaCreate(EmpresaBase):
    certificado_arquivo: Optional[bytes] = None

    @field_serializer('crt')
    def serialize_crt(self, crt: EmpresaCRTEnum, _info):
        return crt.name

class EmpresaUpdate(BaseModel):
    cnpj: Optional[str] = Field(None, max_length=18)
    razao: Optional[str] = None
    fantasia: Optional[str] = None
    url_logo: Optional[str] = None
    inscricao_estadual: Optional[str] = None
    inscricao_municipal: Optional[str] = None
    telefone: Optional[str] = None
    cep: Optional[str] = Field(None, max_length=9)
    estado: Optional[EstadoEnum] = None
    cidade: Optional[str] = None
    cidade_ibge: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    cnae: Optional[str] = None
    crt: Optional[EmpresaCRTEnum] = None
    situacao: Optional[bool] = None
    cor_sidebar: Optional[str] = None
    certificado_arquivo: Optional[bytes] = None
    certificado_senha: Optional[str] = None
    certificado_nome_arquivo: Optional[str] = None
    ambiente_sefaz: Optional[EmpresaAmbienteSefazEnum] = None
    id_classificacao_contabil_padrao: Optional[int] = None
    id_classificacao_contabil_cancelamento: Optional[int] = None
    validade_orcamento: Optional[int] = None

    @field_serializer('crt')
    def serialize_crt(self, crt: Optional[EmpresaCRTEnum], _info):
        return crt.name if crt else None

class Empresa(EmpresaBase):  # RENOMEADO de EmpresaRead para Empresa
    id: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None
    certificado_arquivo: Optional[bytes] = None
    
    nfe_numero_sequencial: Optional[int] = None
    nfce_numero_sequencial: Optional[int] = None
    nfe_ultimo_nsu: Optional[str] = None

    class Config:
        from_attributes = True

# --- 1.1 Schemas de Perfil ---

class PerfilBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    permissoes: Optional[Dict[str, Any]] = {}
    situacao: bool = True

class PerfilCreate(PerfilBase):
    pass

class PerfilUpdate(BaseModel):
    nome: Optional[str] = None
    descricao: Optional[str] = None
    permissoes: Optional[Dict[str, Any]] = None
    situacao: Optional[bool] = None

class Perfil(PerfilBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 2. Schemas do Usuário ---

class UsuarioBase(BaseModel):
    nome: str
    email: str
    situacao: bool = True
    id_perfil: Optional[int] = None

class UsuarioCreate(BaseModel):
    nome: str
    email: str
    senha: str = Field(..., min_length=8)
    situacao: bool = True
    id_perfil: Optional[int] = None

class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    senha: Optional[str] = Field(None, min_length=8)
    situacao: Optional[bool] = None
    id_perfil: Optional[int] = None

class Usuario(UsuarioBase):  # RENOMEADO de UsuarioRead para Usuario
    id: int
    id_empresa: int
    situacao: Optional[bool] = None
    criado_em: datetime
    atualizado_em: Optional[datetime] = None
    empresa: "Empresa" # Atualizada a referência aninhada
    perfil_rel: Optional["Perfil"] = Field(None, serialization_alias="perfil")

    class Config:
        from_attributes = True

# --- 3. Schemas de Cadastro (Cliente, Fornecedor, etc.) ---

class CadastroBase(BaseModel):
    cpf_cnpj: str = Field(..., max_length=18)
    nome_razao: str
    fantasia: Optional[str] = None
    tipo_pessoa: CadastroTipoPessoaEnum = CadastroTipoPessoaEnum.fisica
    tipo_cadastro: CadastroTipoCadastroEnum = CadastroTipoCadastroEnum.cliente
    email: Optional[str] = None
    telefone: Optional[str] = None
    celular: Optional[str] = None
    indicador_ie: Optional[CadastroIndicadorIEEnum] = CadastroIndicadorIEEnum.nao_contribuinte
    inscricao_estadual: Optional[str] = None
    cep: Optional[str] = Field(None, max_length=9)
    estado: Optional[EstadoEnum] = None
    cidade: Optional[str] = None
    cidade_ibge: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    situacao: bool = True
    delivery_method_id_intelipost: Optional[str] = None

class CadastroCreate(CadastroBase):
    pass

class CadastroUpdate(BaseModel):
    cpf_cnpj: Optional[str] = Field(None, max_length=18)
    nome_razao: Optional[str] = None
    fantasia: Optional[str] = None
    tipo_pessoa: Optional[CadastroTipoPessoaEnum] = None
    tipo_cadastro: Optional[CadastroTipoCadastroEnum] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    celular: Optional[str] = None
    indicador_ie: Optional[CadastroIndicadorIEEnum] = None
    inscricao_estadual: Optional[str] = None
    cep: Optional[str] = Field(None, max_length=9)
    estado: Optional[EstadoEnum] = None
    cidade: Optional[str] = None
    cidade_ibge: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    situacao: Optional[bool] = None
    delivery_method_id_intelipost: Optional[str] = None

class Cadastro(CadastroBase):  # RENOMEADO de CadastroRead para Cadastro
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 4. Schemas de Embalagem ---

class EmbalagemBase(BaseModel):
    descricao: str
    regras: Optional[Dict[str, Any]] = None
    situacao: bool = True

class EmbalagemCreate(EmbalagemBase):
    pass

class EmbalagemUpdate(BaseModel):
    descricao: Optional[str] = None
    regras: Optional[Dict[str, Any]] = None
    situacao: Optional[bool] = None

class Embalagem(EmbalagemBase):  # RENOMEADO de EmbalagemRead para Embalagem
    id: int
    id_empresa: int

    class Config:
        from_attributes = True

# --- 5. Schemas de Produto ---

class ProdutoBase(BaseModel):
    sku: str
    gtin: Optional[str] = None
    variacoes: Optional[List[str]] = []
    descricao: str
    unidade: ProdutoUnidadeEnum = ProdutoUnidadeEnum.un
    tipo_produto: ProdutoTipoEnum = ProdutoTipoEnum.mercadoria_revenda
    grupo: Optional[str] = None
    subgrupo1: Optional[str] = None
    subgrupo2: Optional[str] = None
    subgrupo3: Optional[str] = None
    subgrupo4: Optional[str] = None
    subgrupo5: Optional[str] = None
    url_imagem: Optional[str] = None
    classificacao_fiscal: Optional[str] = None
    origem: ProdutoOrigemEnum = ProdutoOrigemEnum.nacional
    ncm: Optional[str] = None
    cest: Optional[str] = None
    anp: Optional[str] = None
    escala_relevante: bool = True
    cnpj_fabricante: Optional[str] = None
    ipi_aliquota: Decimal = Field(0)
    preco: Optional[Decimal] = Field(None)
    custo: Optional[Decimal] = Field(None)
    estoque_negativo: bool = False
    peso: Optional[Decimal] = Field(None)
    altura: Optional[Decimal] = Field(None)
    largura: Optional[Decimal] = Field(None)
    comprimento: Optional[Decimal] = Field(None)
    situacao: bool = True
    
    id_embalagem: Optional[int] = None
    id_fornecedor: Optional[int] = None

class ProdutoCreate(ProdutoBase):
    pass

class ProdutoUpdate(BaseModel):
    sku: Optional[str] = None
    gtin: Optional[str] = None
    descricao: Optional[str] = None
    unidade: Optional[ProdutoUnidadeEnum] = None
    tipo_produto: Optional[ProdutoTipoEnum] = None
    grupo: Optional[str] = None
    subgrupo1: Optional[str] = None
    subgrupo2: Optional[str] = None
    subgrupo3: Optional[str] = None
    subgrupo4: Optional[str] = None
    subgrupo5: Optional[str] = None
    url_imagem: Optional[str] = None
    classificacao_fiscal: Optional[str] = None
    origem: Optional[ProdutoOrigemEnum] = None
    ncm: Optional[str] = None
    cest: Optional[str] = None
    anp: Optional[str] = None
    escala_relevante: Optional[bool] = None
    cnpj_fabricante: Optional[str] = None
    ipi_aliquota: Optional[Decimal] = Field(None)
    preco: Optional[Decimal] = Field(None)
    custo: Optional[Decimal] = Field(None)
    estoque_negativo: Optional[bool] = None
    peso: Optional[Decimal] = Field(None)
    altura: Optional[Decimal] = Field(None)
    largura: Optional[Decimal] = Field(None)
    comprimento: Optional[Decimal] = Field(None)
    situacao: Optional[bool] = None
    id_embalagem: Optional[int] = None
    id_fornecedor: Optional[int] = None

class Produto(ProdutoBase):  # RENOMEADO de ProdutoRead para Produto
    id: int
    id_empresa: int
    
    embalagem: Optional["Embalagem"] = None # Atualizada a referência
    fornecedor: Optional["Cadastro"] = None # Atualizada a referência
    
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

class NotaFiscalRecebida(BaseModel):
    id: int
    chave_acesso: Optional[str] = None
    nsu: Optional[str] = None
    tipo_documento: Optional[str] = None
    cnpj_emitente: Optional[str] = None
    nome_emitente: Optional[str] = None
    valor_total: Optional[Decimal] = None
    data_emissao: Optional[datetime] = None
    situacao_manifestacao: Optional[str] = "Pendente"
    ja_importado: bool = False

    class Config:
        from_attributes = True

class NotaFiscalRecebidaCreate(BaseModel):
    pass

class NotaFiscalRecebidaUpdate(BaseModel):
    ja_importado: Optional[bool] = None
    situacao_manifestacao: Optional[str] = None

Nfe_recebida = NotaFiscalRecebida
Nfe_recebidaCreate = NotaFiscalRecebidaCreate
Nfe_recebidaUpdate = NotaFiscalRecebidaUpdate

# --- 6. Schemas de Conta (Pagar/Receber) ---

class ContaBase(BaseModel):
    tipo_conta: ContaTipoEnum = ContaTipoEnum.a_receber
    situacao: ContaSituacaoEnum = ContaSituacaoEnum.em_aberto
    descricao: Optional[str] = None
    numero_conta: Optional[str] = None
    data_emissao: Optional[date] = None
    data_vencimento: Optional[date] = None # Corrigido de data_vendimento no models para data_vencimento
    data_baixa: Optional[date] = None
    id_classificacao_contabil: int
    caixa_destino_origem: Optional[str] = None
    observacoes: Optional[str] = None
    pagamento: Optional[FiscalPagamentoEnum] = None
    valor: Decimal = Field(...)
    
    id_fornecedor: int

class ContaCreate(ContaBase):
    pass

class ContaUpdate(BaseModel):
    tipo_conta: Optional[ContaTipoEnum] = None
    situacao: Optional[ContaSituacaoEnum] = None
    descricao: Optional[str] = None
    numero_conta: Optional[str] = None
    data_emissao: Optional[date] = None
    data_vencimento: Optional[date] = None
    data_baixa: Optional[date] = None
    id_classificacao_contabil: Optional[int] = None
    caixa_destino_origem: Optional[str] = None
    observacoes: Optional[str] = None
    pagamento: Optional[FiscalPagamentoEnum] = None
    valor: Optional[Decimal] = Field(None)
    id_fornecedor: Optional[int] = None

class Conta(ContaBase):  # RENOMEADO de ContaRead para Conta
    id: int
    id_empresa: int
    id_classificacao_contabil: Optional[int] = None
    
    fornecedor: Optional["Cadastro"] = None # Atualizada a referência
    classificacao_contabil: Optional["ClassificacaoContabil"] = None
    
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 7. Schemas de Estoque ---

class EstoqueBase(BaseModel):
    id_produto: int
    lote: Optional[str] = None
    deposito: Optional[str] = None
    rua: Optional[str] = None
    nivel: Optional[str] = None
    cor: Optional[str] = None
    quantidade: int
    situacao: EstoqueSituacaoEnum = EstoqueSituacaoEnum.entrada
    observacoes: Optional[str] = None

class EstoqueCreate(EstoqueBase):
    pass

class EstoqueUpdate(BaseModel):
    id_produto: Optional[int] = None
    lote: Optional[str] = None
    deposito: Optional[str] = None
    rua: Optional[str] = None
    nivel: Optional[str] = None
    cor: Optional[str] = None
    quantidade: Optional[int] = None
    situacao: Optional[EstoqueSituacaoEnum] = None
    observacoes: Optional[str] = None

class Estoque(EstoqueBase):  # RENOMEADO de EstoqueRead para Estoque
    id: int
    id_empresa: int
    
    produto: "Produto" # Atualizada a referência
    
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 8. Schemas de Pedido ---

class PedidoBase(BaseModel):
    data_orcamento: Optional[date] = None
    data_validade: Optional[date] = None
    data_pedido: Optional[date] = None
    data_despacho: Optional[date] = None
    data_entrega: Optional[date] = None
    data_finalizacao: Optional[date] = None
    origem_venda: Optional[str] = None
    indicador_presenca: Optional[PedidoIndicadorPresencaEnum] = PedidoIndicadorPresencaEnum.presencial
    modalidade_frete: Optional[PedidoModalidadeFreteEnum] = None
    valor_frete: Optional[Decimal] = Field(None)
    ipi_frete: Optional[Decimal] = Field(None)
    total_frete: Optional[Decimal] = Field(None)
    
    delivery_method_id_intelipost: Optional[str] = None
    quote_id: Optional[str] = None
    intelipost_id: Optional[str] = None

    veiculo_placa: Optional[str] = None
    veiculo_uf: Optional[EstadoEnum] = None
    veiculo_antt: Optional[str] = None
    
    volumes_quantidade: Optional[int] = None
    volumes_especie: Optional[str] = None
    volumes_marca: Optional[str] = None
    volumes_numeracao: Optional[str] = None
    volumes_peso_bruto: Optional[Decimal] = Field(None)
    volumes_peso_liquido: Optional[Decimal] = Field(None)
    
    # Campos de Endereço de Entrega
    endereco_cep: Optional[str] = Field(None, max_length=9)
    endereco_estado: Optional[EstadoEnum] = None
    endereco_cidade: Optional[str] = None
    endereco_bairro: Optional[str] = None
    endereco_logradouro: Optional[str] = None
    endereco_numero: Optional[str] = None
    endereco_complemento: Optional[str] = None
    
    total: Optional[Decimal] = Field(None)
    desconto: Optional[Decimal] = Field(None)
    total_desconto: Optional[Decimal] = Field(None)
    itens: Optional[List[Dict[str, Any]]] = None
    pagamento: Optional[FiscalPagamentoEnum] = None
    pagamento_descricao: Optional[str] = None
    caixa_destino_origem: Optional[str] = None
    observacao: Optional[str] = None
    observacoes_nf: Optional[str] = None
    ordem_finalizacao: Optional[Decimal] = Field(None)
    tipo_operacao: Optional[RegraTipoOperacaoEnum] = RegraTipoOperacaoEnum.venda_mercadoria
    retiradas_detalhadas: Optional[List[Dict[str, Any]]] = None
    
    numero_nf: Optional[str] = None
    data_nf: Optional[date] = None
    chave_acesso: Optional[str] = None
    chave_nfe_referencia: Optional[str] = None
    protocolo_autorizacao: Optional[str] = None
    status_sefaz: Optional[str] = None
    xml_autorizado: Optional[str] = None
    pdf_danfe: Optional[str] = None
    pdf_cce: Optional[str] = None
    modelo_fiscal: Optional[int] = 55
    
    situacao: PedidoSituacaoEnum = PedidoSituacaoEnum.orcamento
    
    id_cliente: Optional[int] = None
    id_vendedor: Optional[int] = None
    id_transportadora: Optional[int] = None
    
    meli_xml_enviado: Optional[bool] = False
    intelipost_criado: Optional[bool] = False
    email_enviado: Optional[bool] = False

class PedidoCreate(PedidoBase):
    pass

class PedidoUpdate(BaseModel):
    data_orcamento: Optional[date] = None
    data_validade: Optional[date] = None
    data_pedido: Optional[date] = None
    data_despacho: Optional[date] = None
    data_entrega: Optional[date] = None
    data_finalizacao: Optional[date] = None
    origem_venda: Optional[str] = None
    indicador_presenca: Optional[PedidoIndicadorPresencaEnum] = None
    modalidade_frete: Optional[PedidoModalidadeFreteEnum] = None
    valor_frete: Optional[Decimal] = Field(None)
    ipi_frete: Optional[Decimal] = Field(None)
    total_frete: Optional[Decimal] = Field(None)
    
    delivery_method_id_intelipost: Optional[str] = None
    quote_id: Optional[str] = None
    intelipost_id: Optional[str] = None

    veiculo_placa: Optional[str] = None
    veiculo_uf: Optional[EstadoEnum] = None
    veiculo_antt: Optional[str] = None
    
    volumes_quantidade: Optional[int] = None
    volumes_especie: Optional[str] = None
    volumes_marca: Optional[str] = None
    volumes_numeracao: Optional[str] = None
    volumes_peso_bruto: Optional[Decimal] = Field(None)
    volumes_peso_liquido: Optional[Decimal] = Field(None)
    
    total: Optional[Decimal] = Field(None)
    desconto: Optional[Decimal] = Field(None)
    total_desconto: Optional[Decimal] = Field(None)
    itens: Optional[List[Dict[str, Any]]] = None
    pagamento: Optional[FiscalPagamentoEnum] = None
    pagamento_descricao: Optional[str] = None
    caixa_destino_origem: Optional[str] = None
    observacao: Optional[str] = None
    observacoes_nf: Optional[str] = None
    ordem_finalizacao: Optional[Decimal] = Field(None)
    tipo_operacao: Optional[RegraTipoOperacaoEnum] = None
    retiradas_detalhadas: Optional[List[Dict[str, Any]]] = None
    
    numero_nf: Optional[str] = None
    data_nf: Optional[date] = None
    chave_acesso: Optional[str] = None
    chave_nfe_referencia: Optional[str] = None
    protocolo_autorizacao: Optional[str] = None
    status_sefaz: Optional[str] = None
    xml_autorizado: Optional[str] = None
    pdf_danfe: Optional[str] = None
    pdf_cce: Optional[str] = None
    modelo_fiscal: Optional[int] = None
    
    situacao: Optional[PedidoSituacaoEnum] = None
    id_cliente: Optional[int] = None
    id_vendedor: Optional[int] = None
    id_transportadora: Optional[int] = None

    # Campos de Endereço de Entrega
    endereco_cep: Optional[str] = Field(None, max_length=9)
    endereco_estado: Optional[EstadoEnum] = None
    endereco_cidade: Optional[str] = None
    endereco_bairro: Optional[str] = None
    endereco_logradouro: Optional[str] = None
    endereco_numero: Optional[str] = None
    endereco_complemento: Optional[str] = None
    
    meli_xml_enviado: Optional[bool] = None
    intelipost_criado: Optional[bool] = None
    email_enviado: Optional[bool] = None

class Pedido(PedidoBase):  # RENOMEADO de PedidoRead para Pedido
    id: int
    id_empresa: int
    
    cliente: Optional["Cadastro"] = None # Atualizada a referência
    vendedor: Optional["Cadastro"] = None # Atualizada a referência
    transportadora: Optional["Cadastro"] = None # Atualizada a referência
    
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 9. Schemas de Regra Tributária ---

class TributacaoBase(BaseModel):
    descricao: Optional[str] = None
    regime_emitente: Optional[RegraRegimeEmitenteEnum] = None
    tipo_operacao: Optional[RegraTipoOperacaoEnum] = None
    tipo_cliente: Optional[RegraTipoClienteEnum] = None
    localizacao_destino: Optional[RegraLocalizacaoDestinoEnum] = None
    origem_produto: Optional[FiscalOrigemEnum] = None
    ncm_chave: Optional[str] = None
    prioridade: int = 10
    
    cfop: Optional[str] = None
    icms_cst: Optional[FiscalICMSCSTEnum] = None
    icms_reducao_bc_perc: Decimal = Field(0)
    icms_p_dif: Decimal = Field(0)
    icms_st_cst: Optional[FiscalICMSCSTEnum] = None
    icms_st_mva_perc: Decimal = Field(0)
    icms_st_aliquota: Decimal = Field(0)
    fcp_aliquota: Decimal = Field(0)
    ipi_cst: Optional[FiscalIPICSTEnum] = None
    ipi_codigo_enquadramento: Optional[str] = None
    pis_cst: Optional[FiscalPISCOFINSCSTEnum] = None
    pis_aliquota: Decimal = Field(0)
    cofins_cst: Optional[FiscalPISCOFINSCSTEnum] = None
    cofins_aliquota: Decimal = Field(0)
    cbenef: Optional[str] = None
    ibs_aliquota: Decimal = Field(0)
    cbs_aliquota: Decimal = Field(0)
    is_aliquota: Decimal = Field(0)
    reforma_cst: Optional[str] = '000'
    reforma_c_class_trib: Optional[str] = '000001'
    
    fcp_aliquota_destino: Decimal = Field(0)
    
    regras_uf: Optional[Dict[str, Any]] = Field(default_factory=dict)
    
    situacao: bool = True

class TributacaoCreate(TributacaoBase):
    pass

class TributacaoUpdate(BaseModel):
    descricao: Optional[str] = None
    regime_emitente: Optional[RegraRegimeEmitenteEnum] = None
    tipo_operacao: Optional[RegraTipoOperacaoEnum] = None
    tipo_cliente: Optional[RegraTipoClienteEnum] = None
    localizacao_destino: Optional[RegraLocalizacaoDestinoEnum] = None
    origem_produto: Optional[FiscalOrigemEnum] = None
    ncm_chave: Optional[str] = None
    prioridade: Optional[int] = None
    
    cfop: Optional[str] = None
    icms_cst: Optional[FiscalICMSCSTEnum] = None
    icms_reducao_bc_perc: Optional[Decimal] = Field(None)
    icms_p_dif: Optional[Decimal] = Field(None)
    icms_st_cst: Optional[FiscalICMSCSTEnum] = None
    icms_st_mva_perc: Optional[Decimal] = Field(None)
    icms_st_aliquota: Optional[Decimal] = Field(None)
    fcp_aliquota: Optional[Decimal] = Field(None)
    ipi_cst: Optional[FiscalIPICSTEnum] = None
    ipi_codigo_enquadramento: Optional[str] = None
    pis_cst: Optional[FiscalPISCOFINSCSTEnum] = None
    pis_aliquota: Optional[Decimal] = Field(None)
    cofins_cst: Optional[FiscalPISCOFINSCSTEnum] = None
    cofins_aliquota: Optional[Decimal] = Field(None)
    cbenef: Optional[str] = None
    ibs_aliquota: Optional[Decimal] = Field(None)
    cbs_aliquota: Optional[Decimal] = Field(None)
    is_aliquota: Optional[Decimal] = Field(None)
    reforma_cst: Optional[str] = None
    reforma_c_class_trib: Optional[str] = None
    
    fcp_aliquota_destino: Optional[Decimal] = Field(None)
    
    regras_uf: Optional[Dict[str, Any]] = {}
    
    situacao: Optional[bool] = None

class Tributacao(TributacaoBase):  # RENOMEADO de TributacaoRead para Tributacao
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 13. Schemas de Classificação Contábil ---

class ClassificacaoContabilBase(BaseModel):
    grupo: str
    descricao: str
    tipo: str
    tipo_movimentacao: str = "Saída"
    considerar: bool = True

class ClassificacaoContabilCreate(ClassificacaoContabilBase):
    pass

class ClassificacaoContabilUpdate(BaseModel):
    grupo: Optional[str] = None
    descricao: Optional[str] = None
    tipo: Optional[str] = None
    tipo_movimentacao: Optional[str] = None
    considerar: Optional[bool] = None

class ClassificacaoContabil(ClassificacaoContabilBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 10. Schemas de IntelipostConfiguracao ---

class IntelipostConfiguracaoBase(BaseModel):
    api_key: str
    origin_zip_code: str = Field(..., max_length=9)
    origin_warehouse_code: Optional[str] = None

class IntelipostConfiguracaoCreate(IntelipostConfiguracaoBase):
    pass

class IntelipostConfiguracaoUpdate(BaseModel):
    api_key: Optional[str] = None
    origin_zip_code: Optional[str] = Field(None, max_length=9)
    origin_warehouse_code: Optional[str] = None

class IntelipostConfiguracao(IntelipostConfiguracaoBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# Aliases para compatibilidade com o dispatcher
Intelipost_configuracao = IntelipostConfiguracao
Intelipost_configuracaoCreate = IntelipostConfiguracaoCreate
Intelipost_configuracaoUpdate = IntelipostConfiguracaoUpdate

# --- Schemas de Outras Empresas ---

class OutrasEmpresasConfiguracaoBase(BaseModel):
    nome: str
    email: str
    senha: str
    ativo: bool = True
    token: Optional[str] = None
    token_expiracao: Optional[datetime] = None

class OutrasEmpresasConfiguracaoCreate(OutrasEmpresasConfiguracaoBase):
    pass

class OutrasEmpresasConfiguracaoUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    senha: Optional[str] = None
    ativo: Optional[bool] = None
    token: Optional[str] = None
    token_expiracao: Optional[datetime] = None

class OutrasEmpresasConfiguracao(OutrasEmpresasConfiguracaoBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

Outra_empresa_configuracao = OutrasEmpresasConfiguracao
Outra_empresa_configuracaoCreate = OutrasEmpresasConfiguracaoCreate
Outra_empresa_configuracaoUpdate = OutrasEmpresasConfiguracaoUpdate
Outras_empresas_configuracao = OutrasEmpresasConfiguracao
Outras_empresas_configuracaoCreate = OutrasEmpresasConfiguracaoCreate
Outras_empresas_configuracaoUpdate = OutrasEmpresasConfiguracaoUpdate


class MeliConfiguracaoBase(BaseModel):
    app_id: Optional[str] = None
    client_secret: Optional[str] = None
    redirect_uri: Optional[str] = None
    cliente_padrao_id: Optional[int] = None
    vendedor_padrao_id: Optional[int] = None
    situacao_pedido_inicial: Optional[str] = "Orçamento"
    caixa_padrao: Optional[str] = None

class MeliConfiguracaoCreate(MeliConfiguracaoBase):
    pass

class MeliConfiguracaoUpdate(MeliConfiguracaoBase):
    pass

class MeliConfiguracao(MeliConfiguracaoBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Schema "Virtual" para Listagem de Pedidos ML ---
# Este schema não reflete uma tabela do banco, mas sim o retorno da API do ML formatado
class MeliPedidoListItem(BaseModel):
    id: str  # ID do ML (ex: "200000333")
    date_created: datetime
    total_amount: float
    status: str
    buyer_nickname: str
    item_title: str # Primeiro item ou resumo
    ja_importado: bool = False # Flag para o frontend bloquear importação duplicada

# Aliases para o Dispatcher
Meli_configuracao = MeliConfiguracao
Meli_configuracoes = MeliConfiguracao
Meli_configuracaoCreate = MeliConfiguracaoCreate
Meli_configuracaoUpdate = MeliConfiguracaoUpdate


class MagentoConfiguracaoBase(BaseModel):
    base_url: str
    consumer_key: str
    consumer_secret: str
    access_token: str
    token_secret: str
    store_view_code: Optional[str] = 'default'
    vendedor_padrao_id: Optional[int] = None
    situacao_pedido_inicial: Optional[PedidoSituacaoEnum] = PedidoSituacaoEnum.orcamento
    payment_method_contains: Optional[str] = None
    filtros_padrao: Optional[List[Dict[str, Any]]] = []

class MagentoConfiguracaoCreate(MagentoConfiguracaoBase):
    pass

class MagentoConfiguracaoUpdate(MagentoConfiguracaoBase):
    base_url: Optional[str] = None
    consumer_key: Optional[str] = None
    consumer_secret: Optional[str] = None
    access_token: Optional[str] = None
    token_secret: Optional[str] = None
    store_view_code: Optional[str] = None
    vendedor_padrao_id: Optional[int] = None
    situacao_pedido_inicial: Optional[PedidoSituacaoEnum] = None
    payment_method_contains: Optional[str] = None
    filtros_padrao: Optional[List[Dict[str, Any]]] = None

class MagentoConfiguracao(MagentoConfiguracaoBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Schema "Virtual" para Listagem de Pedidos Magento (Proxy) ---
class MagentoPedidoListItem(BaseModel):
    entity_id: int        # ID interno do Magento (Chave Primária)
    increment_id: str     # Número do Pedido visível (ex: 000000001)
    created_at: datetime
    grand_total: float
    status: str
    customer_name: str
    items_count: int
    payment_method: Optional[str] = None
    ja_importado: bool = False

# Aliases para o Dispatcher
Magento_configuracao = MagentoConfiguracao
Magento_configuracoes = MagentoConfiguracao
Magento_configuracaoCreate = MagentoConfiguracaoCreate
Magento_configuracaoUpdate = MagentoConfiguracaoUpdate

class TiktokConfiguracaoBase(BaseModel):
    app_key: str
    app_secret: str
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    shop_id: Optional[str] = None
    vendedor_padrao_id: Optional[int] = None
    situacao_pedido_inicial: Optional[PedidoSituacaoEnum] = PedidoSituacaoEnum.orcamento
    filtros_padrao: Optional[List[Dict[str, Any]]] = []

class TiktokConfiguracaoCreate(TiktokConfiguracaoBase):
    pass

class TiktokConfiguracaoUpdate(TiktokConfiguracaoBase):
    app_key: Optional[str] = None
    app_secret: Optional[str] = None

class TiktokConfiguracao(TiktokConfiguracaoBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

class TiktokPedidoListItem(BaseModel):
    order_id: str
    create_time: datetime
    order_status: str
    payment_method: Optional[str] = None
    total_amount: float
    buyer_email: Optional[str] = None
    ja_importado: bool = False

Tiktok_configuracao = TiktokConfiguracao
Tiktok_configuracoes = TiktokConfiguracao
Tiktok_configuracaoCreate = TiktokConfiguracaoCreate
Tiktok_configuracaoUpdate = TiktokConfiguracaoUpdate

# Aliases para ClassificacaoContabil
Classificacao_contabil = ClassificacaoContabil
Classificacao_contabilCreate = ClassificacaoContabilCreate
Classificacao_contabilUpdate = ClassificacaoContabilUpdate

class ElasticEmailConfiguracaoBase(BaseModel):
    api_key: str
    from_email: str
    from_name: Optional[str] = None
    ativo: bool = True

class ElasticEmailConfiguracaoCreate(ElasticEmailConfiguracaoBase):
    pass

class ElasticEmailConfiguracaoUpdate(ElasticEmailConfiguracaoBase):
    pass

class ElasticEmailConfiguracao(ElasticEmailConfiguracaoBase):
    id: int
    id_empresa: int

    class Config:
        from_attributes = True

Elastic_email_configuracao = ElasticEmailConfiguracao
Elastic_email_configuracoes = ElasticEmailConfiguracao
Elastic_email_configuracaoCreate = ElasticEmailConfiguracaoCreate
Elastic_email_configuracaoUpdate = ElasticEmailConfiguracaoUpdate


# --- Schemas de AtendaiConfiguracao ---

class AtendaiConfiguracaoBase(BaseModel):
    url_webhook: str
    webhook_token: Optional[str] = None
    ativo: bool = True

class AtendaiConfiguracaoCreate(AtendaiConfiguracaoBase):
    pass

class AtendaiConfiguracaoUpdate(BaseModel):
    url_webhook: Optional[str] = None
    webhook_token: Optional[str] = None
    ativo: Optional[bool] = None

class AtendaiConfiguracao(AtendaiConfiguracaoBase):
    id: int
    id_empresa: int
    criado_em: Optional[datetime] = None
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

Atendai_configuracao = AtendaiConfiguracao
Atendai_configuracoes = AtendaiConfiguracao
Atendai_configuracaoCreate = AtendaiConfiguracaoCreate
Atendai_configuracaoUpdate = AtendaiConfiguracaoUpdate



# --- Schemas de EmailRegra ---

class EmailRegraBase(BaseModel):
    nome: str
    trigger: str  # ex: "Orçamento → Aprovação"
    subject: str = "Atualização do Pedido {pedido_id}"
    body_html: Optional[str] = None
    anexos: List[str] = []
    ativo: bool = True

class EmailRegraCreate(EmailRegraBase):
    pass

class EmailRegraUpdate(BaseModel):
    nome: Optional[str] = None
    trigger: Optional[str] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    anexos: Optional[List[str]] = None
    ativo: Optional[bool] = None

class EmailRegra(EmailRegraBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# Aliases para o dispatcher
Email_regra = EmailRegra
Email_regras = EmailRegra
Email_regraCreate = EmailRegraCreate
Email_regraUpdate = EmailRegraUpdate

# --- 11. Schemas de Opções de Campos (CreatableSelect) ---

class OpcaoCampoBase(BaseModel):
    model_name: str
    field_name: str
    valor: str

class OpcaoCampoCreate(OpcaoCampoBase):
    pass

class OpcaoCampoUpdate(BaseModel):
    valor: str

class OpcaoCampo(OpcaoCampoBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 12. Schemas de Preferências de Usuário ---

class UsuarioPreferenciaBase(BaseModel):
    model_name: str
    config: Dict[str, Any]

class UsuarioPreferencia(UsuarioPreferenciaBase):
    id: int
    id_usuario: int

# --- 13. Schemas de Dashboard Customizável ---

class DashboardPreferenciaUpdate(BaseModel):
    layout: List[Dict[str, Any]]
    cards_config: Dict[str, Any]

class CardQuery(BaseModel):
    modelo: str
    tipo: str
    operacao: str
    campo: str
    agrupar_por: Optional[str] = None
    formato: Optional[str] = "numero"
    filtros: Optional[List[Dict[str, Any]]] = []
    titulo: Optional[str] = ""
    colunas: Optional[List[str]] = []


# --- 14. Schemas de Relatórios ---

class RelatorioBase(BaseModel):
    nome: str
    descricao: Optional[str] = None
    modelo: str
    config: Optional[Dict[str, Any]] = {}

class RelatorioCreate(RelatorioBase):
    pass

class RelatorioUpdate(RelatorioBase):
    pass

class Relatorio(RelatorioBase):
    id: int
    id_empresa: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- Atualização de Referências (AGORA USA OS NOMES CURTOS) ---
def update_all_forward_refs():
    """Chame esta função no final do seu arquivo schemas.py."""
    # O Pydantic V2 usa model_rebuild() para resolver referências aninhadas
    Empresa.model_rebuild()
    Usuario.model_rebuild()
    Perfil.model_rebuild()
    Cadastro.model_rebuild()
    Embalagem.model_rebuild()
    Produto.model_rebuild()
    Conta.model_rebuild()
    Estoque.model_rebuild()
    Pedido.model_rebuild()
    Tributacao.model_rebuild()
    ClassificacaoContabil.model_rebuild()
    IntelipostConfiguracao.model_rebuild()
    MeliConfiguracaoBase.model_rebuild()
    MagentoConfiguracaoBase.model_rebuild()
    TiktokConfiguracaoBase.model_rebuild()
    OpcaoCampo.model_rebuild()
    UsuarioPreferencia.model_rebuild()
    Relatorio.model_rebuild()
    ElasticEmailConfiguracao.model_rebuild()
    AtendaiConfiguracao.model_rebuild()
    NotaFiscalRecebida.model_rebuild()
    EmailRegra.model_rebuild()
    
update_all_forward_refs()