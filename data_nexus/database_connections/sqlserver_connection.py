from sqlalchemy import URL, create_engine
import pymssql
from data_nexus.log_handle.log import *

class SQLServerConnection:
    def __init__(self, db_credentials):
        self.db_credentials = db_credentials
        self.engine = None
        self.connection = None
        self.database = db_credentials.database
        self.schema = db_credentials.schema if db_credentials.schema else 'dbo'
        
    def create(self):
        try:
            port = int(self.db_credentials.port) if self.db_credentials.port else 1433
            url = URL.create(
                "mssql+pymssql",
                username=self.db_credentials.user,
                password=self.db_credentials.password,
                host=self.db_credentials.host,
                port=port,
                database=self.database,
            )
            self.engine = create_engine(
                url,
                pool_pre_ping=True,
                connect_args={
                    "login_timeout": 60,
                    "timeout": 60,
                },
            )
            self.connection = self.engine.raw_connection()
            log_debug("SQLServer connection created successfully.")
        except Exception as e:
            log_error(f"Error creating SQLServer connection: {e}")
            raise e

    def close(self):
        if self.connection:
            try:
                self.connection.close()
                self.connection = None
                log_debug("SQLServer connection closed.")
            except Exception as e:
                log_error(f"Error closing SQLServer connection: {e}")
                raise e
        if self.engine:
            try:
                self.engine.dispose()
                self.engine = None
                log_debug("SQLServer engine disposed.")
            except Exception as e:
                log_error(f"Error disposing SQLServer engine: {e}")
