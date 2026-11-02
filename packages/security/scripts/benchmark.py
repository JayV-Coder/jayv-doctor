"""Benchmark do ticket #13 (meta: 10 mil registros por segundo por núcleo).

`uv run python packages/security/scripts/benchmark.py` mede um registro típico de log de
integração: uns dez campos, um segredo e um dado pessoal.
"""

import time

from aid_security import Sanitizer

RECORD = {
    "timestamp": "2026-11-02T14:05:00.123Z",
    "severity": "error",
    "operation": "BAPI_SALESORDER_CREATEFROMDAT2",
    "integration": "Pedidos Salesforce → SAP",
    "message": "Timeout ao criar pedido 4500012345 para cliente ana.souza@acme.com.br",
    "http": {"status": 504, "method": "POST", "path": "/sap/bc/srt/rfc/sap/zsales"},
    "headers": {"Authorization": "Bearer 9f8e7d6c5b4a39281706f5e4d3c2b1a0", "x-request-id": "a1b2"},
    "duration_ms": 30000,
    "retry": 3,
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
}


def main(seconds: float = 3.0) -> None:
    sanitizer = Sanitizer()
    count = 0
    start = time.perf_counter()
    while time.perf_counter() - start < seconds:
        sanitizer.sanitize(RECORD)
        count += 1
    rate = count / (time.perf_counter() - start)
    print(f"{rate:,.0f} registros/s em um núcleo")


if __name__ == "__main__":
    main()
