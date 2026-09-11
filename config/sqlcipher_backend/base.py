"""Django SQLite backend wired to the sqlcipher3 DB-API driver."""

from __future__ import annotations

import datetime
import decimal
from pathlib import Path
from collections.abc import Mapping
from itertools import tee

from django.db.backends.sqlite3._functions import register as register_functions
from django.db.backends.sqlite3.base import (
    DatabaseWrapper as SQLiteDatabaseWrapper,
    adapt_date,
    adapt_datetime,
    decoder,
    FORMAT_QMARK_REGEX,
)
from django.db.backends.sqlite3.features import DatabaseFeatures as SQLiteDatabaseFeatures
from django.db.backends.sqlite3.operations import DatabaseOperations as SQLiteDatabaseOperations
from django.utils.asyncio import async_unsafe
from django.utils.dateparse import parse_date, parse_datetime, parse_time
from sqlcipher3 import dbapi2 as Database

from database_security import get_database_key, sqlcipher_key_pragma


Database.register_converter("bool", b"1".__eq__)
Database.register_converter("date", decoder(parse_date))
Database.register_converter("time", decoder(parse_time))
Database.register_converter("datetime", decoder(parse_datetime))
Database.register_converter("timestamp", decoder(parse_datetime))
Database.register_adapter(decimal.Decimal, str)
Database.register_adapter(datetime.date, adapt_date)
Database.register_adapter(datetime.datetime, adapt_datetime)


class SQLCipherCursorWrapper(Database.Cursor):
    def execute(self, query, params=None):
        if params is None:
            return super().execute(query)
        param_names = list(params) if isinstance(params, Mapping) else None
        return super().execute(self.convert_query(query, param_names=param_names), params)

    def executemany(self, query, param_list):
        peekable, param_list = tee(iter(param_list))
        first = next(peekable, None)
        param_names = list(first) if isinstance(first, Mapping) else None
        return super().executemany(self.convert_query(query, param_names=param_names), param_list)

    def convert_query(self, query, *, param_names=None):
        if param_names is None:
            return FORMAT_QMARK_REGEX.sub("?", query).replace("%%", "%")
        return query % {name: f":{name}" for name in param_names}


class DatabaseFeatures(SQLiteDatabaseFeatures):
    @property
    def max_query_params(self):
        # sqlcipher3 is DB-API compatible but doesn't expose sqlite3.getlimit().
        # 999 is SQLite's portable conservative limit and keeps Django batching safe.
        return 999


class DatabaseOperations(SQLiteDatabaseOperations):
    """SQLite operations compatible with sqlcipher3's DB-API connection.

    Django 6 asks the native sqlite3 connection for ``getlimit()`` while it
    formats a query for debug logging.  sqlcipher3 does not expose that
    CPython-only method, so use the same conservative batching limit as the
    backend features above.
    """

    def _quote_params_for_last_executed_query(self, params):
        connection = self.connection.connection
        batch_size = min(self.connection.features.max_query_params, 999)

        if len(params) > batch_size:
            results = ()
            for index in range(0, len(params), batch_size):
                chunk = params[index : index + batch_size]
                results += self._quote_params_for_last_executed_query(chunk)
            return results

        sql = "SELECT " + ", ".join(["QUOTE(?)"] * len(params))
        cursor = connection.cursor()
        try:
            return cursor.execute(sql, params).fetchone()
        finally:
            cursor.close()


class DatabaseWrapper(SQLiteDatabaseWrapper):
    Database = Database
    features_class = DatabaseFeatures
    ops_class = DatabaseOperations

    def create_cursor(self, name=None):
        return self.connection.cursor(factory=SQLCipherCursorWrapper)

    @async_unsafe
    def get_new_connection(self, conn_params):
        connection = Database.connect(**conn_params)
        try:
            connection.execute(sqlcipher_key_pragma(get_database_key(create=False)))
            connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
            register_functions(connection)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA legacy_alter_table = OFF")
            for init_command in self.init_commands:
                if init_command := init_command.strip():
                    connection.execute(init_command)
            try:
                Path(conn_params["database"]).chmod(0o600)
            except (KeyError, OSError, TypeError):
                pass
            return connection
        except Exception:
            connection.close()
            raise
