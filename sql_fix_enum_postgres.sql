-- Script Corrigido para PostgreSQL ENUM

-- 1. Renomear o tipo antigo
ALTER TYPE pedidosituacaoenum RENAME TO pedidosituacaoenum_old;

-- 2. Criar o novo tipo sem o valor 'Finalizado'
CREATE TYPE pedidosituacaoenum AS ENUM (
    'Orçamento', 
    'Aprovação', 
    'Programação', 
    'Produção', 
    'Embalagem', 
    'Faturamento', 
    'Expedição', 
    'Despachado', 
    'Cancelado'
);

-- 3. Atualizar registros 'Finalizado' para 'Despachado' ANTES da conversão de tipo
-- Nota: Usamos ::pedidosituacaoenum_old porque a coluna ainda é do tipo antigo
UPDATE pedidos 
SET situacao = 'Despachado'::text::pedidosituacaoenum_old 
WHERE situacao::text = 'Finalizado';

-- 4. Converter as colunas das tabelas para o novo tipo ENUM
-- Tabela: pedidos
ALTER TABLE pedidos 
    ALTER COLUMN situacao TYPE pedidosituacaoenum 
    USING situacao::text::pedidosituacaoenum;

-- Tabela: meli_configuracoes (garantindo que não haja 'Finalizado' antes)
UPDATE meli_configuracoes SET situacao_pedido_inicial = 'Orçamento'::text::pedidosituacaoenum_old WHERE situacao_pedido_inicial::text = 'Finalizado';

ALTER TABLE meli_configuracoes 
    ALTER COLUMN situacao_pedido_inicial TYPE pedidosituacaoenum 
    USING situacao_pedido_inicial::text::pedidosituacaoenum;

-- Tabela: magento_configuracoes (garantindo que não haja 'Finalizado' antes)
UPDATE magento_configuracoes SET situacao_pedido_inicial = 'Orçamento'::text::pedidosituacaoenum_old WHERE situacao_pedido_inicial::text = 'Finalizado';

ALTER TABLE magento_configuracoes 
    ALTER COLUMN situacao_pedido_inicial TYPE pedidosituacaoenum 
    USING situacao_pedido_inicial::text::pedidosituacaoenum;

-- 5. Agora podemos remover o tipo antigo com segurança
DROP TYPE pedidosituacaoenum_old;
