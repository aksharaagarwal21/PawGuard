// @vitest-environment node
import { describe, expect, it } from "vitest";

import vectors from "./__fixtures__/vectors.json";
import { base45Decode } from "./base45";
import { b64ToBytes, decodeQr, inflate, Unreadable } from "./cose";
import { ListRejected, parseRevocations, parseTrustList, verifyCertificate } from "./verify";

/** Vectors are produced by the server's own signing code (scripts/make_verify_vectors.py) with TEST-ONLY keys. */
const ROOT = [b64ToBytes(vectors.root_public_b64)];
const trust = parseTrustList(vectors.trust as never, ROOT);
const revocations = parseRevocations(vectors.revocations as never, ROOT);
const check = (qr: string) => verifyCertificate(qr, trust, revocations, vectors.today);

describe("base45 (RFC 9285 examples)", () => {
  const text = (s: string) => new TextDecoder().decode(base45Decode(s));
  it("decodes the RFC test vectors", () => {
    expect(text("BB8")).toBe("AB");
    expect(text("%69 VD92EX0")).toBe("Hello!!");
    expect(text("UJCLQE7W581")).toBe("base-45");
    expect(text("QED8WEX0")).toBe("ietf!");
  });
  it("rejects invalid input", () => {
    expect(() => base45Decode("GGW")).toThrow(); // value > 0xFFFF (RFC example of an invalid string)
    expect(() => base45Decode("ab")).toThrow(); // lower case is not in the alphabet
    expect(() => base45Decode("A")).toThrow(); // impossible length
  });
});

describe("signed lists", () => {
  it("accepts lists signed by the built-in root key", () => {
    expect(trust.keys.size).toBe(3);
    expect(revocations.ids.size).toBe(1);
  });
  it("rejects a trust list whose content was changed (bad root signature)", () => {
    expect(() => parseTrustList(vectors.trust_forged as never, ROOT)).toThrow(ListRejected);
  });
  it("rejects a trust list signed by another root", () => {
    expect(() => parseTrustList(vectors.trust_other_root as never, ROOT)).toThrow(ListRejected);
  });
  it("rejects a revocation list passed as a trust list", () => {
    expect(() => parseTrustList(vectors.revocations as never, ROOT)).toThrow(ListRejected);
  });
});

describe("certificates", () => {
  it("genuine", async () => {
    const r = await check(vectors.certs.genuine);
    expect(r.status).toBe("genuine");
    if (r.status === "genuine") {
      expect(r.cert.pet.name).toBe("Bruno");
      expect(r.cert.vaccine.givenOn).toBe("2026-06-09");
      expect(r.clinicName).toContain("Test Clinic");
      expect(r.overdue).toBe(false);
    }
  });
  it("a changed date is detected as altered", async () => {
    expect((await check(vectors.certs.altered)).status).toBe("altered");
  });
  it("changing any single byte of the signed payload fails", async () => {
    for (const qr of vectors.byte_flips) {
      expect(["altered", "unreadable", "untrusted"]).toContain((await check(qr)).status);
      expect((await check(qr)).status).not.toBe("genuine");
    }
    expect(vectors.byte_flips.length).toBeGreaterThan(30);
  });
  it("a key that is not in the trust list is untrusted", async () => {
    const r = await check(vectors.certs.unknown_key);
    expect(r).toMatchObject({ status: "untrusted", reason: "unknown_clinic" });
  });
  it("a trusted key id with someone else's signature is altered", async () => {
    expect((await check(vectors.certs.kid_swapped)).status).toBe("altered");
  });
  it("a cancelled certificate shows revoked", async () => {
    expect((await check(vectors.certs.revoked_credential)).status).toBe("revoked");
  });
  it("a revoked key is untrusted", async () => {
    expect(await check(vectors.certs.revoked_key)).toMatchObject({ status: "untrusted", reason: "key_revoked" });
  });
  it("a retired key still verifies what it signed before retirement, not after", async () => {
    expect((await check(vectors.certs.retired_before)).status).toBe("genuine");
    expect(await check(vectors.certs.retired_after)).toMatchObject({ status: "untrusted", reason: "outside_validity" });
  });
  it("genuine but overdue", async () => {
    expect(await check(vectors.certs.overdue)).toMatchObject({ status: "genuine", overdue: true });
  });
  it("malformed, oversized and non-PawGuard codes are unreadable", async () => {
    for (const qr of vectors.unreadable) expect((await check(qr)).status).toBe("unreadable");
  });
  it("without lists it says it cannot check yet", async () => {
    expect((await verifyCertificate(vectors.certs.genuine, null, null, vectors.today)).status).toBe("no_lists");
  });
});

describe("limits", () => {
  it("inflation stops at the size cap (compression bomb)", async () => {
    const big = new Uint8Array(100_000);
    const deflated = new Uint8Array(await new Response(new Blob([big]).stream().pipeThrough(new CompressionStream("deflate"))).arrayBuffer());
    await expect(inflate(deflated, 4096)).rejects.toBeInstanceOf(Unreadable);
  });
  it("decodeQr rejects text over 2000 characters", async () => {
    await expect(decodeQr("PG1:" + "0".repeat(3000))).rejects.toBeInstanceOf(Unreadable);
  });
});
