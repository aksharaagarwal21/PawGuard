/**
 * Base45 decoding (RFC 9285) — a text encoding, not cryptography. Written here because the npm package needs Node's
 * Buffer and accepts invalid input; this version rejects anything outside the alphabet or out of range.
 * Checked against the RFC's own examples in base45.test.ts.
 */
const ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ $%*+-./:";
const VALUE = new Map(Array.from(ALPHABET, (c, i) => [c, i]));

export function base45Decode(input: string): Uint8Array {
  const n = input.length;
  if (n % 3 === 1) throw new Error("invalid base45 length");
  const out = new Uint8Array(Math.floor(n / 3) * 2 + (n % 3 === 2 ? 1 : 0));
  let o = 0;
  for (let i = 0; i < n; i += 3) {
    const a = VALUE.get(input.charAt(i));
    const b = VALUE.get(input.charAt(i + 1));
    if (a === undefined || b === undefined) throw new Error("invalid base45 character");
    if (i + 2 < n) {
      const c = VALUE.get(input.charAt(i + 2));
      if (c === undefined) throw new Error("invalid base45 character");
      const x = a + b * 45 + c * 45 * 45;
      if (x > 0xffff) throw new Error("invalid base45 value");
      out[o++] = x >> 8;
      out[o++] = x & 0xff;
    } else {
      const x = a + b * 45;
      if (x > 0xff) throw new Error("invalid base45 value");
      out[o++] = x;
    }
  }
  return out;
}
