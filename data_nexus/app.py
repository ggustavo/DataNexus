import os
from data_nexus.log_handle.log import *
from flask import Flask, render_template, request, jsonify
from data_nexus.database_connections.mysql_connection import MySQLConnection
from data_nexus.database_connections.postgresql_connection import PostgreSQLConnection
from data_nexus.database_connections.sqlserver_connection import SQLServerConnection
from data_nexus.configuration_management.db_credentials import DBCredentials
from data_nexus.data_access.postgresql_metadata_reader import postgres_fetch_tables
from data_nexus.data_access.mysql_metadata_reader import mysql_fetch_tables
from data_nexus.data_access.sqlserver_metadata_reader import sqlserver_fetch_tables
from data_nexus.configuration_management.utils import unique_key
from data_nexus.configuration_management.metadata import (
    save_database_json_file, load_database_json_file,
    save_connections_json_file, load_connections_json_file,
    load_relationship_config_from_file
)
from data_nexus.configuration_management.relationship_inference import (
    find_candidate_columns, apply_inferred_relationships,
    clean_inferred_constraints, count_inferred_relationships
)
from data_nexus.graphs.graphs_processing import generate_graph

use_memory_buffer = True
use_file_buffer = True

app = Flask(__name__)

connections_file = 'connections.json'

tables_buffer = {}
connections_buffer = {}


# Load tables and connections from JSON files
load = load_connections_json_file(connections_file)
if load != None:
    connections_buffer = load

#t3 = load_database_json_file('202406-2021-1239-0ada48f3-c220-427c-876a-73eebd79efff.json')
#generate_graph(t3)

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
        return response

@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

@app.route('/')
def hello_world():
    return render_template('index.html')


@app.route('/connections', methods=['POST', 'OPTIONS'])
def get_connections():
    global connections_buffer

    if connections_buffer is None or not connections_buffer or len(connections_buffer) == 0:
        return jsonify([]), 200
    
    try:
        connections = []
        for id, connection in connections_buffer.items():
            type = None
            
            if connection.__class__.__name__ == 'MySQLConnection':
                type = "mysql"
            if connection.__class__.__name__ == 'PostgreSQLConnection':
                type = "postgresql"
            if connection.__class__.__name__ == 'SQLServerConnection':
                type = "sqlserver"
                
            record = {
                'id': id,
                "dbms":type,
                "host":connection.db_credentials.host,
                "port":connection.db_credentials.port, 
                "database":connection.db_credentials.database,
                "schema":connection.db_credentials.schema, 
                "user":connection.db_credentials.user, 
                "password":connection.db_credentials.password,
                "id":id,
                "item":None
            }
            
            connections.append(record)
        return jsonify(connections), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/tables', methods=['POST', 'OPTIONS'])
def get_tables():
    try:
        data = request.get_json()
        if not data:
            raise ValueError("No JSON data provided")

        connection_id = data['id']
        tables = restore_tables(connection_id)
        tables = [table.to_dict() for table in tables]
        return jsonify(tables), 200
    
    except Exception as e:
        return jsonify({'error': str(e)}), 400


@app.route('/graph', methods=['POST', 'OPTIONS'])
def get_graph():
    try:
            data = request.get_json()
            if not data:
                raise ValueError("No JSON data provided")

            connection_id = data['id']
            type = data['type']
            centrality_type = data['centrality_type']
            if centrality_type == None:
                centrality_type = 'graph_both'
                
            tables = restore_tables(connection_id)
            graph = generate_graph(tables, type, centrality_type)
            return jsonify(graph), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400
    
@app.route('/metadadata', methods=['POST', 'OPTIONS'])
def get_metadadata():
    try:
            data = request.get_json()
            if not data:
                raise ValueError("No JSON data provided")

            connection_id = data['id']
            name = data['name']
            tables = restore_tables(connection_id)
            result = None
            for table in tables:
                if table.name == name:
                    result = table.to_dict()
            if result == None:
                raise ValueError("Table not found")
            return jsonify(result), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 400



@app.route('/relationship_config', methods=['POST', 'OPTIONS'])
def get_relationship_config():
    global tables_buffer
    global connections_buffer
    try:
        data = request.get_json()
        if not data:
            raise ValueError("No JSON data provided")

        connection_id = data.get('id')
        if not connection_id:
            raise ValueError("Connection ID is required")

        file_name = f'{connection_id}.json'
        has_file = os.path.exists(file_name)
        has_buffer = connection_id in tables_buffer

        if not has_file and not has_buffer:
            return jsonify({
                'has_cache': False,
                'error': 'Cache local (JSON) não encontrado para esta conexão. Você precisa analisar o banco de dados primeiro para carregar e salvar o cache local.'
            }), 200

        # Load tables from buffer or file
        if has_buffer:
            tables = tables_buffer[connection_id]
        else:
            tables = load_database_json_file(file_name)
            if use_memory_buffer and tables:
                tables_buffer.update({connection_id: tables})

        if not tables:
            return jsonify({
                'has_cache': False,
                'error': 'Não foi possível carregar as tabelas do cache.'
            }), 200

        # Load saved config
        saved_config = load_relationship_config_from_file(file_name)
        candidates = find_candidate_columns(tables, saved_config)

        return jsonify({
            'has_cache': True,
            'id': connection_id,
            'enabled': saved_config.get('enabled', False),
            'candidates': candidates,
            'total_tables': len(tables)
        }), 200

    except Exception as e:
        log_error(f"Error in get_relationship_config: {e}")
        return jsonify({'error': str(e)}), 400


@app.route('/save_relationship_config', methods=['POST', 'OPTIONS'])
def save_relationship_config():
    global tables_buffer
    global connections_buffer
    try:
        data = request.get_json()
        if not data:
            raise ValueError("No JSON data provided")

        connection_id = data.get('id')
        enabled = bool(data.get('enabled', False))
        column_settings = data.get('column_settings', {})

        if not connection_id:
            raise ValueError("Connection ID is required")

        file_name = f'{connection_id}.json'
        has_file = os.path.exists(file_name)
        has_buffer = connection_id in tables_buffer

        if not has_file and not has_buffer:
            return jsonify({
                'has_cache': False,
                'error': 'Cache local não encontrado para salvar configurações.'
            }), 400

        # Load tables
        if has_buffer:
            tables = tables_buffer[connection_id]
        else:
            tables = load_database_json_file(file_name)

        if not tables:
            return jsonify({'error': 'Tabelas não encontradas no cache.'}), 400

        # Clean prior inferred constraints
        clean_inferred_constraints(tables)

        # Apply inferred relationships if enabled
        if enabled:
            enabled_columns = [col for col, is_on in column_settings.items() if is_on]
            tables = apply_inferred_relationships(tables, enabled_columns)

        rel_config = {
            'enabled': enabled,
            'column_settings': column_settings
        }

        # Update in-memory buffer
        if use_memory_buffer:
            tables_buffer.update({connection_id: tables})

        # Save to file
        if use_file_buffer or has_file:
            save_database_json_file(tables, file_name, relationship_config=rel_config)

        inferred_count = count_inferred_relationships(tables)

        return jsonify({
            'success': True,
            'id': connection_id,
            'enabled': enabled,
            'relationships_count': inferred_count,
            'message': f'Configurações salvas com sucesso! {inferred_count} relacionamento(s) inferido(s).'
        }), 200

    except Exception as e:
        log_error(f"Error in save_relationship_config: {e}")
        return jsonify({'error': str(e)}), 400


@app.route('/validate_connection', methods=['POST', 'OPTIONS'])
def validate_connection():
    global connections_buffer
    try:
        data = request.get_json()
        if not data:
            raise ValueError("No JSON data provided")

        dbms_name = data['dbms']        
        credentials = DBCredentials(
            database = data['database'],
            user =     data['user'],
            password = data['password'],
            host =     data['host'],
            port =     data['port'],
            schema =   data['schema']
        )

        if dbms_name == 'mysql':
            mysql_conn = MySQLConnection(credentials)
            mysql_conn.create()
            if not mysql_conn.connection:
                raise ValueError("MySQL connection failed")
            mysql_conn.close()
            id = unique_key()
            connections_buffer.update({id : mysql_conn})
            
            save_connections_json_file(connections_buffer, connections_file)
            return jsonify({'id': id}), 200
        
        elif dbms_name == 'postgresql':
            postgres_conn = PostgreSQLConnection(credentials)
            postgres_conn.create()
            if not postgres_conn.connection:
                raise ValueError("PostgreSQL connection failed")
            postgres_conn.close()
            id = unique_key()
            connections_buffer.update({id : postgres_conn})
            save_connections_json_file(connections_buffer, connections_file)
            return jsonify({'id': id}), 200
        elif dbms_name == 'sqlserver':
            sqlserver_conn = SQLServerConnection(credentials)
            sqlserver_conn.create()
            if not sqlserver_conn.connection:
                raise ValueError("SQLServer connection failed")
            sqlserver_conn.close()
            id = unique_key()
            connections_buffer.update({id : sqlserver_conn})
            save_connections_json_file(connections_buffer, connections_file)
            return jsonify({'id': id}), 200
        else:
            raise ValueError("Invalid DBMS name")  
        return jsonify({'error': "connection failed"}), 200
    except Exception as e:
        print(e)
        return jsonify({'error': str(e)}), 400
    
    

def restore_tables(connection_id):
    
    global tables_buffer
    global connections_buffer
    global use_memory_buffer
    global use_file_buffer
    
    if connection_id not in connections_buffer:
        raise ValueError("Invalid connection id")
    
    if use_memory_buffer and connection_id in tables_buffer:
        log_info("Returning from buffer")
        tables = tables_buffer[connection_id]
        return tables

    if use_file_buffer:
        tables = load_database_json_file(f'{connection_id}.json')
        if tables:
            log_info("Returning from file")
            rel_config = load_relationship_config_from_file(f'{connection_id}.json')
            if rel_config.get("enabled"):
                enabled_cols = [k for k, v in rel_config.get("column_settings", {}).items() if v]
                apply_inferred_relationships(tables, enabled_cols)
            if use_memory_buffer:
                tables_buffer.update({connection_id : tables})
            return tables

    connection = connections_buffer[connection_id]
    connection.create()
    
    tables = None
    
    if isinstance(connection, MySQLConnection):
        tables = mysql_fetch_tables(connection)
        
    if isinstance(connection, PostgreSQLConnection):
        tables = postgres_fetch_tables(connection) 

    if isinstance(connection, SQLServerConnection):
        tables = sqlserver_fetch_tables(connection) 
    
    connection.close()
    
    if use_memory_buffer:
        tables_buffer.update({connection_id : tables})
    if use_file_buffer:
        save_database_json_file(tables, f'{connection_id}.json')
    
    log_info("Returning from connection")
    return tables

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)