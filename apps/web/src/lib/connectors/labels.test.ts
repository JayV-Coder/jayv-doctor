import { describe, expect, it } from "vitest";
import {
  checkpointText,
  connectorState,
  intervalLabel,
  lastSyncText,
  nextRunText,
  pauseText,
  syncDuration,
  syncStatus,
} from "./labels";

const NOW = new Date("2026-11-03T14:32:00Z");

describe("connectorState", () => {
  it("usa os rótulos do mockup", () => {
    expect(connectorState({ status: "active", last_sync_at: "2026-11-03T14:30:00Z" })).toEqual({
      label: "Saudável",
      tone: "success",
    });
    expect(connectorState({ status: "failing", last_sync_at: null })).toEqual({
      label: "Com falhas",
      tone: "warning",
    });
    expect(connectorState({ status: "paused", last_sync_at: null }).label).toBe("Pausado");
    expect(connectorState({ status: "disabled", last_sync_at: null }).tone).toBe("danger");
  });

  it("ativo que ainda não sincronizou não se diz saudável", () => {
    expect(connectorState({ status: "active", last_sync_at: null })).toEqual({
      label: "Aguardando",
      tone: "info",
    });
  });
});

describe("lastSyncText", () => {
  it("diz há quanto tempo e quantos eventos, em pt-BR", () => {
    expect(
      lastSyncText({ last_sync_at: "2026-11-03T14:30:00Z", last_sync_records: 1204 }, NOW),
    ).toBe("há 2 min · 1.204 eventos");
    expect(lastSyncText({ last_sync_at: "2026-11-03T11:30:00Z", last_sync_records: 1 }, NOW)).toBe(
      "há 3 h · 1 evento",
    );
    expect(lastSyncText({ last_sync_at: "2026-11-03T14:31:50Z", last_sync_records: 0 }, NOW)).toBe(
      "agora · 0 eventos",
    );
  });

  it("antes da primeira Sincronização", () => {
    expect(lastSyncText({ last_sync_at: null, last_sync_records: null }, NOW)).toBe(
      "ainda não sincronizou",
    );
  });
});

describe("checkpointText", () => {
  it("mostra o instante do GCP em UTC", () => {
    expect(checkpointText({ timestamp: "2026-11-03T14:30:00.123Z", insert_id: "x" })).toBe(
      "2026-11-03 14:30:00Z",
    );
  });

  it("sem Checkpoint, ou num formato sem instante", () => {
    expect(checkpointText(null)).toBe("ainda não há");
    expect(checkpointText({ page: 3 })).toBe("gravado");
  });
});

describe("nextRunText", () => {
  it("diz quando será a próxima tentativa", () => {
    expect(nextRunText("2026-11-03T14:36:00Z", NOW)).toBe("em 4 min");
    expect(nextRunText("2026-11-03T14:31:00Z", NOW)).toBe("agora");
  });
});

describe("pauseText", () => {
  it("explica o motivo e o que fazer", () => {
    expect(pauseText("auth")).toContain("credencial nova");
    expect(pauseText("manual")).toBe("Pausado por um Owner ou Admin.");
    expect(pauseText(null)).toBe("Pausado por um Owner ou Admin.");
  });
});

describe("Sincronização", () => {
  it("duração legível, e nada enquanto roda", () => {
    expect(syncDuration("2026-11-03T14:30:00Z", "2026-11-03T14:30:12Z")).toBe("12 s");
    expect(syncDuration("2026-11-03T14:30:00Z", "2026-11-03T14:32:05Z")).toBe("2 min 5 s");
    expect(syncDuration("2026-11-03T14:30:00Z", null)).toBe("em andamento");
  });

  it("status com o mesmo vocabulário", () => {
    expect(syncStatus("succeeded")).toEqual({ label: "Concluída", tone: "success" });
    expect(syncStatus("failed")).toEqual({ label: "Falhou", tone: "danger" });
    expect(syncStatus("running")).toEqual({ label: "Rodando", tone: "info" });
  });
});

describe("intervalLabel", () => {
  it("em minutos ou horas", () => {
    expect(intervalLabel(60)).toBe("a cada 1 min");
    expect(intervalLabel(300)).toBe("a cada 5 min");
    expect(intervalLabel(3600)).toBe("a cada 1 h");
  });
});
