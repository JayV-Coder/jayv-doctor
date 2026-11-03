from aid_diagnosis_engine.incidents import incident_severity, primary
from aid_diagnosis_engine.rules.base import RuleMatch


def found(code: str, hint: str) -> RuleMatch:
    return RuleMatch(code, "2026.10.1", code, hint, ("e",), {})  # type: ignore[arg-type]


def test_producao_sobe_um_nivel_e_volume_vira_critico() -> None:
    assert incident_severity("medium", "hml", 1) == "medium"
    assert incident_severity("medium", "prd", 1) == "high"
    assert incident_severity("high", "prd", 1) == "critical"
    assert incident_severity("critical", "prd", 1) == "critical"
    assert incident_severity("low", "dev", 20) == "critical"
    assert incident_severity("low", "dev", 19) == "low"


def test_match_principal_e_o_mais_severo_e_depois_o_primeiro_do_catalogo() -> None:
    matches = [found("INT-002", "medium"), found("INT-003", "high"), found("INT-005", "high")]
    chosen = primary(matches)
    assert chosen is not None
    assert chosen.rule_code == "INT-003"
    assert primary([]) is None


def test_titulo_em_portugues_com_a_integracao() -> None:
    from aid_diagnosis_engine.incidents import incident_title

    assert incident_title("TIMEOUT", "Pedidos SF → SAP") == "Timeout · Pedidos SF → SAP"
    assert len(incident_title("TIMEOUT", "x" * 300)) == 200
