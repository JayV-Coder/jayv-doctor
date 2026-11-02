from uuid import UUID

import pytest
from aid_security import Sanitizer, derive_tenant_key, reference_hmac

MASTER = b"chave-mestre-de-teste-com-32-bytes!!"
TENANT_A = UUID("00000000-0000-4000-8000-00000000ac01")
TENANT_B = UUID("00000000-0000-4000-8000-00000000be01")


def test_mesmo_pedido_gera_hmac_diferente_por_tenant_e_estavel_no_mesmo() -> None:
    key_a, key_b = derive_tenant_key(MASTER, TENANT_A), derive_tenant_key(MASTER, TENANT_B)
    first = reference_hmac(key_a, "4500012345")
    assert first == reference_hmac(derive_tenant_key(MASTER, TENANT_A), "4500012345")
    assert first != reference_hmac(key_b, "4500012345")
    assert first.startswith("hmac:")
    assert len(first) == len("hmac:") + 16


def test_busca_normaliza_espacos_nas_pontas() -> None:
    key = derive_tenant_key(MASTER, TENANT_A)
    assert reference_hmac(key, " 4500012345 ") == reference_hmac(key, "4500012345")


def test_hkdf_segue_o_vetor_do_rfc_5869() -> None:
    from aid_security.references import hkdf_sha256

    okm = hkdf_sha256(
        ikm=bytes.fromhex("0b" * 22),
        salt=bytes.fromhex("000102030405060708090a0b0c"),
        info=bytes.fromhex("f0f1f2f3f4f5f6f7f8f9"),
        length=42,
    )
    assert okm.hex() == (
        "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865"
    )


def test_campos_de_referencia_viram_hmac_antes_da_deteccao() -> None:
    key = derive_tenant_key(MASTER, TENANT_A)
    sanitizer = Sanitizer(reference_fields=("order_id", "customer_document"), reference_key=key)
    result, report = sanitizer.sanitize(
        {"order_id": "4500012345", "customer_document": "529.982.247-25", "status": "erro"}
    )
    assert result == {
        "order_id": reference_hmac(key, "4500012345"),
        "customer_document": reference_hmac(key, "529.982.247-25"),
        "status": "erro",
    }
    assert dict(report.counts) == {"referencia": 2}


def test_campos_de_referencia_exigem_chave() -> None:
    with pytest.raises(ValueError, match="chave"):
        Sanitizer(reference_fields=("order_id",))
