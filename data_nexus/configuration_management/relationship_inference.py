import re
from collections import defaultdict
from typing import List, Dict, Any, Optional
from data_nexus.data_access.metadata_models import Table, Constraint
from data_nexus.log_handle.log import log_info, log_error

DEFAULT_GENERIC_COLUMNS = {
    # Generic identifiers
    'id', 'guid', 'rowguid', 'uuid', 'code', 'codigo', 'cd', 'cod', 'identifier',
    # Names & descriptions
    'name', 'nome', 'ds', 'description', 'descricao', 'title', 'titulo', 'label',
    # Dates & timestamps
    'date', 'data', 'dt', 'created_at', 'createdat', 'created_date', 'createddate',
    'criado_em', 'updated_at', 'updatedat', 'updated_date', 'updateddate', 'atualizado_em',
    'modified_date', 'modifieddate', 'deleted_at', 'deletedat', 'excluido_em',
    'start_date', 'startdate', 'end_date', 'enddate', 'data_inicio', 'data_fim',
    'timestamp', 'data_hora', 'datetime', 'dthr',
    # Status & types
    'status', 'state', 'situacao', 'type', 'tipo', 'category', 'categoria', 'flag',
    # Booleans & flags
    'active', 'ativo', 'is_active', 'isactive', 'fl_ativo', 'enabled', 'habilitado',
    'deleted', 'excluido', 'fl_excluido',
    # Generic metrics / values
    'value', 'valor', 'val', 'quantity', 'quantidade', 'qty', 'amount', 'total',
    'version', 'versao', 'num', 'numero', 'number', 'count', 'seq', 'sequence',
    'order', 'ordem', 'ordernumber',
    # Texts & notes
    'comment', 'comments', 'comentario', 'obs', 'observacao', 'notes', 'nota', 'text', 'texto'
}


def normalize_col_name(name: str) -> str:
    """Normalize column name to lowercase trimmed string."""
    return name.strip().lower() if name else ""


def is_column_generic(col_name: str, table_count: int = 0, total_tables: int = 0) -> bool:
    """Determine whether a column is likely generic / metadata rather than an entity FK."""
    norm = normalize_col_name(col_name)
    if not norm:
        return True
    
    # Check exact match against known generic names
    if norm in DEFAULT_GENERIC_COLUMNS:
        return True
    
    # If the column appears in more than 40% of the tables (and >= 3 tables), it's highly generic
    if total_tables >= 4 and table_count >= 3 and (table_count / total_tables) >= 0.4:
        return True
    
    return False


def find_candidate_columns(tables: List[Table], saved_config: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """
    Analyzes tables and returns candidate columns (columns present in 2 or more tables).
    Each candidate includes name, table_count, tables, is_generic, and enabled state.
    """
    total_tables = len(tables)
    col_to_tables = defaultdict(list)
    col_display_name = {}

    for table in tables:
        seen_in_table = set()
        for col in table.columns:
            norm = normalize_col_name(col.name)
            if norm and norm not in seen_in_table:
                seen_in_table.add(norm)
                col_to_tables[norm].append(table.name)
                if norm not in col_display_name:
                    col_display_name[norm] = col.name

    saved_settings = {}
    if saved_config and isinstance(saved_config, dict):
        saved_settings = saved_config.get("column_settings", {}) or {}

    candidates = []
    for norm_name, tbl_names in col_to_tables.items():
        if len(tbl_names) >= 2:
            display_name = col_display_name.get(norm_name, norm_name)
            table_count = len(tbl_names)
            generic = is_column_generic(norm_name, table_count, total_tables)

            # Check if user had a saved setting for this column (case-insensitive check)
            if display_name in saved_settings:
                enabled = bool(saved_settings[display_name])
            elif norm_name in saved_settings:
                enabled = bool(saved_settings[norm_name])
            else:
                # Default: generic columns disabled, domain columns enabled
                enabled = not generic

            candidates.append({
                "name": display_name,
                "norm_name": norm_name,
                "table_count": table_count,
                "tables": sorted(tbl_names),
                "is_generic": generic,
                "enabled": enabled
            })

    # Sort: non-generic first, then by table_count descending, then alphabetical
    candidates.sort(key=lambda c: (c["is_generic"], -c["table_count"], c["name"].lower()))
    return candidates


def _extract_stem(col_name: str) -> str:
    """Extract base entity name from column name, e.g. customer_id -> customer, ID_User -> user."""
    norm = normalize_col_name(col_name)
    # Remove prefixes like id_, cd_, cod_
    norm = re.sub(r'^(id_|cd_|cod_)', '', norm)
    # Remove suffixes like _id, id, _key, key, _code, code, _cd, cd
    norm = re.sub(r'(_id|id|_key|key|_code|code|_cd|cd)$', '', norm)
    return norm.strip('_')


def _find_parent_table(col_name: str, candidate_tables: List[Table]) -> Optional[Table]:
    """Identify which table among candidates is most likely the parent / referenced table."""
    norm_col = normalize_col_name(col_name)
    stem = _extract_stem(col_name)

    # 1. Match Table Name Heuristic
    if stem and len(stem) >= 3:
        for table in candidate_tables:
            tbl_norm = normalize_col_name(table.name)
            # Remove common prefixes like tb_, tbl_
            clean_tbl = re.sub(r'^(tb_|tbl_|dim_|fact_)', '', tbl_norm)
            if clean_tbl in (stem, stem + 's', stem + 'es', stem.rstrip('s')):
                return table

    # 2. Check for Primary Key or Unique Index on col_name
    for table in candidate_tables:
        # Check indexes for unique constraint on this column
        for idx in table.indexes:
            if normalize_col_name(idx.column_name) == norm_col and not idx.non_unique:
                return table
        # Check constraints for PRIMARY or PK constraint on this column
        for con in table.constraints:
            if normalize_col_name(con.column_name) == norm_col:
                con_name_upper = (con.name or "").upper()
                if "PRIMARY" in con_name_upper or con_name_upper.startswith("PK"):
                    return table

    # 3. Smallest row count / dimension table heuristic
    sorted_by_tuples = sorted(candidate_tables, key=lambda t: (t.num_tuples or 0, len(t.columns)))
    return sorted_by_tuples[0] if sorted_by_tuples else None


def clean_inferred_constraints(tables: List[Table]) -> None:
    """Removes all previously generated inferred constraints from tables."""
    for table in tables:
        table.constraints = [
            c for c in table.constraints
            if not (
                (c.name and c.name.startswith("INFERRED_")) or
                getattr(c, "is_inferred", False)
            )
        ]


def apply_inferred_relationships(tables: List[Table], enabled_columns: List[str]) -> List[Table]:
    """
    Applies inferred foreign key constraints to tables based on enabled candidate columns.
    Modifies tables in-place and returns tables.
    """
    # First, remove prior inferred constraints
    clean_inferred_constraints(tables)

    if not enabled_columns:
        return tables

    norm_enabled = {normalize_col_name(col) for col in enabled_columns if col}

    for norm_col in norm_enabled:
        # Find all tables that have this column
        matching_tables = []
        col_actual_name = norm_col
        for table in tables:
            for col in table.columns:
                if normalize_col_name(col.name) == norm_col:
                    matching_tables.append(table)
                    col_actual_name = col.name
                    break

        if len(matching_tables) < 2:
            continue

        parent = _find_parent_table(norm_col, matching_tables)
        if not parent:
            parent = matching_tables[0]

        # Connect each other table to the parent
        for child in matching_tables:
            if child.name == parent.name:
                continue

            # Check if child already references parent to avoid duplicate constraints
            already_references = any(
                c.referenced_table_name == parent.name
                for c in child.constraints
                if c.referenced_table_name
            )
            if already_references:
                continue

            inferred_constraint = Constraint(
                name=f"INFERRED_{col_actual_name}",
                column_name=col_actual_name,
                referenced_table_schema=None,
                referenced_table_name=parent.name,
                referenced_column_name=col_actual_name,
                is_inferred=True
            )
            child.constraints.append(inferred_constraint)

    return tables


def count_inferred_relationships(tables: List[Table]) -> int:
    """Counts the total number of inferred constraints across all tables."""
    count = 0
    for table in tables:
        for c in table.constraints:
            if (c.name and c.name.startswith("INFERRED_")) or getattr(c, "is_inferred", False):
                count += 1
    return count
