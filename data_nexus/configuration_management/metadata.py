import json
import os
from data_nexus.log_handle.log import *
from data_nexus.data_access.metadata_models import Table
from data_nexus.configuration_management.db_credentials import DBCredentials
from data_nexus.database_connections.mysql_connection import MySQLConnection
from data_nexus.database_connections.postgresql_connection import PostgreSQLConnection
from data_nexus.database_connections.sqlserver_connection import SQLServerConnection

def save_database_json_file(tables, file_name, relationship_config=None):
    try:
        log_info(f"Saving JSON file: {file_name}")
        tables_data = [table.to_dict() for table in tables]
        
        # If no config passed, check if existing file already had relationship_config
        if relationship_config is None and os.path.exists(file_name):
            try:
                with open(file_name, "r") as f:
                    existing = json.load(f)
                    if isinstance(existing, dict) and "relationship_config" in existing:
                        relationship_config = existing["relationship_config"]
            except Exception:
                pass

        if relationship_config is not None:
            data = {
                "relationship_config": relationship_config,
                "tables": tables_data
            }
        else:
            data = tables_data

        with open(file_name, "w+") as outfile:
            json.dump(data, outfile, indent=4)
    except Exception as e:
        log_error(f"Error occurred while saving JSON file: {e}")
        

def load_database_json_file(file_name):
    try:
        with open(file_name, "r") as f:
            log_info(f"Loading JSON file: {file_name}")
            data = json.load(f)
            if isinstance(data, dict):
                tables_data = data.get("tables", [])
            elif isinstance(data, list):
                tables_data = data
            else:
                tables_data = []
            tables = dict_list_to_table_list(tables_data)
            return tables
    except FileNotFoundError:
        log_error(f"File '{file_name}' not found.")
        return None
    except Exception as e:
        log_error(f"Error occurred while loading JSON file: {e}")
        return None


def load_relationship_config_from_file(file_name):
    try:
        if not os.path.exists(file_name):
            return {"enabled": False, "column_settings": {}}
        with open(file_name, "r") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data.get("relationship_config", {"enabled": False, "column_settings": {}})
            return {"enabled": False, "column_settings": {}}
    except Exception as e:
        log_error(f"Error occurred while loading relationship config: {e}")
        return {"enabled": False, "column_settings": {}}


def dict_list_to_table_list(data):
    tables = []
    for table in data:
        tables.append(Table.from_dict(table))
    return tables



def save_connections_json_file(connections, file_name):
    try:
        log_error(f"Saving JSON file: {file_name}")
        data = []
        for id, connection in connections.items():
            record = {
                'id': id,
                'type': connection.__class__.__name__,
                'credentials': connection.db_credentials.to_dict()
            }
            data.append(record)
        with open(file_name, "w+") as outfile:
            json.dump(data, outfile, indent=4)
    except Exception as e:
        log_error(f"Error occurred while saving JSON file: {e}")
        
        
def load_connections_json_file(file_name):
    try:
        with open(file_name, "r") as f:
            log_info(f"Loading JSON file: {file_name}")
            data = json.load(f)
            connections = dict_list_to_connection_list(data)
            
            return connections
    except FileNotFoundError:
        log_error(f"File '{file_name}' not found.")
        return None
    except Exception as e:
        log_error(f"Error occurred while loading JSON file: {e}")
        return None
    
def dict_list_to_connection_list(data):
    connections = {}
    for record in data:
        connection = None
        if record['type'] == 'MySQLConnection':
            credentials = DBCredentials.from_dict(record['credentials'])
            connection = MySQLConnection(credentials)
        if record['type'] == 'PostgreSQLConnection':
            credentials = DBCredentials.from_dict(record['credentials'])
            connection = PostgreSQLConnection(credentials)
        if record['type'] == 'SQLServerConnection':
            credentials = DBCredentials.from_dict(record['credentials'])
            connection = SQLServerConnection(credentials)
        connections.update({record['id'] : connection})
    return connections