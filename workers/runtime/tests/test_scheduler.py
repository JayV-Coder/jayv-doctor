"""O agendador fora do GCP (Dokploy) tem os mesmos jobs e horários do Terraform."""

import re
from datetime import UTC, datetime
from pathlib import Path

from aid_worker.scheduler import JOBS, due

STACK = Path(__file__).resolve().parents[3] / "infrastructure/terraform/stack/main.tf"
# Dependem do GCP (Cloud Monitoring e GCS): fora do agendador local.
GCP_ONLY = {"/platform/metrics", "/backup/storage"}


def test_mesmos_jobs_do_cloud_scheduler() -> None:
    text = STACK.read_text(encoding="utf-8")
    found = set()
    for block in re.findall(r'resource "google_cloud_scheduler_job" "\w+" \{(.*?)\n\}', text, re.S):
        schedule = re.search(r'schedule\s*=\s*"([^"]+)"', block)
        target = re.search(r'module\.workers\["(\w+)"\]\.uri\}(/[^"]*)"', block)
        if schedule and target and target.group(2) not in GCP_ONLY:
            found.add((schedule.group(1), target.group(1), target.group(2)))
    assert found == set(JOBS)


def test_cron_dos_jobs() -> None:
    at = datetime(2026, 11, 11, 6, 15, tzinfo=UTC)
    assert due("* * * * *", at)
    assert due("*/5 * * * *", at)
    assert not due("*/10 * * * *", at)
    assert due("15 6 * * *", at)
    assert not due("0 6 * * *", at)
