from data_nexus.log_handle.log import *
from data_nexus.database_connections.sqlserver_connection import SQLServerConnection
from data_nexus.data_access.metadata_models import Table, Column, Constraint, Index


def sqlserver_fetch_tables(sqlserver: SQLServerConnection, excluded_tables=[]):
    table_data = []
    for table in sqlserver_database_info(sqlserver):
        if table not in excluded_tables:
            meta = sqlserver_metadata_table(sqlserver, table)
            if meta:
                table_data.append(meta)
    return table_data


def sqlserver_database_info(sqlserver: SQLServerConnection):
    try:
        with sqlserver.connection.cursor() as cursor:
            if sqlserver.schema:
                sql = f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE' AND TABLE_SCHEMA = '{sqlserver.schema}';"
            else:
                sql = "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_TYPE = 'BASE TABLE';"
            log_debug(f"Query: {sql}")
            cursor.execute(sql)
            return [table[0] for table in cursor.fetchall()]
    except Exception as e:
        log_error(f"Error searching metadata for schema {sqlserver.schema}: {e}")
        raise e


def sqlserver_metadata_table(sqlserver: SQLServerConnection, table_name):
    try:
        table = fetch_table_info(sqlserver, table_name)
        if table is None:
            return None
        columns = fetch_columns_info(sqlserver, table_name)
        if columns is None:
            return None
        constraints = fetch_constraints_info(sqlserver, table_name)
        if constraints is None:
            return None
        indexes = fetch_indexes_info(sqlserver, table_name)
        if indexes is None:
            return None
        table.columns = columns
        table.constraints = constraints
        table.indexes = indexes
        return table
    except Exception as e:
        log_error(f"Error searching metadata for table {sqlserver.schema}.{table_name}: {e}")
        raise e


def fetch_table_info(sqlserver: SQLServerConnection, table_name):
    try:
        with sqlserver.connection.cursor() as cursor:
            # First try fast partition row count (instantaneous for large schemas)
            try:
                if sqlserver.schema:
                    sql_fast = f"""
                    SELECT COALESCE(SUM(p.rows), 0) AS num_tuples
                    FROM sys.partitions p
                    JOIN sys.tables t ON p.object_id = t.object_id
                    JOIN sys.schemas s ON t.schema_id = s.schema_id
                    WHERE p.index_id IN (0, 1) 
                      AND t.name = '{table_name}' 
                      AND s.name = '{sqlserver.schema}';
                    """
                else:
                    sql_fast = f"""
                    SELECT COALESCE(SUM(p.rows), 0) AS num_tuples
                    FROM sys.partitions p
                    JOIN sys.tables t ON p.object_id = t.object_id
                    WHERE p.index_id IN (0, 1) 
                      AND t.name = '{table_name}';
                    """
                log_debug(f"Query: {sql_fast}")
                cursor.execute(sql_fast)
                result = cursor.fetchone()
                if result is not None and result[0] is not None:
                    return Table(name=table_name, num_tuples=int(result[0]))
            except Exception as e_fast:
                log_debug(f"Fast count fallback for {table_name}: {e_fast}")

            # Fallback to SELECT COUNT(*)
            table_ref = f"[{sqlserver.schema}].[{table_name}]" if sqlserver.schema else f"[{table_name}]"
            sql = f"SELECT COUNT(*) as num_tuples FROM {table_ref};"
            log_debug(f"Query: {sql}")
            cursor.execute(sql)
            result = cursor.fetchone()
            num_tuples = result[0] if result else 0
            return Table(name=table_name, num_tuples=int(num_tuples))
    except Exception as e:
        log_error(f"Error searching metadata for table {sqlserver.schema}.{table_name}: {e}")
        raise e


def fetch_columns_info(sqlserver: SQLServerConnection, table_name):
    try:
        if sqlserver.schema:
            sql = f"""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = '{sqlserver.schema}' AND TABLE_NAME = '{table_name}';
            """
        else:
            sql = f"""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, COLUMN_DEFAULT
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = '{table_name}';
            """
        log_debug(f"Query: {sql}")

        with sqlserver.connection.cursor() as cursor:
            cursor.execute(sql)
            columns = []
            for row in cursor.fetchall():
                column_name, data_type, is_nullable, column_default = row
                nullable = (is_nullable == 'YES')
                column = Column(name=column_name, data_type=data_type, nullable=nullable, default=column_default)
                columns.append(column)
            return columns
    except Exception as e:
        log_error(f"Error fetching columns info for table {sqlserver.schema}.{table_name}: {e}")
        raise e


def fetch_constraints_info(sqlserver: SQLServerConnection, table_name):
    try:
        if sqlserver.schema:
            sql = f"""
            SELECT 
                fk.name AS constraint_name,
                col1.name AS column_name,
                s2.name AS referenced_table_schema,
                t2.name AS referenced_table_name,
                col2.name AS referenced_column_name
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.tables t1 ON fkc.parent_object_id = t1.object_id
            JOIN sys.schemas s1 ON t1.schema_id = s1.schema_id
            JOIN sys.columns col1 ON fkc.parent_object_id = col1.object_id AND fkc.parent_column_id = col1.column_id
            JOIN sys.tables t2 ON fkc.referenced_object_id = t2.object_id
            JOIN sys.schemas s2 ON t2.schema_id = s2.schema_id
            JOIN sys.columns col2 ON fkc.referenced_object_id = col2.object_id AND fkc.referenced_column_id = col2.column_id
            WHERE t1.name = '{table_name}' AND s1.name = '{sqlserver.schema}';
            """
        else:
            sql = f"""
            SELECT 
                fk.name AS constraint_name,
                col1.name AS column_name,
                s2.name AS referenced_table_schema,
                t2.name AS referenced_table_name,
                col2.name AS referenced_column_name
            FROM sys.foreign_keys fk
            JOIN sys.foreign_key_columns fkc ON fk.object_id = fkc.constraint_object_id
            JOIN sys.tables t1 ON fkc.parent_object_id = t1.object_id
            JOIN sys.columns col1 ON fkc.parent_object_id = col1.object_id AND fkc.parent_column_id = col1.column_id
            JOIN sys.tables t2 ON fkc.referenced_object_id = t2.object_id
            JOIN sys.schemas s2 ON t2.schema_id = s2.schema_id
            JOIN sys.columns col2 ON fkc.referenced_object_id = col2.object_id AND fkc.referenced_column_id = col2.column_id
            WHERE t1.name = '{table_name}';
            """
        log_debug(f"Query: {sql}")

        with sqlserver.connection.cursor() as cursor:
            cursor.execute(sql)
            constraints = []
            for row in cursor.fetchall():
                constraint_name, column_name, referenced_table_schema, referenced_table_name, referenced_column_name = row
                constraint = Constraint(
                    name=constraint_name,
                    column_name=column_name,
                    referenced_table_schema=referenced_table_schema,
                    referenced_table_name=referenced_table_name,
                    referenced_column_name=referenced_column_name
                )
                constraints.append(constraint)
            return constraints
    except Exception as e:
        log_error(f"Error fetching constraints info for table {sqlserver.schema}.{table_name}: {e}")
        raise e


def fetch_indexes_info(sqlserver: SQLServerConnection, table_name):
    try:
        if sqlserver.schema:
            sql = f"""
            SELECT 
                i.name AS index_name,
                c.name AS column_name,
                c.is_nullable AS nullable,
                i.type_desc AS index_type,
                CASE WHEN i.is_unique = 1 THEN 0 ELSE 1 END AS non_unique
            FROM sys.indexes i
            JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            JOIN sys.tables t ON i.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE t.name = '{table_name}' 
              AND s.name = '{sqlserver.schema}'
              AND i.is_hypothetical = 0
              AND i.name IS NOT NULL;
            """
        else:
            sql = f"""
            SELECT 
                i.name AS index_name,
                c.name AS column_name,
                c.is_nullable AS nullable,
                i.type_desc AS index_type,
                CASE WHEN i.is_unique = 1 THEN 0 ELSE 1 END AS non_unique
            FROM sys.indexes i
            JOIN sys.index_columns ic ON i.object_id = ic.object_id AND i.index_id = ic.index_id
            JOIN sys.columns c ON ic.object_id = c.object_id AND ic.column_id = c.column_id
            JOIN sys.tables t ON i.object_id = t.object_id
            WHERE t.name = '{table_name}' 
              AND i.is_hypothetical = 0
              AND i.name IS NOT NULL;
            """
        log_debug(f"Query: {sql}")

        with sqlserver.connection.cursor() as cursor:
            cursor.execute(sql)
            indexes = []
            for row in cursor.fetchall():
                index_name, column_name, nullable, index_type, non_unique = row
                index = Index(
                    name=index_name,
                    column_name=column_name,
                    nullable=bool(nullable),
                    index_type=index_type,
                    non_unique=bool(non_unique),
                    excluded=False
                )
                indexes.append(index)
            return indexes
    except Exception as e:
        log_error(f"Error fetching indexes info for table {sqlserver.schema}.{table_name}: {e}")
        raise e
