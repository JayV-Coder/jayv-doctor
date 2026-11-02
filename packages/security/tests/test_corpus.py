"""Metas do ticket #13 no corpus: precisão de 100% nos segredos e recall ≥ 99% em PII."""

import json
from collections import Counter
from pathlib import Path

from aid_security import Sanitizer

CORPUS = Path(__file__).parent / "corpus" / "corpus.jsonl"
SECRETS = {
    "private_key",
    "bearer",
    "jwt",
    "aws_key",
    "gcp_key",
    "gcp_token",
    "salesforce_session",
    "password",
    "authorization",
    "cookie",
    "token",
}

cases = [json.loads(line) for line in CORPUS.read_text().splitlines()]
sanitizer = Sanitizer()


def found(text: str) -> Counter[str]:
    return sanitizer.sanitize(text)[1].counts


def test_corpus_tem_ao_menos_200_casos() -> None:
    assert len(cases) >= 200
    assert sum(1 for case in cases if not case["expect"]) >= 100


def test_precisao_de_100_por_cento_nos_segredos() -> None:
    false_positives = [
        (case["id"], kind)
        for case in cases
        for kind in found(case["text"])
        if kind in SECRETS and kind not in case["expect"]
    ]
    assert false_positives == []


def test_todo_segredo_do_corpus_e_removido() -> None:
    missed = [
        case["id"]
        for case in cases
        for kind, count in case["expect"].items()
        if kind in SECRETS and found(case["text"])[kind] < count
    ]
    assert missed == []


def test_recall_de_pii_de_ao_menos_99_por_cento() -> None:
    expected = hits = 0
    missed = []
    for case in cases:
        counts = found(case["text"])
        for kind, count in case["expect"].items():
            if kind in SECRETS:
                continue
            expected += count
            got = min(counts[kind], count)
            hits += got
            if got < count:
                missed.append(case["id"])
    assert hits / expected >= 0.99, missed


def test_negativos_saem_intactos() -> None:
    changed = [
        case["id"]
        for case in cases
        if not case["expect"] and sanitizer.sanitize(case["text"])[0] != case["text"]
    ]
    assert changed == []
