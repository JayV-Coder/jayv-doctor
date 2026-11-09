"""`aid-agent register --token …` e `aid-agent run`. O laço é só de saída: pede a config (long
poll), coleta o autorizado, enfileira em disco e envia; sem rede, a fila espera e o envio volta
quando a rede volta, sem duplicar."""

import argparse
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from aid_agent import __version__
from aid_agent.buffer import Buffer
from aid_agent.client import Platform, PlatformError, register
from aid_agent.collectors import (
    DirectoryCollector,
    RfcConnection,
    RfcFunctionCollector,
    RfcTableCollector,
)
from aid_agent.identity import (
    Credentials,
    load_credentials,
    load_or_create_key,
    public_key,
    save_credentials,
)
from aid_agent.updater import RESTART, apply

log = logging.getLogger("aid_agent")
BATCH = 500


def state_dir() -> Path:
    path = Path(os.environ.get("AID_AGENT_STATE", "/var/lib/aid-agent"))
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    return path


def rfc_connection() -> RfcConnection:
    """Conexão RFC com o usuário técnico (variáveis `AID_SAP_*` só na máquina do agente). A
    biblioteca (PyRFC ou compatível, com o NW RFC SDK) vem da imagem do cliente."""
    try:
        from pyrfc import Connection  # type: ignore[import-not-found]
    except ImportError as exc:
        raise RuntimeError(
            "coleta RFC sem a biblioteca RFC instalada (docs/operations/agente.md)"
        ) from exc

    names = {
        "ashost": "AID_SAP_ASHOST",
        "sysnr": "AID_SAP_SYSNR",
        "client": "AID_SAP_CLIENT",
        "user": "AID_SAP_USER",
        "passwd": "AID_SAP_PASSWORD",
    }
    connection: RfcConnection = Connection(**{key: os.environ[env] for key, env in names.items()})
    return connection


def flush(platform: Platform, buffer: Buffer) -> int:
    """Envia a fila em lotes de 500. Falha de rede para aqui e a fila espera a próxima rodada."""
    sent = 0
    while events := buffer.take(BATCH):
        platform.send(events)
        buffer.ack([event["event_id"] for event in events])
        sent += len(events)
    return sent


def cycle(
    platform: Platform,
    buffer: Buffer,
    config: dict[str, Any],
    integration_id: str,
    connect: Callable[[], RfcConnection] = rfc_connection,
) -> tuple[int, int]:
    """Uma rodada: coleta o autorizado e tenta enviar a fila. Devolve (coletados, enviados)."""
    collected = 0
    for spec in config.get("collections", []):
        try:
            if spec["type"] == "directory":
                collected += DirectoryCollector(spec, integration_id, buffer).collect()
            elif spec["type"] == "rfc_table":
                collected += RfcTableCollector(spec, integration_id, buffer, connect).collect()
            elif spec["type"] == "rfc_function":
                collected += RfcFunctionCollector(spec, integration_id, buffer, connect).collect()
        except Exception:
            # Uma coleta com problema (RFC fora, pasta sem permissão) não segura as outras.
            log.exception("coleta %s falhou", spec.get("type"))
    try:
        sent = flush(platform, buffer)
    except httpx.HTTPError:
        log.warning("plataforma inacessível: %d Eventos esperam na fila", buffer.size())
        sent = 0
    return collected, sent


def fetch(url: str) -> bytes:
    return httpx.get(url, timeout=120, follow_redirects=False).raise_for_status().content


def run(once: bool = False) -> int:
    state = state_dir()
    credentials = load_credentials(state)
    if credentials is None:
        log.error("agente sem registro: rode `aid-agent register --token …`")
        return 2
    platform = Platform(credentials, load_or_create_key(state), state)
    buffer = Buffer(state / "buffer.sqlite3")
    # A última config fica na fila em disco: reiniciado sem rede, o agente continua coletando.
    saved = json.loads(buffer.checkpoint("config") or "null") or {"config_version": 0}
    while True:
        try:
            platform.heartbeat(__version__)
            found = platform.config(int(saved["config_version"]))
            if found is not None:
                saved = found
                buffer.save_checkpoint("config", json.dumps(found))
                if updated(found.get("update")):
                    return RESTART
        except PlatformError:
            log.error("a plataforma recusou o agente: confira se ele foi revogado")
            return 3
        except httpx.HTTPError:
            log.warning("sem rede com a plataforma; a coleta continua para a fila em disco")
        config = dict(saved.get("config") or {})
        if saved.get("integration_id"):
            cycle(platform, buffer, config, str(saved["integration_id"]))
        if once:
            return 0
        time.sleep(int(config.get("interval_seconds", 300)))


def updated(manifest: dict[str, Any] | None) -> bool:
    """Aplica a versão anunciada quando o agente roda como zipapp (`AID_AGENT_BINARY`). Na imagem
    Docker a atualização é a imagem nova, e o anúncio só aparece no log."""
    if not manifest or manifest.get("version") == __version__:
        return False
    binary = os.environ.get("AID_AGENT_BINARY")
    if not binary:
        log.info("versão %s disponível; atualize a imagem do agente", manifest.get("version"))
        return False
    if not apply(manifest, Path(binary), fetch):
        log.error(
            "atualização %s recusada: assinatura ou sha256 não conferem", manifest.get("version")
        )
        return False
    log.info("versão %s aplicada; reiniciando", manifest["version"])
    return True


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
    )
    parser = argparse.ArgumentParser(prog="aid-agent")
    commands = parser.add_subparsers(dest="command", required=True)
    registering = commands.add_parser("register", help="registra o agente com o token de uso único")
    registering.add_argument("--token", required=True)
    registering.add_argument("--api", default=os.environ.get("AID_API_URL", ""))
    running = commands.add_parser("run", help="coleta e envia (só conexões de saída)")
    running.add_argument("--once", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "register":
        if not args.api.startswith("https://") and not args.api.startswith("http://127.0.0.1"):
            log.error("AID_API_URL precisa ser https://")
            return 2
        state = state_dir()
        key = load_or_create_key(state)
        found = register(args.api, args.token, public_key(key), __version__)
        save_credentials(
            state,
            Credentials(args.api, found["agent_id"], found["secret"]),
            found.get("certificate"),
        )
        log.info("agente %s registrado", found["agent_id"])
        return 0
    return run(once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
