from aid_knowledge.chunking import chunk_text, estimate_tokens
from aid_knowledge.search import rrf


def doc(paragraphs: int, words: int = 60) -> str:
    body = []
    for n in range(paragraphs):
        if n % 5 == 0:
            body.append(f"# Seção {n // 5}")
        body.append(" ".join(f"palavra{n}_{w}" for w in range(words)))
    return "\n\n".join(body)


def test_fragmentos_entre_500_e_800_tokens_com_sobreposicao() -> None:
    chunks = chunk_text(doc(60))
    assert len(chunks) > 3
    for chunk in chunks[:-1]:
        assert 500 <= chunk.tokens <= 800
    assert chunks[-1].tokens <= 800
    # Sobreposição: o fim de um aparece no começo do seguinte.
    tail = chunks[0].content.split()[-10:]
    assert " ".join(tail) in chunks[1].content
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_titulo_da_secao_vai_no_metadado() -> None:
    chunks = chunk_text(doc(30))
    assert chunks[0].heading == "Seção 0"
    assert any(chunk.heading == "Seção 3" for chunk in chunks)


def test_documento_curto_vira_um_fragmento_so() -> None:
    (only,) = chunk_text("# Runbook\n\nReinicie o job VL10.")
    assert only.content.startswith("# Runbook")
    assert only.tokens == estimate_tokens(only.content)


def test_paragrafo_gigante_e_quebrado_em_palavras() -> None:
    chunks = chunk_text(" ".join(f"w{n}" for n in range(5000)))
    assert all(chunk.tokens <= 800 for chunk in chunks)


def test_rrf_junta_listas_pela_posicao() -> None:
    fused = rrf([["a", "b", "c"], ["c", "a", "d"]])
    assert fused[0] == "a"
    assert set(fused) == {"a", "b", "c", "d"}
    assert fused.index("c") < fused.index("b")
