"""Alembic ortamı.

* Uygulama içinden (``otogaleri.db.init_db``) çağrıldığında hazır bağlantı
  ``config.attributes["connection"]`` ile gelir.
* Komut satırından (``alembic upgrade head``) çağrıldığında engine
  ``otogaleri.config`` ayarlarından kurulur.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from otogaleri.db import create_db_engine, metadata

config = context.config
target_metadata = metadata


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


_connection = config.attributes.get("connection")
if _connection is not None:
    _run(_connection)
else:
    if config.config_file_name is not None:
        fileConfig(config.config_file_name, disable_existing_loggers=False)
    with create_db_engine().begin() as conn:
        _run(conn)
