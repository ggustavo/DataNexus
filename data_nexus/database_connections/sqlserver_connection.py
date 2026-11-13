import pymssql
from data_nexus.log_handle.log import *

class SQLServerConnection:
    def __init__(self, db_credentials):
        self.db_credentials = db_credentials
        self.connection = None
        self.database = db_credentials.database
        self.schema = db_credentials.schema if db_credentials.schema else 'dbo'
        
    def create(self):
        try:
            port = int(self.db_credentials.port) if self.db_credentials.port else 1433
            self.connection = pymssql.connect(
                server=self.db_credentials.host,
                port=port,
                user=self.db_credentials.user,
                password=self.db_credentials.password,
                database=self.database,
                login_timeout=60,
                timeout=60
            )
            log_debug("SQLServer connection created successfully.")
        except Exception as e:
            log_error(f"Error creating SQLServer connection: {e}")
            raise e

    def close(self):
        if self.connection:
            try:
                self.connection.close()
                log_debug("SQLServer connection closed.")
                self.connection = None
            except Exception as e:
                log_error(f"Error closing SQLServer connection: {e}")
                raise e
