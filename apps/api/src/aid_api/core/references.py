"""Referência de negócio digitada numa busca: vira HMAC com a chave da Organização, como na
ingestão, e o número nunca chega ao banco nem aos logs."""

import os
from uuid import UUID

from aid_security.references import derive_tenant_key, reference_hmac

from aid_api.core.auth import Claims


def reference_of(claims: Claims, term: str | None) -> str | None:
    """Sem `HMAC_MASTER_KEY` configurada, a busca fica só pelos ids técnicos."""
    master = os.environ.get("HMAC_MASTER_KEY")
    if not term or not master or claims.tenant_id is None:
        return None
    return reference_hmac(derive_tenant_key(master.encode(), UUID(claims.tenant_id)), term.strip())
