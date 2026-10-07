/**
 * Cached trust and revocation lists for offline verification. Both are verified against the root key built into the
 * app every time they are loaded; a downloaded list never replaces a newer cached one (no rollback).
 * Stored in localStorage (public data only — clinic public keys and cancelled certificate ids).
 */
import { ListRejected, parseRevocations, parseTrustList, type RevocationList, type SignedListDoc, type TrustList } from "./verify";

const KEY = "pawguard.verify.lists.v1";

export type ListsState = {
  trust: TrustList | null;
  revocations: RevocationList | null;
  fetchedAt: number | null; // ms since epoch, when both lists were last downloaded and verified
};

type Stored = { trust: SignedListDoc; revocations: SignedListDoc; fetchedAt: number };

const EMPTY: ListsState = { trust: null, revocations: null, fetchedAt: null };

export function loadCachedLists(): ListsState {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const s = JSON.parse(raw) as Stored;
    return { trust: parseTrustList(s.trust), revocations: parseRevocations(s.revocations), fetchedAt: s.fetchedAt };
  } catch {
    return EMPTY; // missing, unreadable, or failed the root signature check: treat as not downloaded
  }
}

async function getDoc(path: string): Promise<SignedListDoc> {
  const r = await fetch(path, { cache: "no-store", headers: { accept: "application/json" } });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return (await r.json()) as SignedListDoc;
}

/** Download both lists, verify them, and keep them unless the cached copy is newer. */
export async function refreshLists(prev: ListsState): Promise<ListsState> {
  const [trustDoc, revDoc] = await Promise.all([getDoc("/api/v1/public/trust-list"), getDoc("/api/v1/public/revocations")]);
  const trust = parseTrustList(trustDoc); // throws ListRejected on a bad root signature
  const revocations = parseRevocations(revDoc);
  if ((prev.trust && trust.version < prev.trust.version) || (prev.revocations && revocations.version < prev.revocations.version)) {
    throw new ListRejected("older than the cached lists");
  }
  const fetchedAt = Date.now();
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ trust: trustDoc, revocations: revDoc, fetchedAt } satisfies Stored));
  } catch {
    /* storage unavailable (private window): lists still work for this visit */
  }
  return { trust, revocations, fetchedAt };
}

export function isStale(state: ListsState, now: number): boolean {
  if (!state.fetchedAt || !state.trust) return false;
  return now - state.fetchedAt > state.trust.staleAfterDays * 86_400_000;
}
