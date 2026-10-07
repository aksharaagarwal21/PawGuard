import { b64ToBytes } from "./cose";

/**
 * PawGuard platform root PUBLIC key(s) — built into the app so the trust list can be verified offline (ADR 0011).
 * Generated with `pawguard-admin keys init`; the private key lives only in the server's secrets folder.
 * Root rotation: add the new key here, ship, switch signing, then remove the old key in a later build.
 */
export const ROOT_PUBLIC_KEYS_B64 = ["pa9Iv86uCAZm7BOiizW7G/Y28zaXhlqoedj4nChNZBs="];

export const ROOT_KEYS: Uint8Array[] = ROOT_PUBLIC_KEYS_B64.map(b64ToBytes);
