"""`scripts/apply-doctor-migrations.py`: quais arquivos do submódulo são do Doctor (ADR-0022)."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


def script() -> ModuleType:
    name = "apply_doctor_migrations"
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "scripts" / "apply-doctor-migrations.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


apply = script()


def folder(tmp_path: Path, *names: str) -> Path:
    created = tmp_path / "migrations"
    created.mkdir()
    for name in names:
        (created / name).write_text("select 1;", encoding="utf-8")
    return created


def test_so_o_nome_com_doctor_logo_depois_da_versao_e_do_doctor(tmp_path: Path) -> None:
    found = apply.doctor_migrations(
        folder(
            tmp_path,
            "20261107100000_doctor_local_ai.sql",
            "20261030122348_doctor_schema.sql",
            # Do jayv-coder e do site: vão pelo `db push`, nunca por este script.
            "20261112100000_coder_schema.sql",
            "20261201000000_site_doctor_textos.sql",
            "20261201000001_doctor_notas.md",
        )
    )
    assert [migration.name for migration in found] == [
        "20261030122348_doctor_schema.sql",
        "20261107100000_doctor_local_ai.sql",
    ]


def test_submodulo_sem_checkout_e_erro_e_nao_nada_pendente(tmp_path: Path) -> None:
    # `vendor/supabase` vazio (clone sem `git submodule update --init`): dizer "nada pendente"
    # deixaria ligar o hook num banco sem as migrações.
    with pytest.raises(apply.MigrationsMissingError, match="git submodule update --init"):
        apply.doctor_migrations(tmp_path / "nao-existe")
    with pytest.raises(apply.MigrationsMissingError):
        apply.doctor_migrations(folder(tmp_path, "20261112100000_coder_schema.sql"))


def test_avisa_das_migracoes_compartilhadas_anteriores_que_o_deploy_nao_aplicou(
    tmp_path: Path,
) -> None:
    created = folder(
        tmp_path,
        "20261027111000_audit.sql",
        "20261112100000_coder_schema.sql",
        "20261113200000_doctor_sso.sql",
        "20261114000000_textos.sql",
    )
    pending = [created / "20261113200000_doctor_sso.sql"]
    # A do dia 12 vem antes da do Doctor e não está no histórico do `db push`; a do dia 14 vem
    # depois e não interessa.
    assert apply.shared_not_deployed(created, pending, {"20261027111000"}) == [
        "20261112100000_coder_schema.sql"
    ]
    assert apply.shared_not_deployed(created, pending, {"20261027111000", "20261112100000"}) == []
    assert apply.shared_not_deployed(created, [], set()) == []
