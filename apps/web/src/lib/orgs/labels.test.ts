import { describe, expect, it } from "vitest";
import { isManager } from "./labels";

describe("isManager", () => {
  it("só Owner e Admin administram a Organização", () => {
    expect(isManager("owner")).toBe(true);
    expect(isManager("admin")).toBe(true);
    expect(isManager("analyst")).toBe(false);
    expect(isManager("viewer")).toBe(false);
    expect(isManager(null)).toBe(false);
  });
});
