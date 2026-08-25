import logging
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
import app.core.db.models as models

logger = logging.getLogger(__name__)


def run_one_time_id_sequencial_migration(engine: Engine, base):
    """
    Migração robusta e IDEMPOTENTE para id_sequencial.

    Arquitetura:
    - FASE 1 (SEMPRE roda): ADD COLUMN id_sequencial - idempotente via IF NOT EXISTS
    - FASE 2 (SEMPRE roda): Preenche id_sequencial NULL via ROW_NUMBER - idempotente (só toca NULL)
    - FASE 3 (roda UMA VEZ): Migra FKs de .id -> .id_sequencial, marcada em schema_migrations
    
    Isso garante que mesmo após restore de backup, os dados sejam repreenchidos corretamente.
    """
    logger.info("[MIGRAÇÃO] Iniciando verificação...")

    MIGRATION_VERSION = "migration_id_sequencial_v1"

    tenant_tables = [
        "empresas", "perfil", "usuarios", "cadastros", "embalagens", "produtos",
        "contas", "estoque", "pedidos", "regras_tributarias", "classificacao_contabil",
        "intelipost_configuracoes", "meli_configuracoes", "meli_credentials",
        "magento_configuracoes", "tiktok_configuracoes", "shopee_configuracoes", "elastic_email_configuracoes",
        "atendai_configuracoes", "outras_empresas_configuracoes", "email_regras",
        "opcoes_campos", "relatorios", "nfe_recebidas"
    ]

    fk_mappings = [
        ("usuarios",             "id_perfil",                          "perfil"),
        ("produtos",             "id_embalagem",                       "embalagens"),
        ("produtos",             "id_fornecedor",                      "cadastros"),
        ("contas",               "id_fornecedor",                      "cadastros"),
        ("contas",               "id_classificacao_contabil",          "classificacao_contabil"),
        ("estoque",              "id_produto",                         "produtos"),
        ("pedidos",              "id_cliente",                         "cadastros"),
        ("pedidos",              "id_vendedor",                        "cadastros"),
        ("pedidos",              "id_transportadora",                  "cadastros"),
        ("empresas",             "id_classificacao_contabil_padrao",   "classificacao_contabil"),
        ("empresas",             "id_classificacao_contabil_cancelamento", "classificacao_contabil"),
        ("meli_configuracoes",   "cliente_padrao_id",                  "cadastros"),
        ("meli_configuracoes",   "vendedor_padrao_id",                 "cadastros"),
        ("magento_configuracoes","vendedor_padrao_id",                 "cadastros"),
        ("tiktok_configuracoes", "vendedor_padrao_id",                 "cadastros"),
        ("shopee_configuracoes", "vendedor_padrao_id",                 "cadastros"),
        ("usuario_preferencias", "id_usuario",                        "usuarios"),
        ("dashboard_preferencias","id_usuario",                       "usuarios"),
    ]

    # Setup: Cria tabela de controle de migrações
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version VARCHAR(255) PRIMARY KEY,
                    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                )
            """))
    except Exception as e:
        logger.error(f"[MIGRAÇÃO] Erro ao criar schema_migrations: {e}")
        return

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # =========================================================================
    # FASE 1: ADD COLUMN id_sequencial (SEMPRE, idempotente via IF NOT EXISTS)
    # Uma transação por tabela para garantir que cada coluna seja commitada
    # independentemente das demais operações.
    # =========================================================================
    logger.info("[MIGRAÇÃO] FASE 1: Garantindo colunas id_sequencial...")
    for tbl in tenant_tables:
        if tbl not in existing_tables:
            continue
        existing_cols = {c["name"].lower() for c in inspector.get_columns(tbl)}
        if "id_sequencial" not in existing_cols:
            try:
                with engine.begin() as conn:
                    conn.execute(text(
                        f'ALTER TABLE "{tbl}" ADD COLUMN IF NOT EXISTS "id_sequencial" INTEGER'
                    ))
                logger.info(f"[MIGRAÇÃO] FASE 1: Coluna id_sequencial adicionada em '{tbl}'.")
            except Exception as e:
                logger.error(f"[MIGRAÇÃO] FASE 1: Falha em '{tbl}': {e}")

    # =========================================================================
    # FASE 2: Preenche id_sequencial NULL via ROW_NUMBER (SEMPRE, idempotente)
    # Só toca registros com id_sequencial IS NULL, portanto seguro re-executar.
    # Roda em uma única transação para garantir consistência dos números.
    # =========================================================================
    logger.info("[MIGRAÇÃO] FASE 2: Preenchendo id_sequencial (registros com NULL)...")
    try:
        # Re-inspeciona após possíveis ALTERs na fase 1
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        with engine.begin() as conn:
            # Empresas: usa o próprio id como sequencial (único por definição)
            if "empresas" in existing_tables:
                result = conn.execute(text(
                    "UPDATE empresas SET id_sequencial = id WHERE id_sequencial IS NULL"
                ))
                if result.rowcount:
                    logger.info(f"[MIGRAÇÃO] FASE 2: empresas: {result.rowcount} registros preenchidos.")

            for tbl in tenant_tables:
                if tbl == "empresas" or tbl not in existing_tables:
                    continue
                cols = {c["name"].lower() for c in inspector.get_columns(tbl)}
                # Só executa se a coluna id_sequencial realmente existe
                if "id_sequencial" not in cols:
                    continue

                if "id_empresa" in cols:
                    result = conn.execute(text(f"""
                        WITH max_seqs AS (
                            SELECT id_empresa, COALESCE(MAX(id_sequencial), 0) AS max_s
                            FROM "{tbl}"
                            GROUP BY id_empresa
                        ),
                        null_rows AS (
                            SELECT id, id_empresa,
                                   ROW_NUMBER() OVER (PARTITION BY id_empresa ORDER BY id) AS rn
                            FROM "{tbl}"
                            WHERE id_sequencial IS NULL
                        )
                        UPDATE "{tbl}" t
                        SET id_sequencial = COALESCE(m.max_s, 0) + nr.rn
                        FROM null_rows nr
                        LEFT JOIN max_seqs m ON nr.id_empresa = m.id_empresa
                        WHERE t.id = nr.id
                    """))
                else:
                    result = conn.execute(text(f"""
                        WITH max_seqs AS (
                            SELECT COALESCE(MAX(id_sequencial), 0) AS max_s
                            FROM "{tbl}"
                        ),
                        null_rows AS (
                            SELECT id,
                                   ROW_NUMBER() OVER (ORDER BY id) AS rn
                            FROM "{tbl}"
                            WHERE id_sequencial IS NULL
                        )
                        UPDATE "{tbl}" t
                        SET id_sequencial = m.max_s + nr.rn
                        FROM null_rows nr
                        CROSS JOIN max_seqs m
                        WHERE t.id = nr.id
                    """))

                if result.rowcount:
                    logger.info(f"[MIGRAÇÃO] FASE 2: '{tbl}': {result.rowcount} registros preenchidos.")

        logger.info("[MIGRAÇÃO] FASE 2: Preenchimento concluído.")
    except Exception as e:
        logger.error(f"[MIGRAÇÃO] FASE 2 falhou: {e}")
        return

    # =========================================================================
    # FASE 3: Migra FKs de .id -> .id_sequencial (roda UMA VEZ via schema_migrations)
    # =========================================================================
    # Verifica se a migração de FKs já foi aplicada
    fks_already_done = False
    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("SELECT version FROM schema_migrations WHERE version = :ver"),
                {"ver": MIGRATION_VERSION}
            ).fetchone()
            fks_already_done = result is not None
    except Exception as e:
        logger.error(f"[MIGRAÇÃO] Erro ao verificar schema_migrations: {e}")
        return

    if fks_already_done:
        logger.info(f"[MIGRAÇÃO] FASE 3: FKs já migradas ('{MIGRATION_VERSION}' registrada). Pulando.")
        return

    logger.info("[MIGRAÇÃO] FASE 3: Migrando colunas FK para usar id_sequencial...")

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    fk_success = _migrate_fks_with_replication_role(engine, inspector, existing_tables, fk_mappings)

    if not fk_success:
        logger.warning("[MIGRAÇÃO] FASE 3: Tentativa 1 falhou. Tentando via DROP/RECREATE constraints...")
        fk_success = _migrate_fks_with_constraint_drop(engine, inspector, existing_tables, fk_mappings)

    if not fk_success:
        logger.error(
            "[MIGRAÇÃO] FASE 3 falhou completamente. As FKs não foram migradas. "
            "Os dados de id_sequencial estão corretos, mas as referências ainda apontam para o id antigo. "
            "Reinicie o servidor para nova tentativa."
        )
        return

    # =========================================================================
    # FASE 4: Registra migração de FKs como concluída
    # =========================================================================
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO schema_migrations (version) VALUES (:ver) ON CONFLICT DO NOTHING"),
                {"ver": MIGRATION_VERSION}
            )
        logger.info(f"[MIGRAÇÃO] '{MIGRATION_VERSION}' concluída e registrada com sucesso!")
    except Exception as e:
        logger.error(f"[MIGRAÇÃO] FASE 4: Erro ao registrar: {e}")


def _migrate_fks_with_replication_role(engine, inspector, existing_tables, fk_mappings):
    """Tenta migrar FKs via SET session_replication_role = 'replica' (requer superuser ou replication)."""
    try:
        with engine.begin() as conn:
            conn.execute(text("SET session_replication_role = 'replica'"))

            for source_tbl, fk_col, target_tbl in fk_mappings:
                if source_tbl not in existing_tables or target_tbl not in existing_tables:
                    continue
                source_col_info = {c["name"].lower(): c for c in inspector.get_columns(source_tbl)}
                if fk_col.lower() not in source_col_info:
                    continue

                source_cols = {c["name"].lower() for c in inspector.get_columns(source_tbl)}
                target_cols = {c["name"].lower() for c in inspector.get_columns(target_tbl)}
                emp_clause = 'AND s."id_empresa" = target.id_empresa' if ("id_empresa" in source_cols and "id_empresa" in target_cols) else ''

                logger.info(f"[MIGRAÇÃO] FK: '{source_tbl}.{fk_col}' -> '{target_tbl}.id_sequencial'")
                col_type = str(source_col_info[fk_col.lower()]["type"]).upper()
                is_varchar = any(t in col_type for t in ["VARCHAR", "CHARACTER", "TEXT", "CHAR"])

                if is_varchar:
                    conn.execute(text(f"""
                        UPDATE "{source_tbl}" s
                        SET "{fk_col}" = target.id_sequencial::VARCHAR
                        FROM "{target_tbl}" target
                        WHERE s."{fk_col}" ~ '^[0-9]+$'
                          AND s."{fk_col}"::INTEGER = target.id
                          AND s."{fk_col}" IS NOT NULL
                          {emp_clause}
                    """))
                else:
                    conn.execute(text(f"""
                        UPDATE "{source_tbl}" s
                        SET "{fk_col}" = target.id_sequencial
                        FROM "{target_tbl}" target
                        WHERE s."{fk_col}" = target.id
                          AND s."{fk_col}" IS NOT NULL
                          {emp_clause}
                    """))

            conn.execute(text("SET session_replication_role = 'origin'"))

        logger.info("[MIGRAÇÃO] FASE 3 (replication_role): FKs migradas com sucesso.")
        return True
    except Exception as e:
        logger.warning(f"[MIGRAÇÃO] session_replication_role falhou: {e}")
        return False


def _migrate_fks_with_constraint_drop(engine, inspector, existing_tables, fk_mappings):
    """
    Fallback: Dropa FK constraints, executa UPDATEs e recria as constraints
    apontando para id_sequencial. Funciona sem privilégios de superuser.
    """
    try:
        dropped_constraints = []

        with engine.begin() as conn:
            source_tables = {m[0] for m in fk_mappings if m[0] in existing_tables}

            for tbl in source_tables:
                fk_constraints = conn.execute(text("""
                    SELECT tc.constraint_name, kcu.column_name,
                           ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_name = :tbl
                      AND tc.table_schema = 'public'
                """), {"tbl": tbl}).fetchall()

                for row in fk_constraints:
                    constraint_name, col_name, foreign_table, foreign_col = row
                    conn.execute(text(
                        f'ALTER TABLE "{tbl}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'
                    ))
                    dropped_constraints.append({
                        "table": tbl, "constraint": constraint_name,
                        "column": col_name, "foreign_table": foreign_table,
                        "foreign_column": foreign_col,
                    })
                    logger.info(f"[MIGRAÇÃO] Constraint {constraint_name} removida temporariamente.")

            # Executa UPDATEs de FK sem constraints
            for source_tbl, fk_col, target_tbl in fk_mappings:
                if source_tbl not in existing_tables or target_tbl not in existing_tables:
                    continue
                source_col_info = {c["name"].lower(): c for c in inspector.get_columns(source_tbl)}
                if fk_col.lower() not in source_col_info:
                    continue

                source_cols = {c["name"].lower() for c in inspector.get_columns(source_tbl)}
                target_cols = {c["name"].lower() for c in inspector.get_columns(target_tbl)}
                emp_clause = 'AND s."id_empresa" = target.id_empresa' if ("id_empresa" in source_cols and "id_empresa" in target_cols) else ''

                logger.info(f"[MIGRAÇÃO] FK (DROP): '{source_tbl}.{fk_col}' -> '{target_tbl}.id_sequencial'")
                col_type = str(source_col_info[fk_col.lower()]["type"]).upper()
                is_varchar = any(t in col_type for t in ["VARCHAR", "CHARACTER", "TEXT", "CHAR"])

                if is_varchar:
                    conn.execute(text(f"""
                        UPDATE "{source_tbl}" s
                        SET "{fk_col}" = target.id_sequencial::VARCHAR
                        FROM "{target_tbl}" target
                        WHERE s."{fk_col}" ~ '^[0-9]+$'
                          AND s."{fk_col}"::INTEGER = target.id
                          AND s."{fk_col}" IS NOT NULL
                          {emp_clause}
                    """))
                else:
                    conn.execute(text(f"""
                        UPDATE "{source_tbl}" s
                        SET "{fk_col}" = target.id_sequencial
                        FROM "{target_tbl}" target
                        WHERE s."{fk_col}" = target.id
                          AND s."{fk_col}" IS NOT NULL
                          {emp_clause}
                    """))

            # Recria constraints apontando para id_sequencial ou id_empresa, id_sequencial se for id_sequencial
            for c in dropped_constraints:
                target_col = "id_sequencial" if c["foreign_column"] == "id" else c["foreign_column"]
                try:
                    source_cols = {col["name"].lower() for col in inspector.get_columns(c['table'])}
                    target_cols = {col["name"].lower() for col in inspector.get_columns(c['foreign_table'])}
                    if target_col == "id_sequencial" and "id_empresa" in source_cols and "id_empresa" in target_cols:
                        conn.execute(text(f"""
                            ALTER TABLE "{c['table']}"
                            ADD CONSTRAINT "{c['constraint']}"
                            FOREIGN KEY ("id_empresa", "{c['column']}")
                            REFERENCES "{c['foreign_table']}" ("id_empresa", "id_sequencial")
                            ON DELETE SET NULL ON UPDATE CASCADE
                        """))
                    else:
                        conn.execute(text(f"""
                            ALTER TABLE "{c['table']}"
                            ADD CONSTRAINT "{c['constraint']}"
                            FOREIGN KEY ("{c['column']}")
                            REFERENCES "{c['foreign_table']}" ("{target_col}")
                        """))
                    logger.info(f"[MIGRAÇÃO] Constraint {c['constraint']} recriada -> {c['foreign_table']}.{target_col}")
                except Exception as recreate_err:
                    logger.warning(f"[MIGRAÇÃO] Não foi possível recriar {c['constraint']}: {recreate_err}")

        logger.info("[MIGRAÇÃO] FASE 3 (drop/recreate): FKs migradas com sucesso.")
        return True
    except Exception as e:
        logger.error(f"[MIGRAÇÃO] FASE 3 (drop/recreate) falhou: {e}")
        return False


def fix_legacy_foreign_keys(engine: Engine):
    """
    Inspeciona e remove constraints monocoluna legadas (apontando para cadastros.id, etc.)
    e garante as novas FKs compostas por (id_empresa, col_name) -> target_table(id_empresa, id_sequencial).
    """
    logger.info("[MIGRAÇÃO] Verificando e corrigindo FKs monocoluna legadas...")
    
    fk_configs = [
        ("pedidos", "id_transportadora", "cadastros", "fk_pedidos_transportadora_empresa_seq"),
        ("pedidos", "id_cliente", "cadastros", "fk_pedidos_cliente_empresa_seq"),
        ("pedidos", "id_vendedor", "cadastros", "fk_pedidos_vendedor_empresa_seq"),
        ("produtos", "id_fornecedor", "cadastros", "fk_produtos_fornecedor_empresa_seq"),
        ("produtos", "id_embalagem", "embalagens", "fk_produtos_embalagem_empresa_seq"),
        ("contas", "id_fornecedor", "cadastros", "fk_contas_fornecedor_empresa_seq"),
        ("estoque", "id_produto", "produtos", "fk_estoque_produto_empresa_seq"),
    ]

    try:
        with engine.begin() as conn:
            for tbl, col_name, target_tbl, new_constraint_name in fk_configs:
                # Busca constraints existentes na tabela que utilizam a coluna col_name
                fk_constraints = conn.execute(text("""
                    SELECT tc.constraint_name, ccu.column_name AS foreign_column
                    FROM information_schema.table_constraints AS tc
                    JOIN information_schema.key_column_usage AS kcu
                        ON tc.constraint_name = kcu.constraint_name
                        AND tc.table_schema = kcu.table_schema
                    JOIN information_schema.constraint_column_usage AS ccu
                        ON ccu.constraint_name = tc.constraint_name
                    WHERE tc.constraint_type = 'FOREIGN KEY'
                      AND tc.table_name = :tbl
                      AND kcu.column_name = :col
                      AND tc.table_schema = 'public'
                """), {"tbl": tbl, "col": col_name}).fetchall()

                for constraint_name, foreign_column in fk_constraints:
                    # Se a constraint aponta para 'id' (monocoluna antiga) ou tem nome antigo, dropa
                    if foreign_column == "id" or constraint_name != new_constraint_name:
                        logger.info(f"[MIGRAÇÃO] Removendo FK legada '{constraint_name}' de '{tbl}.{col_name}'...")
                        conn.execute(text(f'ALTER TABLE "{tbl}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'))

                # Verifica se a nova FK composta já existe
                check_new = conn.execute(text("""
                    SELECT constraint_name 
                    FROM information_schema.table_constraints 
                    WHERE table_name = :tbl 
                      AND constraint_name = :cname
                      AND table_schema = 'public'
                """), {"tbl": tbl, "cname": new_constraint_name}).fetchone()

                if not check_new:
                    logger.info(f"[MIGRAÇÃO] Criando FK composta '{new_constraint_name}' em '{tbl}' ({col_name} -> {target_tbl}.id_sequencial)...")
                    conn.execute(text(f"""
                        ALTER TABLE "{tbl}"
                        ADD CONSTRAINT "{new_constraint_name}"
                        FOREIGN KEY ("id_empresa", "{col_name}")
                        REFERENCES "{target_tbl}" ("id_empresa", "id_sequencial")
                        ON DELETE SET NULL ON UPDATE CASCADE
                    """))
                    logger.info(f"[MIGRAÇÃO] FK composta '{new_constraint_name}' criada com sucesso!")
    except Exception as e:
        logger.error(f"[MIGRAÇÃO] Falha ao corrigir FKs legadas: {e}")


def backfill_meli_fields_from_observacao(engine: Engine):
    """
    Extrai e preenche meli_order_id, meli_pack_id, meli_buyer_nickname, 
    meli_logistic_type e meli_shipping_service a partir do campo observacao
    para pedidos onde meli_order_id ainda é NULL.
    """
    import re
    try:
        with engine.begin() as conn:
            query = text("""
                SELECT id, observacao 
                FROM pedidos 
                WHERE meli_order_id IS NULL 
                  AND observacao IS NOT NULL
                  AND (origem_venda ILIKE '%mercado%' OR observacao ILIKE '%pedido ml%' OR observacao ILIKE '%id ml%')
            """)
            rows = conn.execute(query).fetchall()
            if not rows:
                return

            logger.info(f"[BACKFILL MELI] Encontrados {len(rows)} pedidos para extração de dados do Mercado Livre...")
            updated_count = 0

            for r in rows:
                ped_id, obs = r[0], r[1] or ""
                pack_id = None
                order_id = None
                buyer = None
                service = None
                log_type = None

                # Padrão 1: "Pedido ML: 2000014461847753 | ID: 2000017861967786"
                m_pack_and_id = re.search(r"Pedido ML:\s*(\d+)\s*\|\s*ID:\s*([\d,\s]+)", obs)
                if m_pack_and_id:
                    pack_id = m_pack_and_id.group(1).strip()
                    order_id = m_pack_and_id.group(2).strip()
                else:
                    # Padrão 2: "Pedido ML: 2000018090551354"
                    m_single_id = re.search(r"Pedido ML:\s*([\d,\s]+)", obs)
                    if m_single_id:
                        order_id = m_single_id.group(1).strip()
                    else:
                        # Padrão 3: "Pedido 2000014548984385" ou "ID ML: 2000015002796874"
                        m_generic_id = re.search(r"(?:Pedido|ID ML:?)\s*(\d{15,})", obs)
                        if m_generic_id:
                            order_id = m_generic_id.group(1).strip()

                m_buyer = re.search(r"Comprador:\s*([^|]+)", obs)
                if m_buyer:
                    buyer = m_buyer.group(1).strip()

                m_service = re.search(r"Servi[çc]o:\s*([^|]+)", obs)
                if m_service:
                    service = m_service.group(1).strip()

                m_log = re.search(r"Log[íi]stica:\s*([^|]+)", obs)
                if m_log:
                    log_type = m_log.group(1).strip()

                if order_id or pack_id:
                    conn.execute(text("""
                        UPDATE pedidos
                        SET meli_order_id = COALESCE(meli_order_id, :order_id),
                            meli_pack_id = COALESCE(meli_pack_id, :pack_id),
                            meli_buyer_nickname = COALESCE(meli_buyer_nickname, :buyer),
                            meli_shipping_service = COALESCE(meli_shipping_service, :service),
                            meli_logistic_type = COALESCE(meli_logistic_type, :log_type)
                        WHERE id = :ped_id
                    """), {
                        "order_id": str(order_id) if order_id else None,
                        "pack_id": str(pack_id) if pack_id else None,
                        "buyer": str(buyer) if buyer else None,
                        "service": str(service) if service else None,
                        "log_type": str(log_type) if log_type else None,
                        "ped_id": ped_id
                    })
                    updated_count += 1

            logger.info(f"[BACKFILL MELI] {updated_count} pedidos atualizados com dados estruturados do Mercado Livre!")
    except Exception as e:
        logger.error(f"[BACKFILL MELI] Erro durante backfill de campos do ML: {e}")


def sync_database_schema(engine: Engine, base):
    """
    Inspeciona todas as tabelas registradas no SQLAlchemy Base.metadata.
    Adiciona colunas faltantes automaticamente e executa backfills necessários.
    """
    logger.info("[SYNC] Iniciando sincronização do banco de dados...")

    try:
        # 1. Cria tabelas novas
        base.metadata.create_all(bind=engine)

        # 2. Migração id_sequencial (fases 1 e 2 sempre rodam; fase 3 só uma vez)
        try:
            run_one_time_id_sequencial_migration(engine, base)
        except Exception as mig_err:
            logger.error(f"[SYNC] Migração id_sequencial falhou: {mig_err}. Continuando sync...")

        # 2b. Corrige FKs legadas para garantir FKs compostas (id_empresa, id_sequencial)
        try:
            fix_legacy_foreign_keys(engine)
        except Exception as fk_err:
            logger.error(f"[SYNC] Correção de FKs legadas falhou: {fk_err}")

        # 3. Sync de colunas faltantes (safety net)
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())

        for table_name, table in base.metadata.tables.items():
            if table_name not in existing_tables:
                continue
            existing_columns = {col["name"].lower() for col in inspector.get_columns(table_name)}
            for column in table.columns:
                col_name = column.name
                if col_name.lower() not in existing_columns:
                    logger.info(f"[SYNC] Coluna faltante: '{table_name}.{col_name}'. Adicionando...")
                    try:
                        compiled_type = column.type.compile(engine.dialect)
                        with engine.begin() as conn:
                            conn.execute(text(
                                f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col_name}" {compiled_type}'
                            ))
                        logger.info(f"[SYNC] '{table_name}.{col_name}' ({compiled_type}) adicionada.")
                    except Exception as col_err:
                        logger.error(f"[SYNC] Erro em '{table_name}.{col_name}': {col_err}")

        # 4. Backfill de campos Mercado Livre estruturados
        try:
            backfill_meli_fields_from_observacao(engine)
        except Exception as bf_err:
            logger.error(f"[SYNC] Backfill Mercado Livre falhou: {bf_err}")

        logger.info("[SYNC] Sincronização concluída com sucesso.")
    except Exception as e:
        logger.error(f"[SYNC] Erro crítico: {e}")
