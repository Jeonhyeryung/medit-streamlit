import pymysql
import pymysqlpool
import os
from datetime import datetime
import string
import random
from config import DB_CONFIG as config


class MysqlConnectorPool:
    __instance = None
    db_manager = None

    @classmethod
    def __getInstance(cls):
        return cls.__instance

    @classmethod
    def instance(cls, *args, **kwargs):
        cls.__instance = cls(*args, **kwargs)
        cls.instance = cls.__getInstance()
        return cls.__instance

    def __init__(self, max_connections=10):
        self.config = config
        self.pool = None
        self.max_connections = max_connections
        self.db_config = self.config

    def connect(self):
        self.pool = pymysqlpool.ConnectionPool(
            host=self.db_config['host'],
            user=self.db_config['user'],
            password=self.db_config['password'],
            database=self.db_config['database'],
            autocommit=True
        )

        return self.pool

    def disconnect(self):
        if self.pool:
            self.pool.close()
            self.pool = None

    def read(self, query):
        connection = self.connect().get_connection()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                connection.commit()
                return rows

        except Exception as e:
            print(f"Error executing query: {str(e)}")
            return None

        finally:
            connection.close()

    def write(self, query):
        connection = self.connect().get_connection()
        try:
            with connection.cursor(pymysql.cursors.DictCursor) as cursor:
                cursor.execute(query)

        except Exception as e:
            print(e)
            # return None
            return False

        finally:
            connection.close()

    def generate_no(self):
        now = datetime.now()
        formattedData = now.strftime("%Y%m%d%H%M%S")
        secure_code = ''.join(random.SystemRandom().choice(string.ascii_uppercase + string.digits) for _ in range(6))
        number = formattedData + secure_code
        return number