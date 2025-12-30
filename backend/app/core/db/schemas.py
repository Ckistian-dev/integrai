from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any, Dict, Type
from datetime import datetime
from decimal import Decimal

# Importar Enums do models.py para garantir consistência
# Assumindo que os Enums estão acessíveis (via .models ou definidos localmente)
from .models import (
    EmpresaCRTEnum, EmpresaEmissaoEnum, UsuarioPerfilEnum, 
    CadastroTipoPessoaEnum, CadastroTipoCadastroEnum, ProdutoUnidadeEnum,
    ProdutoTipoEnum, ProdutoOrigemEnum, ContaTipoEnum, ContaSituacaoEnum,
    ContaPlanoContasEnum, ContaCaixaEnum, EstoqueSituacaoEnum, PedidoSituacaoEnum,
    RegraRegimeEmitenteEnum, RegraTipoOperacaoEnum, RegraTipoClienteEnum,
    RegraLocalizacaoDestinoEnum, CadastroIndicadorIEEnum
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
    perfil: Optional[UsuarioPerfilEnum] = None
    email: Optional[str] = None

class Page(BaseModel):
    """Schema genérico para paginação."""
    items: List[Any]
    total_count: int

    class Config:
        from_attributes = True

# --- Schemas de Metadados ---
class FieldMetadata(BaseModel):
    name: str
    label: str
    type: str
    required: bool
    options: Optional[List[Dict[str, Any]]] = None
    format_mask: Optional[str] = None
    tab: Optional[str] = None
    foreign_key_model: Optional[str] = None # Modelo que a FK aponta (ex: "cadastros")
    foreign_key_label_field: Optional[str] = None # Campo de label (ex: "nome_razao")

class ModelMetadata(BaseModel):
    model_name: str
    display_name: str
    display_field: Optional[str] = None # O campo principal de display do modelo (ex: "nome_razao")
    fields: List[FieldMetadata]


# --- 1. Schemas da Empresa ---

class EmpresaBase(BaseModel):
    cnpj: str = Field(..., max_length=18)
    razao: str
    fantasia: Optional[str] = None
    inscricao_estadual: Optional[str] = None
    cep: str = Field(..., max_length=9)
    estado: Optional[str] = Field(None, max_length=2)
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    cnae: Optional[str] = None
    crt: EmpresaCRTEnum = EmpresaCRTEnum.simples_nacional
    emissao: EmpresaEmissaoEnum = EmpresaEmissaoEnum.desenvolvimento
    situacao: bool = True

class EmpresaCreate(EmpresaBase):
    pass

class EmpresaUpdate(BaseModel):
    cnpj: Optional[str] = Field(None, max_length=18)
    razao: Optional[str] = None
    fantasia: Optional[str] = None
    inscricao_estadual: Optional[str] = None
    cep: Optional[str] = Field(None, max_length=9)
    estado: Optional[str] = Field(None, max_length=2)
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    cnae: Optional[str] = None
    crt: Optional[EmpresaCRTEnum] = None
    emissao: Optional[EmpresaEmissaoEnum] = None
    situacao: Optional[bool] = None

class Empresa(EmpresaBase):  # RENOMEADO de EmpresaRead para Empresa
    id: int
    criado_em: datetime
    atualizado_em: Optional[datetime] = None

    class Config:
        from_attributes = True

# --- 2. Schemas do Usuário ---

class UsuarioBase(BaseModel):
    nome: str
    email: str
    perfil: UsuarioPerfilEnum = UsuarioPerfilEnum.vendedor
    situacao: bool = True

class UsuarioCreate(BaseModel):
    nome: str
    email: str
    senha: str = Field(..., min_length=8)
    perfil: UsuarioPerfilEnum = UsuarioPerfilEnum.vendedor
    situacao: bool = True

class UsuarioUpdate(BaseModel):
    nome: Optional[str] = None
    email: Optional[str] = None
    senha: Optional[str] = Field(None, min_length=8)
    perfil: Optional[UsuarioPerfilEnum] = None
    situacao: Optional[bool] = None

class Usuario(UsuarioBase):  # RENOMEADO de UsuarioRead para Usuario
    id: int
    id_empresa: int
    situacao: Optional[bool] = None
    criado_em: datetime
    atualizado_em: Optional[datetime] = None
    empresa: "Empresa" # Atualizada a referência aninhada

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
    estado: Optional[str] = Field(None, max_length=2)
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    situacao: bool = True

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
    estado: Optional[str] = Field(None, max_length=2)
    cidade: Optional[str] = None
    bairro: Optional[str] = None
    logradouro: Optional[str] = None
    numero: Optional[str] = None
    complemento: Optional[str] = None
    situacao: Optional[bool] = None

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
    cfop: Optional[str] = None
    preco: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    custo: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    estoque_negativo: bool = False
    peso: Optional[Decimal] = Field(None, max_digits=10, decimal_places=3)
    altura: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    largura: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    comprimento: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
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
    cfop: Optional[str] = None
    preco: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    custo: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    estoque_negativo: Optional[bool] = None
    peso: Optional[Decimal] = Field(None, max_digits=10, decimal_places=3)
    altura: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    largura: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    comprimento: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
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

# --- 6. Schemas de Conta (Pagar/Receber) ---

class ContaBase(BaseModel):
    tipo_conta: ContaTipoEnum = ContaTipoEnum.a_receber
    situacao: ContaSituacaoEnum = ContaSituacaoEnum.em_aberto
    descricao: Optional[str] = None
    numero_conta: Optional[int] = None
    data_emissao: Optional[datetime] = None
    data_vencimento: Optional[datetime] = None # Corrigido de data_vendimento no models para data_vencimento
    data_baixa: Optional[datetime] = None
    plano_contas: ContaPlanoContasEnum = ContaPlanoContasEnum.despesas
    caixa_destino_origem: ContaCaixaEnum = ContaCaixaEnum.sicredi
    observacoes: Optional[str] = None
    pagamento: Optional[str] = None
    valor: Decimal = Field(..., max_digits=10, decimal_places=2)
    
    id_fornecedor: Optional[int] = None

class ContaCreate(ContaBase):
    pass

class ContaUpdate(BaseModel):
    tipo_conta: Optional[ContaTipoEnum] = None
    situacao: Optional[ContaSituacaoEnum] = None
    descricao: Optional[str] = None
    numero_conta: Optional[int] = None
    data_emissao: Optional[datetime] = None
    data_vencimento: Optional[datetime] = None
    data_baixa: Optional[datetime] = None
    plano_contas: Optional[ContaPlanoContasEnum] = None
    caixa_destino_origem: Optional[ContaCaixaEnum] = None
    observacoes: Optional[str] = None
    pagamento: Optional[str] = None
    valor: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    id_fornecedor: Optional[int] = None

class Conta(ContaBase):  # RENOMEADO de ContaRead para Conta
    id: int
    id_empresa: int
    
    fornecedor: Optional["Cadastro"] = None # Atualizada a referência
    
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
    situacao: EstoqueSituacaoEnum = EstoqueSituacaoEnum.disponivel

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
    data_emissao: Optional[datetime] = None
    data_validade: Optional[datetime] = None
    data_finalizacao: Optional[datetime] = None
    origem_venda: Optional[str] = None
    modalidade_frete: Optional[str] = None
    valor_frete: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    prazo_entrega: Optional[str] = None
    total: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    desconto: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    total_desconto: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    itens: Optional[List[Dict[str, Any]]] = None
    pagamento: Optional[str] = None
    observacao: Optional[str] = None
    ordem_finalizacao: Optional[str] = None
    endereco_expedicao: Optional[str] = None
    natureza_operacao: Optional[str] = None
    cfop: Optional[str] = None
    icms_cst: Optional[str] = None
    icms_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    icms_reducao_bc_perc: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    icms_st_cst: Optional[str] = None
    icms_st_mva_perc: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    icms_st_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    ipi_cst: Optional[str] = None
    ipi_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    pis_cst: Optional[str] = None
    pis_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    cofins_cst: Optional[str] = None
    cofins_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    
    situacao: PedidoSituacaoEnum = PedidoSituacaoEnum.orcamento
    
    id_cliente: Optional[int] = None
    id_vendedor: Optional[int] = None
    id_transportadora: Optional[int] = None

class PedidoCreate(PedidoBase):
    pass

class PedidoUpdate(BaseModel):
    data_emissao: Optional[datetime] = None
    data_validade: Optional[datetime] = None
    data_finalizacao: Optional[datetime] = None
    origem_venda: Optional[str] = None
    modalidade_frete: Optional[str] = None
    valor_frete: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    prazo_entrega: Optional[str] = None
    total: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    desconto: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    total_desconto: Optional[Decimal] = Field(None, max_digits=10, decimal_places=2)
    itens: Optional[List[Dict[str, Any]]] = None
    pagamento: Optional[str] = None
    observacao: Optional[str] = None
    ordem_finalizacao: Optional[str] = None
    endereco_expedicao: Optional[str] = None
    natureza_operacao: Optional[str] = None
    cfop: Optional[str] = None
    icms_cst: Optional[str] = None
    icms_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    icms_reducao_bc_perc: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    icms_st_cst: Optional[str] = None
    icms_st_mva_perc: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    icms_st_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    ipi_cst: Optional[str] = None
    ipi_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    pis_cst: Optional[str] = None
    pis_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    cofins_cst: Optional[str] = None
    cofins_aliquota: Optional[Decimal] = Field(None, max_digits=5, decimal_places=2)
    situacao: Optional[PedidoSituacaoEnum] = None
    id_cliente: Optional[int] = None
    id_vendedor: Optional[int] = None
    id_transportadora: Optional[int] = None

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
    origem_produto: Optional[str] = None
    ncm_chave: Optional[str] = None
    prioridade: int = 10
    situacao: bool = True

class TributacaoCreate(TributacaoBase):
    pass

class TributacaoUpdate(BaseModel):
    descricao: Optional[str] = None
    regime_emitente: Optional[RegraRegimeEmitenteEnum] = None
    tipo_operacao: Optional[RegraTipoOperacaoEnum] = None
    tipo_cliente: Optional[RegraTipoClienteEnum] = None
    localizacao_destino: Optional[RegraLocalizacaoDestinoEnum] = None
    origem_produto: Optional[str] = None
    ncm_chave: Optional[str] = None
    prioridade: Optional[int] = None
    situacao: Optional[bool] = None

class Tributacao(TributacaoBase):  # RENOMEADO de TributacaoRead para Tributacao
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
    Cadastro.model_rebuild()
    Embalagem.model_rebuild()
    Produto.model_rebuild()
    Conta.model_rebuild()
    Estoque.model_rebuild()
    Pedido.model_rebuild()
    Tributacao.model_rebuild()

update_all_forward_refs()