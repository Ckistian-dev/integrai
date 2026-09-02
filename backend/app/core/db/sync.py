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

    # Inclui dinamicamente qualquer tabela dos modelos que possua id_empresa ou id_sequencial
    if base and hasattr(base, 'metadata') and hasattr(base.metadata, 'tables'):
        for tbl_name, tbl_obj in base.metadata.tables.items():
            if "id_empresa" in tbl_obj.columns or "id_sequencial" in tbl_obj.columns:
                if tbl_name not in tenant_tables:
                    tenant_tables.append(tbl_name)

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

    # Garante que as Unique Constraints estejam criadas antes de qualquer operação de FK
    ensure_unique_constraints(engine)

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
                try:
                    fk_constraints = conn.execute(text("""
                        SELECT c.conname AS constraint_name,
                               att.attname AS column_name,
                               confrel.relname AS foreign_table,
                               fatt.attname AS foreign_column
                        FROM pg_constraint c
                        JOIN pg_class conrel ON conrel.oid = c.conrelid
                        JOIN pg_namespace ns ON ns.oid = conrel.relnamespace
                        JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
                        LEFT JOIN pg_class confrel ON confrel.oid = c.confrelid
                        LEFT JOIN pg_attribute fatt ON fatt.attrelid = c.confrelid AND fatt.attnum = c.confkey[1]
                        WHERE c.contype = 'f'
                          AND ns.nspname = 'public'
                          AND conrel.relname = :tbl
                    """), {"tbl": tbl}).fetchall()

                    for row in fk_constraints:
                        constraint_name, col_name, foreign_table, foreign_col = row
                        conn.execute(text(
                            f'ALTER TABLE "{tbl}" DROP CONSTRAINT IF EXISTS "{constraint_name}" CASCADE'
                        ))
                        dropped_constraints.append({
                            "table": tbl, "constraint": constraint_name,
                            "column": col_name, "foreign_table": foreign_table,
                            "foreign_column": foreign_col,
                        })
                        logger.info(f"[MIGRAÇÃO] Constraint {constraint_name} removida temporariamente.")
                except Exception as query_err:
                    logger.debug(f"[MIGRAÇÃO] Consulta de constraints para {tbl}: {query_err}")

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


def ensure_unique_constraints(engine: Engine, base=None):
    """
    Garante que todas as tabelas tenant com id_empresa e id_sequencial
    possuam uma constraint UNIQUE (id_empresa, id_sequencial).
    Isso é PRÉ-REQUISITO OBRIGATÓRIO no PostgreSQL para a criação de Foreign Keys compostas.
    """
    logger.info("[MIGRAÇÃO] Garantindo constraints UNIQUE (id_empresa, id_sequencial)...")

    unique_tables = [
        ("perfil", "uq_perfil_empresa_sequencial"),
        ("usuarios", "uq_usuarios_empresa_sequencial"),
        ("cadastros", "uq_cadastros_empresa_sequencial"),
        ("embalagens", "uq_embalagens_empresa_sequencial"),
        ("produtos", "uq_produtos_empresa_sequencial"),
        ("contas", "uq_contas_empresa_sequencial"),
        ("estoque", "uq_estoque_empresa_sequencial"),
        ("pedidos", "uq_pedidos_empresa_sequencial"),
        ("regras_tributarias", "uq_regras_tributarias_empresa_sequencial"),
        ("classificacao_contabil", "uq_classificacao_contabil_empresa_sequencial"),
        ("intelipost_configuracoes", "uq_intelipost_configuracoes_empresa_sequencial"),
        ("meli_configuracoes", "uq_meli_configuracoes_empresa_sequencial"),
        ("magento_configuracoes", "uq_magento_configuracoes_empresa_sequencial"),
        ("tiktok_configuracoes", "uq_tiktok_configuracoes_empresa_sequencial"),
        ("shopee_configuracoes", "uq_shopee_configuracoes_empresa_sequencial"),
        ("elastic_email_configuracoes", "uq_elastic_email_configuracoes_empresa_sequencial"),
        ("atendai_configuracoes", "uq_atendai_configuracoes_empresa_sequencial"),
        ("outras_empresas_configuracoes", "uq_outras_empresas_configuracoes_empresa_sequencial"),
        ("email_regras", "uq_email_regras_empresa_sequencial"),
        ("opcoes_campos", "uq_opcoes_campos_empresa_sequencial"),
        ("relatorios", "uq_relatorios_empresa_sequencial"),
        ("nfe_recebidas", "uq_nfe_recebidas_empresa_sequencial"),
    ]

    if base and hasattr(base, 'metadata') and hasattr(base.metadata, 'tables'):
        existing_names = {t[0] for t in unique_tables}
        for tbl_name, tbl_obj in base.metadata.tables.items():
            if "id_empresa" in tbl_obj.columns and "id_sequencial" in tbl_obj.columns and tbl_name not in existing_names:
                unique_tables.append((tbl_name, f"uq_{tbl_name}_empresa_sequencial"))

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for tbl, cname in unique_tables:
        if tbl not in existing_tables:
            continue

        try:
            cols = {c["name"].lower() for c in inspector.get_columns(tbl)}
            if "id_empresa" not in cols or "id_sequencial" not in cols:
                continue

            with engine.begin() as conn:
                # 1. Verifica se já existe constraint UNIQUE ou PRIMARY KEY em (id_empresa, id_sequencial)
                has_uq = conn.execute(text("""
                    SELECT c.conname
                    FROM pg_constraint c
                    JOIN pg_class conrel ON conrel.oid = c.conrelid
                    JOIN pg_namespace ns ON ns.oid = conrel.relnamespace
                    WHERE c.contype IN ('u', 'p')
                      AND ns.nspname = 'public'
                      AND conrel.relname = :tbl
                      AND (
                          SELECT array_agg(att.attname::text ORDER BY u.attpos)
                          FROM unnest(c.conkey) WITH ORDINALITY AS u(attnum, attpos)
                          JOIN pg_attribute att ON att.attrelid = conrel.oid AND att.attnum = u.attnum
                      ) = ARRAY['id_empresa', 'id_sequencial']::text[]
                """), {"tbl": tbl}).fetchone()

                if has_uq:
                    continue

                # 2. Preenche eventuais id_sequencial NULL
                conn.execute(text(f"""
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

                # 3. Verifica e resolve duplicatas se houver
                dup_check = conn.execute(text(f"""
                    SELECT id_empresa, id_sequencial
                    FROM "{tbl}"
                    WHERE id_sequencial IS NOT NULL
                    GROUP BY id_empresa, id_sequencial
                    HAVING COUNT(*) > 1
                    LIMIT 1
                """)).fetchone()

                if dup_check:
                    logger.warning(f"[MIGRAÇÃO] Duplicatas de id_sequencial detectadas em '{tbl}'. Corrigindo sequencial...")
                    conn.execute(text(f"""
                        WITH renumbered AS (
                            SELECT id, ROW_NUMBER() OVER (PARTITION BY id_empresa ORDER BY id) AS rn
                            FROM "{tbl}"
                        )
                        UPDATE "{tbl}" t
                        SET id_sequencial = r.rn
                        FROM renumbered r
                        WHERE t.id = r.id
                    """))

                # 4. Adiciona a constraint UNIQUE
                logger.info(f"[MIGRAÇÃO] Criando constraint UNIQUE '{cname}' em '{tbl}' (id_empresa, id_sequencial)...")
                conn.execute(text(f"""
                    ALTER TABLE "{tbl}"
                    ADD CONSTRAINT "{cname}" UNIQUE ("id_empresa", "id_sequencial")
                """))
                logger.info(f"[MIGRAÇÃO] Constraint UNIQUE '{cname}' criada com sucesso em '{tbl}'.")
        except Exception as e:
            logger.warning(f"[MIGRAÇÃO] Não foi possível criar UNIQUE constraint '{cname}' em '{tbl}': {e}")


def fix_legacy_foreign_keys(engine: Engine):
    """
    Inspeciona e remove constraints monocoluna legadas (apontando para cadastros.id, etc.)
    e garante as novas FKs compostas por (id_empresa, col_name) -> target_table(id_empresa, id_sequencial).
    """
    logger.info("[MIGRAÇÃO] Verificando e corrigindo FKs monocoluna legadas...")
    
    # Garante que as Unique Constraints estejam criadas antes de aplicar as FKs
    ensure_unique_constraints(engine)

    legacy_constraint_names = [
        ("contas", "contas_id_fornecedor_fkey"),
        ("contas", "contas_id_classificacao_contabil_fkey"),
        ("produtos", "produtos_id_fornecedor_fkey"),
        ("produtos", "produtos_id_embalagem_fkey"),
        ("estoque", "estoque_id_produto_fkey"),
        ("pedidos", "pedidos_id_cliente_fkey"),
        ("pedidos", "pedidos_id_vendedor_fkey"),
        ("pedidos", "pedidos_id_transportadora_fkey"),
        ("usuarios", "usuarios_id_perfil_fkey"),
        ("empresas", "empresas_id_classificacao_contabil_padrao_fkey"),
        ("empresas", "empresas_id_classificacao_contabil_cancelamento_fkey"),
        ("usuario_preferencias", "usuario_preferencias_id_usuario_fkey"),
        ("dashboard_preferencias", "dashboard_preferencias_id_usuario_fkey"),
    ]

    # 1. Drop explícito de nomes conhecidos de constraints legadas
    for tbl, cname in legacy_constraint_names:
        try:
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{tbl}" DROP CONSTRAINT IF EXISTS "{cname}" CASCADE'))
        except Exception as e:
            logger.debug(f"[MIGRAÇÃO] Drop de constraint legada '{cname}' em '{tbl}': {e}")

    # 2. Drop dinâmico de qualquer outra FK monocoluna em tabelas multi-tenant no PostgreSQL
    try:
        with engine.begin() as conn:
            monocol_fks = conn.execute(text("""
                SELECT c.conname AS constraint_name,
                       conrel.relname AS table_name,
                       att.attname AS column_name
                FROM pg_constraint c
                JOIN pg_class conrel ON conrel.oid = c.conrelid
                JOIN pg_namespace ns ON ns.oid = conrel.relnamespace
                JOIN pg_attribute att ON att.attrelid = c.conrelid AND att.attnum = c.conkey[1]
                WHERE c.contype = 'f'
                  AND ns.nspname = 'public'
                  AND ARRAY_LENGTH(c.conkey, 1) = 1
                  AND conrel.relname IN ('contas', 'produtos', 'estoque', 'pedidos', 'usuarios', 'empresas', 'usuario_preferencias', 'dashboard_preferencias')
            """)).fetchall()

            for r_cname, r_tbl, r_col in monocol_fks:
                if r_col not in ["id_empresa"]:
                    logger.info(f"[MIGRAÇÃO] Removendo FK monocoluna legada '{r_cname}' de '{r_tbl}.{r_col}'...")
                    conn.execute(text(f'ALTER TABLE "{r_tbl}" DROP CONSTRAINT IF EXISTS "{r_cname}" CASCADE'))
    except Exception as e:
        logger.debug(f"[MIGRAÇÃO] Varredura dinâmica de FKs monocoluna: {e}")

    # 2b. Converte a coluna usuarios.id_perfil de VARCHAR para INTEGER se necessário
    try:
        with engine.begin() as conn:
            col_type_res = conn.execute(text("""
                SELECT data_type 
                FROM information_schema.columns 
                WHERE table_name = 'usuarios' AND column_name = 'id_perfil' AND table_schema = 'public'
            """)).scalar()

            if col_type_res and ('character' in col_type_res.lower() or col_type_res in ['text', 'varchar']):
                logger.info("[MIGRAÇÃO] Convertendo coluna 'usuarios.id_perfil' de VARCHAR para INTEGER...")
                
                # Se houver nomes de perfis (ex: 'admin', 'vendedor'), tenta mapear para o id_sequencial do perfil correspondente
                conn.execute(text("""
                    UPDATE "usuarios" u
                    SET "id_perfil" = p.id_sequencial::VARCHAR
                    FROM "perfil" p
                    WHERE u.id_empresa = p.id_empresa
                      AND LOWER(TRIM(u."id_perfil")) = LOWER(TRIM(p.nome))
                      AND u."id_perfil" !~ '^[0-9]+$'
                """))

                # Converte a coluna para INTEGER
                conn.execute(text("""
                    ALTER TABLE "usuarios" 
                    ALTER COLUMN "id_perfil" TYPE INTEGER 
                    USING (CASE WHEN "id_perfil" ~ '^[0-9]+$' THEN "id_perfil"::INTEGER ELSE NULL END)
                """))
                logger.info("[MIGRAÇÃO] Coluna 'usuarios.id_perfil' convertida para INTEGER com sucesso!")
    except Exception as conv_err:
        logger.warning(f"[MIGRAÇÃO] Aviso ao converter usuarios.id_perfil para INTEGER: {conv_err}")

    # 3. Garante as novas FKs compostas (uma transação isolada por tabela/coluna)
    fk_configs = [
        ("pedidos", "id_transportadora", "cadastros", "fk_pedidos_transportadora_empresa_seq", "SET NULL"),
        ("pedidos", "id_cliente", "cadastros", "fk_pedidos_cliente_empresa_seq", "SET NULL"),
        ("pedidos", "id_vendedor", "cadastros", "fk_pedidos_vendedor_empresa_seq", "SET NULL"),
        ("produtos", "id_fornecedor", "cadastros", "fk_produtos_fornecedor_empresa_seq", "SET NULL"),
        ("produtos", "id_embalagem", "embalagens", "fk_produtos_embalagem_empresa_seq", "SET NULL"),
        ("contas", "id_fornecedor", "cadastros", "fk_contas_fornecedor_empresa_seq", "RESTRICT"),
        ("contas", "id_classificacao_contabil", "classificacao_contabil", "fk_contas_classificacao_empresa_seq", "RESTRICT"),
        ("estoque", "id_produto", "produtos", "fk_estoque_produto_empresa_seq", "RESTRICT"),
        ("usuarios", "id_perfil", "perfil", "fk_usuarios_perfil_empresa_seq", "SET NULL"),
    ]

    for tbl, col_name, target_tbl, new_constraint_name, on_delete in fk_configs:
        try:
            with engine.begin() as conn:
                check_new = conn.execute(text("""
                    SELECT constraint_name 
                    FROM information_schema.table_constraints 
                    WHERE table_name = :tbl 
                      AND constraint_name = :cname
                      AND table_schema = 'public'
                """), {"tbl": tbl, "cname": new_constraint_name}).fetchone()

                if not check_new:
                    # Limpa referências órfãs se on_delete for SET NULL
                    if on_delete == "SET NULL":
                        conn.execute(text(f"""
                            UPDATE "{tbl}" s
                            SET "{col_name}" = NULL
                            WHERE s."{col_name}" IS NOT NULL
                              AND NOT EXISTS (
                                  SELECT 1 FROM "{target_tbl}" t
                                  WHERE t.id_empresa = s.id_empresa AND t.id_sequencial = s."{col_name}"
                              )
                        """))

                    logger.info(f"[MIGRAÇÃO] Criando FK composta '{new_constraint_name}' em '{tbl}' ({col_name} -> {target_tbl}.id_sequencial)...")
                    conn.execute(text(f"""
                        ALTER TABLE "{tbl}"
                        ADD CONSTRAINT "{new_constraint_name}"
                        FOREIGN KEY ("id_empresa", "{col_name}")
                        REFERENCES "{target_tbl}" ("id_empresa", "id_sequencial")
                        ON DELETE {on_delete} ON UPDATE CASCADE
                    """))
                    logger.info(f"[MIGRAÇÃO] FK composta '{new_constraint_name}' criada com sucesso!")
        except Exception as e:
            logger.warning(f"[MIGRAÇÃO] Não foi possível criar FK composta '{new_constraint_name}' em '{tbl}': {e}")


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


def sync_missing_columns_and_enums(engine: Engine, base):
    """
    Sincroniza automaticamente todos os tipos ENUM e todas as novas colunas
    definidas nos modelos SQLAlchemy (base.metadata) com o PostgreSQL.
    Executa cada adição de coluna em transação isolada para máxima resiliência.
    """
    logger.info("[SYNC] Verificando e sincronizando novas colunas e enums no banco de dados...")
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    # 1. Sincronização de tipos ENUM no PostgreSQL
    for table_name, table in base.metadata.tables.items():
        if table_name not in existing_tables:
            continue

        for column in table.columns:
            col_type = column.type
            enum_class = getattr(col_type, 'enum_class', None)
            enum_name = getattr(col_type, 'name', None)
            enums_values = getattr(col_type, 'enums', None)

            if enum_class or enums_values:
                vals = [e.value if hasattr(e, 'value') else str(e) for e in (enum_class or enums_values)]
                e_name = enum_name or (enum_class.__name__.lower() if enum_class else f"{table_name}_{column.name}_enum")
                
                try:
                    with engine.begin() as conn:
                        type_exists = conn.execute(
                            text("SELECT 1 FROM pg_type WHERE typname = :tname"),
                            {"tname": e_name}
                        ).scalar()
                        
                        if not type_exists:
                            vals_escaped = ", ".join(f"'{v}'" for v in vals)
                            conn.execute(text(f'CREATE TYPE "{e_name}" AS ENUM ({vals_escaped})'))
                            logger.info(f"[SYNC] Novo tipo ENUM '{e_name}' criado no PostgreSQL.")
                        else:
                            for v in vals:
                                try:
                                    conn.execute(text(f'ALTER TYPE "{e_name}" ADD VALUE IF NOT EXISTS \'{v}\''))
                                except Exception:
                                    pass
                except Exception as enum_err:
                    logger.debug(f"[SYNC] Aviso na sincronização do enum '{e_name}': {enum_err}")

    # 2. Sincronização de Novas Colunas em todas as tabelas
    added_count = 0
    inspector = inspect(engine)
    for table_name, table in base.metadata.tables.items():
        if table_name not in existing_tables:
            continue

        try:
            existing_columns = {col["name"].lower() for col in inspector.get_columns(table_name)}
        except Exception as insp_err:
            logger.warning(f"[SYNC] Falha ao inspecionar colunas de '{table_name}': {insp_err}")
            continue

        for column in table.columns:
            col_name = column.name
            if col_name.lower() not in existing_columns:
                logger.info(f"[SYNC] Nova coluna detectada: '{table_name}.{col_name}'. Adicionando ao banco...")
                try:
                    # Compila o tipo PostgreSQL
                    try:
                        compiled_type = column.type.compile(engine.dialect)
                    except Exception:
                        compiled_type = "TEXT"

                    # Monta cláusula DEFAULT se houver
                    default_clause = ""
                    if column.server_default is not None:
                        default_clause = f" DEFAULT {column.server_default.arg}"
                    elif column.default is not None and getattr(column.default, 'is_scalar', False):
                        val = column.default.arg
                        if isinstance(val, bool):
                            default_clause = f" DEFAULT {'true' if val else 'false'}"
                        elif isinstance(val, (int, float)):
                            default_clause = f" DEFAULT {val}"
                        elif isinstance(val, str):
                            default_clause = f" DEFAULT '{val}'"

                    alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col_name}" {compiled_type}{default_clause}'
                    
                    with engine.begin() as conn:
                        conn.execute(text(alter_sql))
                    
                    logger.info(f"[SYNC] ✔ Coluna '{table_name}.{col_name}' ({compiled_type}) adicionada com sucesso!")
                    added_count += 1
                except Exception as col_err:
                    logger.error(f"[SYNC] ✖ Erro ao adicionar '{table_name}.{col_name}': {col_err}. Tentando fallback...")
                    try:
                        # Fallback seguro para JSONB ou TEXT
                        fallback_type = "JSONB" if "json" in str(column.type).lower() else "TEXT"
                        with engine.begin() as conn:
                            conn.execute(text(f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col_name}" {fallback_type}'))
                        logger.info(f"[SYNC] ✔ Coluna '{table_name}.{col_name}' adicionada via fallback ({fallback_type}).")
                        added_count += 1
                    except Exception as fb_err:
                        logger.error(f"[SYNC] Falha no fallback para '{table_name}.{col_name}': {fb_err}")

    if added_count > 0:
        logger.info(f"[SYNC] Sincronização de colunas concluída: {added_count} nova(s) coluna(s) adicionada(s) ao banco!")
    else:
        logger.info("[SYNC] Todas as colunas dos modelos estão sincronizadas no banco de dados.")


def sync_database_schema(engine: Engine, base):
    """
    Inspeciona todas as tabelas registradas no SQLAlchemy Base.metadata.
    Adiciona colunas faltantes e ENUMs automaticamente, garante constraints e executa backfills necessários.
    """
    logger.info("[SYNC] Iniciando sincronização do banco de dados no startup...")

    try:
        # 1. Cria tabelas novas declaradas nos modelos
        base.metadata.create_all(bind=engine)

        # 2. Sincroniza todas as novas colunas e ENUMs imediatamente (prioridade máxima)
        try:
            sync_missing_columns_and_enums(engine, base)
        except Exception as col_sync_err:
            logger.error(f"[SYNC] Erro na sincronização de colunas/enums: {col_sync_err}")

        # 3. Migração id_sequencial (fases 1 e 2 sempre rodam; fase 3 só uma vez)
        try:
            run_one_time_id_sequencial_migration(engine, base)
        except Exception as mig_err:
            logger.error(f"[SYNC] Migração id_sequencial falhou: {mig_err}. Continuando sync...")

        # 4. Corrige FKs legadas para garantir FKs compostas (id_empresa, id_sequencial)
        try:
            fix_legacy_foreign_keys(engine)
        except Exception as fk_err:
            logger.error(f"[SYNC] Correção de FKs legadas falhou: {fk_err}")

        # 5. Backfill de campos Mercado Livre estruturados
        try:
            backfill_meli_fields_from_observacao(engine)
        except Exception as bf_err:
            logger.error(f"[SYNC] Backfill Mercado Livre falhou: {bf_err}")

        # 6. Criação automática de índices declarados nos modelos
        try:
            inspector_indexes = inspect(engine)
            existing_tables = set(inspector_indexes.get_table_names())
            for table_name, table in base.metadata.tables.items():
                if table_name not in existing_tables:
                    continue
                try:
                    existing_indexes = {idx["name"].lower() for idx in inspector_indexes.get_indexes(table_name) if idx.get("name")}
                except Exception:
                    existing_indexes = set()

                for index in table.indexes:
                    if index.name and index.name.lower() not in existing_indexes:
                        try:
                            index.create(bind=engine)
                            logger.info(f"[SYNC] Índice '{index.name}' criado com sucesso na tabela '{table_name}'.")
                        except Exception as idx_err:
                            logger.warning(f"[SYNC] Aviso ao criar índice '{index.name}': {idx_err}")
        except Exception as idx_sync_err:
            logger.error(f"[SYNC] Erro na sincronização de índices: {idx_sync_err}")

        logger.info("[SYNC] Sincronização do banco de dados concluída com sucesso.")
    except Exception as e:
        logger.error(f"[SYNC] Erro crítico na inicialização do banco: {e}")
