"""Fuzzing (ticket #13): o Sanitizer nunca lança exceção e só cresce o que cabe nos marcadores."""

from typing import Any

from aid_security import Sanitizer
from aid_security.sanitizer import MAX_STRING_BYTES, TRUNCATED
from hypothesis import given, settings
from hypothesis import strategies as st

sanitizer = Sanitizer()
LONGEST_MARKER = len("[REMOVIDO:salesforce_session]")

# Texto com pedaços que se parecem com o que os detectores procuram, para exercitar as bordas.
fragments = st.sampled_from(
    [
        "Bearer ",
        "eyJ",
        "password=",
        "Authorization: ",
        "@",
        ".",
        "-",
        "/",
        "(11) ",
        "+55",
        "529.982.247-25",
        "4111 1111 1111 1111",
        "AKIA",
        "AIza",
        "00D",
        "!",
        "10.0.0.1",
        "[REMOVIDO:",
        "]",
    ]
)
texts = st.lists(st.one_of(st.text(max_size=20), fragments), max_size=30).map("".join)
json_values: st.SearchStrategy[Any] = st.recursive(
    st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | texts,
    lambda children: (
        st.lists(children, max_size=4) | st.dictionaries(st.text(max_size=12), children, max_size=4)
    ),
    max_leaves=25,
)


@settings(max_examples=400, deadline=None)
@given(json_values)
def test_nunca_lanca_excecao(value: Any) -> None:
    sanitizer.sanitize(value)


@settings(max_examples=400, deadline=None)
@given(texts)
def test_so_cresce_o_tamanho_dos_marcadores(text: str) -> None:
    result, report = sanitizer.sanitize(text)
    assert isinstance(result, str)
    removed = sum(report.counts.values())
    limit = min(len(text), MAX_STRING_BYTES) + removed * LONGEST_MARKER + len(TRUNCATED)
    assert len(result) <= limit
