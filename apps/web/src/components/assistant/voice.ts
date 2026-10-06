"use client";

/**
 * Minimal Web Speech API helpers (speech recognition + speech synthesis). Recognition is a Chrome/Edge/Safari
 * feature behind a prefix; the DOM type library doesn't describe it, so the small surface used here is typed locally.
 */
export type VoiceLang = "en" | "hi" | "ta";
export const BCP47: Record<VoiceLang, string> = { en: "en-IN", hi: "hi-IN", ta: "ta-IN" };

interface RecognitionResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>;
}
interface RecognitionErrorEvent {
  error: string;
}
export interface Recognition {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  continuous: boolean;
  onresult: ((e: RecognitionResultEvent) => void) | null;
  onerror: ((e: RecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionCtor = new () => Recognition;

export function recognitionSupported(): boolean {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition);
}

export function createRecognition(lang: VoiceLang): Recognition | null {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) return null;
  const r = new Ctor();
  r.lang = BCP47[lang];
  r.interimResults = true;
  r.maxAlternatives = 1;
  r.continuous = false;
  return r;
}

/** Voices load asynchronously in Chrome; wait briefly for them. */
export async function voicesFor(lang: VoiceLang): Promise<SpeechSynthesisVoice[]> {
  if (!("speechSynthesis" in window)) return [];
  const pick = () => window.speechSynthesis.getVoices().filter((v) => v.lang.toLowerCase().startsWith(lang));
  let found = pick();
  if (found.length === 0) {
    await new Promise<void>((resolve) => {
      const done = () => resolve();
      window.speechSynthesis.addEventListener("voiceschanged", done, { once: true });
      setTimeout(done, 1500);
    });
    found = pick();
  }
  // Prefer an Indian-English / local voice when several exist.
  return found.sort((a, b) => Number(b.lang === BCP47[lang]) - Number(a.lang === BCP47[lang]));
}

export function speak(text: string, voice: SpeechSynthesisVoice, onEnd: () => void): void {
  window.speechSynthesis.cancel();
  const u = new SpeechSynthesisUtterance(text);
  u.voice = voice;
  u.lang = voice.lang;
  u.rate = 0.95;
  u.onend = onEnd;
  u.onerror = onEnd;
  window.speechSynthesis.speak(u);
}

export function stopSpeaking(): void {
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
}
