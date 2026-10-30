import { describe, expect, it } from "vitest";

import { CONTRACTS_PACKAGE } from "./index";

describe("@aid/contracts", () => {
  it("exporta o nome do pacote", () => {
    expect(CONTRACTS_PACKAGE).toBe("@aid/contracts");
  });
});
