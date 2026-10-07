/**
 * Offline certificate verification: signed trust list → clinic key → certificate signature → key validity at the
 * issue time → signed revocation list. Pure functions; caching and fetching live in lists-store.ts.
 */
import { ROOT_KEYS } from "./root-key";
import { b64ToBytes, decodeQr, hex, parseSign1, Unreadable, verifySign1, type CborMap } from "./cose";

export type SignedListDoc = { format: "PG-TL1" | "PG-RL1"; version: number; cose: string };

export type TrustKey = {
  kid: string;
  clinicId: string;
  clinicName: string;
  publicKey: Uint8Array;
  validFrom: number;
  validTo: number | null;
  status: "active" | "retired" | "revoked";
  isDemo: boolean;
};

export type TrustList = { version: number; issuedAt: number; keys: Map<string, TrustKey>; staleAfterDays: number };
export type RevocationList = { version: number; issuedAt: number; ids: Set<string> };

export class ListRejected extends Error {}

function rootVerified(doc: SignedListDoc, format: SignedListDoc["format"], rootKeys: Uint8Array[]): CborMap {
  if (!doc || doc.format !== format || typeof doc.cose !== "string" || doc.cose.length > 200_000) {
    throw new ListRejected("wrong list");
  }
  let msg;
  try {
    msg = parseSign1(b64ToBytes(doc.cose));
  } catch {
    throw new ListRejected("unreadable list");
  }
  if (!rootKeys.some((k) => verifySign1(msg, k))) throw new ListRejected("bad root signature");
  return msg.payload;
}

const uuidOf = (b: unknown) => {
  const h = b instanceof Uint8Array ? hex(b) : "";
  return h.length === 32 ? `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}` : "";
};

export function parseTrustList(doc: SignedListDoc, rootKeys: Uint8Array[] = ROOT_KEYS): TrustList {
  const p = rootVerified(doc, "PG-TL1", rootKeys);
  const keys = new Map<string, TrustKey>();
  for (const e of (p.get(3) as CborMap[]) ?? []) {
    const kid = e.get(1);
    const pk = e.get(4);
    if (!(kid instanceof Uint8Array) || !(pk instanceof Uint8Array) || pk.length !== 32) continue;
    keys.set(hex(kid), {
      kid: hex(kid),
      clinicId: uuidOf(e.get(2)),
      clinicName: String(e.get(3) ?? ""),
      publicKey: pk,
      validFrom: Number(e.get(5) ?? 0),
      validTo: e.get(6) === undefined ? null : Number(e.get(6)),
      status: (e.get(7) as TrustKey["status"]) ?? "revoked",
      isDemo: Boolean(e.get(8)),
    });
  }
  return { version: Number(p.get(1)), issuedAt: Number(p.get(2)), keys, staleAfterDays: Number(p.get(4) ?? 7) };
}

export function parseRevocations(doc: SignedListDoc, rootKeys: Uint8Array[] = ROOT_KEYS): RevocationList {
  const p = rootVerified(doc, "PG-RL1", rootKeys);
  const ids = new Set<string>(((p.get(3) as unknown[]) ?? []).map(uuidOf).filter(Boolean));
  return { version: Number(p.get(1)), issuedAt: Number(p.get(2)), ids };
}

export type Certificate = {
  credentialId: string;
  pet: { reference: string; name?: string; species?: string; sex?: string; description?: string };
  vaccine: { product?: string; lot?: string; givenOn: string; nextDueOn?: string; nextDueSource?: string };
  clinic: { id: string; name: string };
  vetName: string;
  issuedAt: number;
};

export type Outcome =
  | { status: "unreadable" }
  | { status: "no_lists" }
  | { status: "untrusted"; reason: "unknown_clinic" | "key_revoked" | "outside_validity"; cert?: Certificate }
  | { status: "altered"; cert?: Certificate }
  | { status: "revoked"; cert: Certificate; clinicName: string }
  | { status: "genuine"; cert: Certificate; clinicName: string; overdue: boolean; demo: boolean };

const SKEW = 300; // seconds of clock tolerance at the key's validity boundaries

function readCert(p: CborMap): Certificate | undefined {
  try {
    const pet = p.get(3) as CborMap;
    const vac = p.get(4) as CborMap;
    const clinic = p.get(5) as CborMap;
    const given = vac.get(3);
    if (Number(p.get(1)) !== 1 || typeof given !== "string") return undefined;
    return {
      credentialId: uuidOf(p.get(2)),
      pet: {
        reference: String(pet.get(1) ?? ""),
        name: pet.get(2) as string | undefined,
        species: pet.get(3) as string | undefined,
        sex: pet.get(4) as string | undefined,
        description: pet.get(5) as string | undefined,
      },
      vaccine: {
        product: vac.get(1) as string | undefined,
        lot: vac.get(2) as string | undefined,
        givenOn: given,
        nextDueOn: vac.get(4) as string | undefined,
        nextDueSource: vac.get(5) as string | undefined,
      },
      clinic: { id: uuidOf(clinic.get(1)), name: String(clinic.get(2) ?? "") },
      vetName: String(p.get(6) ?? ""),
      issuedAt: Number(p.get(7)),
    };
  } catch {
    return undefined;
  }
}

/** `today` is the verifier's local date (YYYY-MM-DD) for the overdue check. */
export async function verifyCertificate(
  qrText: string,
  trust: TrustList | null,
  revocations: RevocationList | null,
  today: string,
): Promise<Outcome> {
  let msg;
  try {
    msg = await decodeQr(qrText);
  } catch (e) {
    if (e instanceof Unreadable) return { status: "unreadable" };
    return { status: "unreadable" };
  }
  if (!trust || !revocations) return { status: "no_lists" };
  const cert = readCert(msg.payload);
  const key = trust.keys.get(hex(msg.kid));
  if (!key) return { status: "untrusted", reason: "unknown_clinic" };
  if (key.status === "revoked") return { status: "untrusted", reason: "key_revoked", cert };
  if (!verifySign1(msg, key.publicKey) || !cert) return { status: "altered" };
  if (cert.issuedAt < key.validFrom - SKEW || (key.validTo !== null && cert.issuedAt > key.validTo + SKEW)) {
    return { status: "untrusted", reason: "outside_validity", cert };
  }
  if (revocations.ids.has(cert.credentialId)) return { status: "revoked", cert, clinicName: key.clinicName };
  const overdue = Boolean(cert.vaccine.nextDueOn && cert.vaccine.nextDueOn < today);
  return { status: "genuine", cert, clinicName: key.clinicName, overdue, demo: key.isDemo };
}
