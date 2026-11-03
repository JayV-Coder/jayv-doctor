import { describe, expect, it } from "vitest";
import { canManage, isManager } from "./labels";

describe("isManager", () => {
  it("só Owner e Admin administram a Organização", () => {
    expect(isManager("owner")).toBe(true);
    expect(isManager("admin")).toBe(true);
    expect(isManager("analyst")).toBe(false);
    expect(isManager("viewer")).toBe(false);
    expect(isManager(null)).toBe(false);
  });
});

describe("canManage", () => {
  it("exige Owner ou Admin com MFA", () => {
    expect(canManage({ active_role: "admin", aal: "aal2" })).toBe(true);
    expect(canManage({ active_role: "admin", aal: "aal1" })).toBe(false);
    expect(canManage({ active_role: "analyst", aal: "aal2" })).toBe(false);
    expect(canManage(null)).toBe(false);
  });
});
