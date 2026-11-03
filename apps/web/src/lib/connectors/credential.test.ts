import { describe, expect, it } from "vitest";
import { serviceAccountEmail } from "./credential";

describe("serviceAccountEmail", () => {
  it("lê o e-mail da Service Account da chave JSON", () => {
    const key = JSON.stringify({
      type: "service_account",
      client_email: "doctor-reader@acme.iam.gserviceaccount.com",
      private_key: "-----BEGIN PRIVATE KEY-----\n...",
    });
    expect(serviceAccountEmail(key)).toBe("doctor-reader@acme.iam.gserviceaccount.com");
  });

  it("recusa o que não é chave de Service Account", () => {
    expect(serviceAccountEmail("nao-e-json")).toBeNull();
    expect(serviceAccountEmail(JSON.stringify({ type: "authorized_user" }))).toBeNull();
    expect(serviceAccountEmail(JSON.stringify({ client_email: "x@y" }))).toBeNull();
    expect(serviceAccountEmail("[]")).toBeNull();
  });
});
