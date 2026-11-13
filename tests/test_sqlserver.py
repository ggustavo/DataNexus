import unittest
from unittest.mock import MagicMock, patch
from data_nexus.configuration_management.db_credentials import DBCredentials
from data_nexus.database_connections.sqlserver_connection import SQLServerConnection
from data_nexus.data_access.sqlserver_metadata_reader import (
    sqlserver_fetch_tables,
    sqlserver_database_info,
    fetch_table_info,
    fetch_columns_info,
    fetch_constraints_info,
    fetch_indexes_info,
)
from data_nexus.data_access.metadata_models import Table, Column, Constraint, Index
from data_nexus.configuration_management.metadata import dict_list_to_connection_list
from data_nexus.graphs.graphs_processing import generate_graph


class TestSQLServerIntegration(unittest.TestCase):

    def setUp(self):
        self.credentials = DBCredentials(
            database="test_db",
            user="test_user",
            password="fake_password",
            host="127.0.0.1",
            port="1433",
            schema="dbo"
        )
        self.sqlserver_conn = SQLServerConnection(self.credentials)

    @patch("data_nexus.database_connections.sqlserver_connection.create_engine")
    def test_connection_create_and_close(self, mock_create_engine):
        mock_engine = MagicMock()
        mock_raw_conn = MagicMock()
        mock_engine.raw_connection.return_value = mock_raw_conn
        mock_create_engine.return_value = mock_engine

        self.sqlserver_conn.create()
        self.assertEqual(self.sqlserver_conn.connection, mock_raw_conn)
        self.assertEqual(self.sqlserver_conn.engine, mock_engine)

        self.sqlserver_conn.close()
        mock_raw_conn.close.assert_called_once()
        mock_engine.dispose.assert_called_once()
        self.assertIsNone(self.sqlserver_conn.connection)
        self.assertIsNone(self.sqlserver_conn.engine)

    def test_dict_list_to_connection_list(self):
        data = [
            {
                "id": "test_sqlserver",
                "type": "SQLServerConnection",
                "credentials": {
                    "database": "test_db",
                    "user": "test_user",
                    "password": "fake_password",
                    "host": "localhost",
                    "port": "1433",
                    "schema": "dbo"
                }
            }
        ]
        connections = dict_list_to_connection_list(data)
        self.assertIn("test_sqlserver", connections)
        self.assertIsInstance(connections["test_sqlserver"], SQLServerConnection)
        self.assertEqual(connections["test_sqlserver"].schema, "dbo")

    def test_sqlserver_database_info(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("TableA",), ("TableB",)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        self.sqlserver_conn.connection = mock_conn

        tables = sqlserver_database_info(self.sqlserver_conn)
        self.assertEqual(tables, ["TableA", "TableB"])

    def test_fetch_table_info(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Fast count returns 1500 rows
        mock_cursor.fetchone.return_value = (1500,)
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        self.sqlserver_conn.connection = mock_conn

        table = fetch_table_info(self.sqlserver_conn, "TableA")
        self.assertIsNotNone(table)
        self.assertEqual(table.name, "TableA")
        self.assertEqual(table.num_tuples, 1500)

    def test_fetch_columns_info(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("id", "int", "NO", None),
            ("name", "varchar", "YES", None)
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        self.sqlserver_conn.connection = mock_conn

        columns = fetch_columns_info(self.sqlserver_conn, "TableA")
        self.assertEqual(len(columns), 2)
        self.assertEqual(columns[0].name, "id")
        self.assertFalse(columns[0].nullable)
        self.assertEqual(columns[1].name, "name")
        self.assertTrue(columns[1].nullable)

    def test_fetch_constraints_info(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("FK_TableA_TableB", "b_id", "dbo", "TableB", "id")
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        self.sqlserver_conn.connection = mock_conn

        constraints = fetch_constraints_info(self.sqlserver_conn, "TableA")
        self.assertEqual(len(constraints), 1)
        self.assertEqual(constraints[0].name, "FK_TableA_TableB")
        self.assertEqual(constraints[0].referenced_table_name, "TableB")

    def test_fetch_indexes_info(self):
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            ("PK_TableA", "id", False, "CLUSTERED", 0)
        ]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
        self.sqlserver_conn.connection = mock_conn

        indexes = fetch_indexes_info(self.sqlserver_conn, "TableA")
        self.assertEqual(len(indexes), 1)
        self.assertEqual(indexes[0].name, "PK_TableA")
        self.assertEqual(indexes[0].index_type, "CLUSTERED")
        self.assertFalse(indexes[0].non_unique)

    def test_generate_graph_with_sqlserver_tables(self):
        table_b = Table(name="TableB", num_tuples=50)
        table_a = Table(
            name="TableA",
            num_tuples=100,
            constraints=[
                Constraint("FK_A_B", "b_id", "dbo", "TableB", "id")
            ]
        )

        graph = generate_graph([table_a, table_b], "graph_tuples", "graph_both")
        self.assertIn("nodes", graph)
        self.assertIn("links", graph)
        self.assertEqual(len(graph["nodes"]), 2)
        self.assertEqual(len(graph["links"]), 1)
        self.assertEqual(graph["links"][0]["source"], "TableA")
        self.assertEqual(graph["links"][0]["target"], "TableB")


if __name__ == '__main__':
    unittest.main()
