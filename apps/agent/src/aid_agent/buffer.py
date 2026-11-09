"""Fila em disco (SQLite) dos Eventos já sanitizados: sobrevive a queda de rede e a reinício.

O `event_id` é a chave. Coletar de novo o mesmo registro não enfileira duas vezes, nem depois de
enviado: os ids enviados ficam em `sent` por 14 dias. Reenviar depois de uma resposta perdida
também não duplica, porque a ingestão deduplica pelo `event_id`. Um lote que a plataforma recusa
por inteiro vai para `rejected`, para não travar a fila.
"""

import json
import sqlite3
from collections.abc import Sequence
from pathlib import Path
from typing import Any

SENT_RETENTION_DAYS = 14


class Buffer:
    def __init__(self, path: Path) -> None:
        self.db = sqlite3.connect(path)
        self.db.execute("pragma journal_mode = wal")
        self.db.executescript(
            """
            create table if not exists pending (event_id text primary key, payload text not null,
              enqueued_at real not null default (unixepoch('subsec')));
            create table if not exists sent (event_id text primary key,
              sent_at real not null default (unixepoch('subsec')));
            create table if not exists rejected (event_id text primary key, payload text not null,
              reason text not null, rejected_at real not null default (unixepoch('subsec')));
            create table if not exists checkpoints (key text primary key, value text not null);
            """
        )
        self.db.commit()

    def enqueue(self, events: Sequence[dict[str, Any]]) -> int:
        before = self.db.total_changes
        self.db.executemany(
            "insert or ignore into pending (event_id, payload)"
            " select ?, ? where not exists (select 1 from sent where event_id = ?)",
            [(event["event_id"], json.dumps(event), event["event_id"]) for event in events],
        )
        self.db.commit()
        return self.db.total_changes - before

    def take(self, limit: int) -> list[dict[str, Any]]:
        rows = self.db.execute(
            "select payload from pending order by enqueued_at, event_id limit ?", (limit,)
        ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def ack(self, event_ids: Sequence[str]) -> None:
        ids = [(event_id,) for event_id in event_ids]
        self.db.executemany("insert or ignore into sent (event_id) values (?)", ids)
        self.db.executemany("delete from pending where event_id = ?", ids)
        self.db.execute(
            "delete from sent where sent_at < unixepoch('subsec') - ?",
            (SENT_RETENTION_DAYS * 86400,),
        )
        self.db.commit()

    def reject(self, events: Sequence[dict[str, Any]], reason: str) -> None:
        self.db.executemany(
            "insert or replace into rejected (event_id, payload, reason) values (?, ?, ?)",
            [(event["event_id"], json.dumps(event), reason) for event in events],
        )
        self.db.executemany(
            "delete from pending where event_id = ?", [(event["event_id"],) for event in events]
        )
        self.db.commit()

    def size(self) -> int:
        return int(self.db.execute("select count(*) from pending").fetchone()[0])

    def rejected(self) -> int:
        return int(self.db.execute("select count(*) from rejected").fetchone()[0])

    def checkpoint(self, key: str) -> str | None:
        row = self.db.execute("select value from checkpoints where key = ?", (key,)).fetchone()
        return None if row is None else str(row[0])

    def save_checkpoint(self, key: str, value: str) -> None:
        self.db.execute(
            "insert into checkpoints (key, value) values (?, ?)"
            " on conflict (key) do update set value = excluded.value",
            (key, value),
        )
        self.db.commit()

    def close(self) -> None:
        self.db.close()
