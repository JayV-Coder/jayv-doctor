import { describe, expect, it } from "vitest";
import { activeTab, pageTitle, TABS } from "./nav";

describe("TABS", () => {
  it("segue a barra do mockup: Início, Incidentes, Execuções, Conectores e Mais", () => {
    expect(TABS.map(({ label }) => label)).toEqual([
      "Início",
      "Incidentes",
      "Execuções",
      "Conectores",
      "Mais",
    ]);
  });
});

describe("activeTab", () => {
  it("destaca a aba da própria rota", () => {
    expect(activeTab("/")).toBe("/");
    expect(activeTab("/incidentes")).toBe("/incidentes");
    expect(activeTab("/conectores")).toBe("/conectores");
  });

  it("mantém a aba nas telas de detalhe", () => {
    expect(activeTab("/incidentes/inc-0142")).toBe("/incidentes");
    expect(activeTab("/execucoes/abc/eventos")).toBe("/execucoes");
  });

  it("põe a Importação manual sob Conectores, como no mockup", () => {
    expect(activeTab("/importar")).toBe("/conectores");
    expect(pageTitle("/importar")).toBe("Importar logs");
    expect(pageTitle("/incidentes/abc/relatorio")).toBe("Relatório");
    expect(pageTitle("/incidentes/abc")).toBe("Incidentes");
    expect(activeTab("/eventos/abc")).toBe("/execucoes");
    expect(pageTitle("/eventos/abc")).toBe("Evento original");
    expect(pageTitle("/execucoes/abc")).toBe("Execuções");
    expect(pageTitle("/conectores/novo")).toBe("Novo conector");
    expect(activeTab("/conectores/novo")).toBe("/conectores");
    expect(pageTitle("/conectores/abc")).toBe("Conectores");
  });

  it("põe em Mais as telas que se abrem de lá", () => {
    expect(activeTab("/membros")).toBe("/mais");
    expect(activeTab("/integracoes")).toBe("/mais");
  });

  it("não confunde prefixo de palavra com subrota", () => {
    expect(activeTab("/incidentesx")).toBe("/mais");
  });
});

describe("pageTitle", () => {
  it("usa o rótulo da aba ou o nome da tela", () => {
    expect(pageTitle("/")).toBe("Início");
    expect(pageTitle("/execucoes")).toBe("Execuções");
    expect(pageTitle("/membros")).toBe("Membros");
    expect(pageTitle("/integracoes")).toBe("Integrações");
  });

  it("cai no rótulo da aba nas subrotas sem título próprio", () => {
    expect(pageTitle("/incidentes/inc-0142")).toBe("Incidentes");
  });
});
