/**
 * PawGuard signed certificates (ADR 0010): `PG1:` + Base45(zlib(COSE_Sign1)) with EdDSA/Ed25519.
 * Signature checking uses @noble/curves (audited); CBOR uses cborg; inflation uses the browser's DecompressionStream.
 * This file only assembles the RFC 9052 Sig_structure — no cryptographic primitive is implemented here.
 */
import { ed25519 } from "@noble/curves/ed25519.js";
import { decode, encode } from "cborg";

import { base45Decode } from "./base45";

export const PREFIX = "PG1:";
export const MAX_QR_TEXT = 2000;
export const MAX_INFLATED = 4096;
const ALG_EDDSA = -8;

export class Unreadable extends Error {}

export type CborMap = Map<number, unknown>;

export type Sign1 = {
  kid: Uint8Array;
  protectedBytes: Uint8Array;
  body: Uint8Array;
  signature: Uint8Array;
  payload: CborMap;
};

// cborg 6 tag decoders receive a `decode` function and must call it to read the tagged content (COSE_Sign1 = tag 18).
type TagDecoder = (decode: () => unknown) => unknown;
const TAGS: TagDecoder[] = [];
TAGS[18] = (decode) => ({ cose: decode() });

function cbor(bytes: Uint8Array): unknown {
  return decode(bytes, { useMaps: true, tags: TAGS, rejectDuplicateMapKeys: true });
}

/** zlib inflate with a hard output cap (guards against compression bombs). */
export async function inflate(data: Uint8Array, max = MAX_INFLATED): Promise<Uint8Array> {
  const stream = new Blob([data as BlobPart]).stream().pipeThrough(new DecompressionStream("deflate"));
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    total += value.length;
    if (total > max) {
      await reader.cancel();
      throw new Unreadable("too large");
    }
    chunks.push(value);
  }
  const out = new Uint8Array(total);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

export function parseSign1(bytes: Uint8Array): Sign1 {
  let obj: unknown;
  try {
    obj = cbor(bytes);
  } catch {
    throw new Unreadable("not CBOR");
  }
  const arr = (obj as { cose?: unknown })?.cose;
  if (!Array.isArray(arr) || arr.length !== 4) throw new Unreadable("not COSE_Sign1");
  const [protectedBytes, , body, signature] = arr as unknown[];
  if (!(protectedBytes instanceof Uint8Array && body instanceof Uint8Array && signature instanceof Uint8Array)) {
    throw new Unreadable("bad COSE fields");
  }
  let header: unknown;
  let payload: unknown;
  try {
    header = cbor(protectedBytes);
    payload = cbor(body);
  } catch {
    throw new Unreadable("bad header or payload");
  }
  if (!(header instanceof Map) || header.get(1) !== ALG_EDDSA || !(header.get(4) instanceof Uint8Array)) {
    throw new Unreadable("unsupported algorithm");
  }
  if (!(payload instanceof Map)) throw new Unreadable("bad payload");
  return { kid: header.get(4) as Uint8Array, protectedBytes, body, signature, payload: payload as CborMap };
}

export function verifySign1(msg: Sign1, publicKey: Uint8Array): boolean {
  const sigStructure = encode(["Signature1", msg.protectedBytes, new Uint8Array(0), msg.body]);
  try {
    return msg.signature.length === 64 && ed25519.verify(msg.signature, sigStructure, publicKey);
  } catch {
    return false;
  }
}

/** QR text → COSE_Sign1 (throws Unreadable for anything that is not a well-formed PawGuard certificate). */
export async function decodeQr(text: string): Promise<Sign1> {
  const t = text.trim();
  if (t.length > MAX_QR_TEXT || !t.startsWith(PREFIX)) throw new Unreadable("not a PawGuard certificate");
  let compressed: Uint8Array;
  try {
    compressed = base45Decode(t.slice(PREFIX.length));
  } catch {
    throw new Unreadable("bad encoding");
  }
  let raw: Uint8Array;
  try {
    raw = await inflate(compressed);
  } catch (e) {
    throw e instanceof Unreadable ? e : new Unreadable("bad compression");
  }
  return parseSign1(raw);
}

export function hex(b: Uint8Array): string {
  return Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
}

export function b64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}
