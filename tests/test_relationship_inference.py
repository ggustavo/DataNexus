import unittest
import os
import json
from data_nexus.data_access.metadata_models import Table, Column, Constraint, Index
from data_nexus.configuration_management.relationship_inference import (
    is_column_generic,
    find_candidate_columns,
    apply_inferred_relationships,
    clean_inferred_constraints,
    count_inferred_relationships,
    _find_parent_table,
    _extract_stem
)
from data_nexus.app import app, tables_buffer


class TestRelationshipInference(unittest.TestCase):

    def setUp(self):
        # Create mock tables simulating a database without foreign keys
        self.customers_table = Table(
            name="customer",
            num_tuples=100,
            columns=[
                Column(name="customer_id", data_type="int", nullable=False, default=None),
                Column(name="name", data_type="varchar(100)", nullable=False, default=None),
                Column(name="created_at", data_type="datetime", nullable=False, default=None),
            ],
            constraints=[
                Constraint(name="PK_customer", column_name="customer_id",
                           referenced_table_schema=None, referenced_table_name=None, referenced_column_name=None)
            ],
            indexes=[
                Index(name="PK_customer", column_name="customer_id", nullable=False,
                      index_type="CLUSTERED", non_unique=0, excluded=False)
            ]
        )

        self.orders_table = Table(
            name="orders",
            num_tuples=1000,
            columns=[
                Column(name="order_id", data_type="int", nullable=False, default=None),
                Column(name="customer_id", data_type="int", nullable=False, default=None),
                Column(name="created_at", data_type="datetime", nullable=False, default=None),
                Column(name="total_amount", data_type="decimal(10,2)", nullable=False, default=None),
            ],
            constraints=[],  # No foreign keys!
            indexes=[
                Index(name="PK_orders", column_name="order_id", nullable=False,
                      index_type="CLUSTERED", non_unique=0, excluded=False)
            ]
        )

        self.payments_table = Table(
            name="payments",
            num_tuples=1200,
            columns=[
                Column(name="payment_id", data_type="int", nullable=False, default=None),
                Column(name="customer_id", data_type="int", nullable=False, default=None),
                Column(name="created_at", data_type="datetime", nullable=False, default=None),
                Column(name="amount", data_type="decimal(10,2)", nullable=False, default=None),
            ],
            constraints=[],
            indexes=[]
        )

        self.tables = [self.customers_table, self.orders_table, self.payments_table]

    def test_extract_stem(self):
        self.assertEqual(_extract_stem("customer_id"), "customer")
        self.assertEqual(_extract_stem("id_cliente"), "cliente")
        self.assertEqual(_extract_stem("ProductID"), "product")
        self.assertEqual(_extract_stem("order_key"), "order")

    def test_is_column_generic(self):
        # Generic columns
        self.assertTrue(is_column_generic("name"))
        self.assertTrue(is_column_generic("id"))
        self.assertTrue(is_column_generic("created_at"))
        self.assertTrue(is_column_generic("modifieddate"))
        self.assertTrue(is_column_generic("rowguid"))
        self.assertTrue(is_column_generic("status"))
        
        # Domain columns (not generic)
        self.assertFalse(is_column_generic("customer_id"))
        self.assertFalse(is_column_generic("product_code"))
        self.assertFalse(is_column_generic("salesorderid"))

    def test_find_candidate_columns(self):
        candidates = find_candidate_columns(self.tables)
        candidate_names = [c["name"] for c in candidates]
        
        # customer_id and created_at appear in all 3 tables
        self.assertIn("customer_id", candidate_names)
        self.assertIn("created_at", candidate_names)
        # order_id appears only in orders, so should NOT be a candidate
        self.assertNotIn("order_id", candidate_names)
        self.assertNotIn("payment_id", candidate_names)

        # Check generic classification
        cust_cand = next(c for c in candidates if c["name"] == "customer_id")
        self.assertFalse(cust_cand["is_generic"])
        self.assertTrue(cust_cand["enabled"])  # Non-generic defaults to True
        self.assertEqual(cust_cand["table_count"], 3)
        self.assertEqual(set(cust_cand["tables"]), {"customer", "orders", "payments"})

        created_cand = next(c for c in candidates if c["name"] == "created_at")
        self.assertTrue(created_cand["is_generic"])
        self.assertFalse(created_cand["enabled"])  # Generic defaults to False

    def test_find_candidate_columns_with_saved_config(self):
        saved_config = {
            "enabled": True,
            "column_settings": {
                "created_at": True,   # user manually enabled generic column
                "customer_id": False  # user manually disabled customer_id
            }
        }
        candidates = find_candidate_columns(self.tables, saved_config)
        cust_cand = next(c for c in candidates if c["name"] == "customer_id")
        created_cand = next(c for c in candidates if c["name"] == "created_at")

        self.assertFalse(cust_cand["enabled"])
        self.assertTrue(created_cand["enabled"])

    def test_find_parent_table(self):
        # For customer_id, customer table should be identified as parent (name matches customer)
        parent = _find_parent_table("customer_id", self.tables)
        self.assertIsNotNone(parent)
        self.assertEqual(parent.name, "customer")

    def test_apply_inferred_relationships(self):
        # Initially orders and payments have 0 constraints
        self.assertEqual(len(self.orders_table.constraints), 0)
        self.assertEqual(len(self.payments_table.constraints), 0)

        # Apply inferred relationship for customer_id
        apply_inferred_relationships(self.tables, ["customer_id"])

        # orders and payments should now have an inferred FK constraint to customer
        self.assertEqual(len(self.orders_table.constraints), 1)
        self.assertEqual(len(self.payments_table.constraints), 1)

        ord_con = self.orders_table.constraints[0]
        self.assertEqual(ord_con.name, "INFERRED_customer_id")
        self.assertEqual(ord_con.column_name, "customer_id")
        self.assertEqual(ord_con.referenced_table_name, "customer")
        self.assertEqual(ord_con.referenced_column_name, "customer_id")
        self.assertTrue(ord_con.is_inferred)

        self.assertEqual(count_inferred_relationships(self.tables), 2)

    def test_clean_inferred_constraints(self):
        apply_inferred_relationships(self.tables, ["customer_id"])
        self.assertEqual(count_inferred_relationships(self.tables), 2)

        # Clean inferred constraints
        clean_inferred_constraints(self.tables)
        self.assertEqual(count_inferred_relationships(self.tables), 0)
        self.assertEqual(len(self.orders_table.constraints), 0)
        # customer's original PK constraint must still be intact
        self.assertEqual(len(self.customers_table.constraints), 1)
        self.assertEqual(self.customers_table.constraints[0].name, "PK_customer")


class TestRelationshipEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()
        self.test_conn_id = "test_conn_mock"
        self.test_file = f"{self.test_conn_id}.json"

        # Create mock tables
        t1 = Table("users", 50, columns=[
            Column("user_id", "int", False, None),
            Column("name", "varchar", False, None)
        ])
        t2 = Table("orders", 500, columns=[
            Column("order_id", "int", False, None),
            Column("user_id", "int", False, None),
            Column("name", "varchar", False, None)
        ])
        
        # Save mock cache file
        with open(self.test_file, "w") as f:
            json.dump([t1.to_dict(), t2.to_dict()], f)

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if self.test_conn_id in tables_buffer:
            del tables_buffer[self.test_conn_id]

    def test_get_config_no_cache(self):
        response = self.client.post("/relationship_config", json={"id": "non_existent_connection"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertFalse(data["has_cache"])
        self.assertIn("error", data)

    def test_get_config_with_cache(self):
        response = self.client.post("/relationship_config", json={"id": self.test_conn_id})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data["has_cache"])
        self.assertEqual(data["total_tables"], 2)
        candidates = data["candidates"]
        cand_names = [c["name"] for c in candidates]
        self.assertIn("user_id", cand_names)
        self.assertIn("name", cand_names)

    def test_save_config_and_persist(self):
        # Save configuration enabling user_id and disabling name
        save_resp = self.client.post("/save_relationship_config", json={
            "id": self.test_conn_id,
            "enabled": True,
            "column_settings": {
                "user_id": True,
                "name": False
            }
        })
        self.assertEqual(save_resp.status_code, 200)
        save_data = save_resp.get_json()
        self.assertTrue(save_data["success"])
        self.assertEqual(save_data["relationships_count"], 1)

        # Verify persistence in JSON file
        with open(self.test_file, "r") as f:
            persisted = json.load(f)
        self.assertIn("relationship_config", persisted)
        self.assertTrue(persisted["relationship_config"]["enabled"])
        self.assertTrue(persisted["relationship_config"]["column_settings"]["user_id"])
        self.assertFalse(persisted["relationship_config"]["column_settings"]["name"])

        # Fetch config again to verify it loads persisted settings
        get_resp = self.client.post("/relationship_config", json={"id": self.test_conn_id})
        get_data = get_resp.get_json()
        self.assertTrue(get_data["enabled"])
        user_id_cand = next(c for c in get_data["candidates"] if c["name"] == "user_id")
        name_cand = next(c for c in get_data["candidates"] if c["name"] == "name")
        self.assertTrue(user_id_cand["enabled"])
        self.assertFalse(name_cand["enabled"])


if __name__ == '__main__':
    unittest.main()
