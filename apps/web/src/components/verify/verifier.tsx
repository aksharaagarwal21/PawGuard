"use client";

import { AlertTriangle, Camera, CheckCircle2, HelpCircle, ImageUp, RefreshCw, ShieldX, WifiOff, XCircle } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button, cn } from "@pawguard/ui";

import { formatDateTime, formatPartialDate } from "@/lib/format";
import { isStale, loadCachedLists, refreshLists, type ListsState } from "@/lib/verify/lists-store";
import { getDetector, prepareOffline, readImage } from "@/lib/verify/scanner";
import { verifyCertificate, type Outcome } from "@/lib/verify/verify";

const today = () => new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD in the verifier's own time zone

type Tone = "ok" | "bad" | "warn" | "neutral";
const TONE: Record<Tone, string> = {
  ok: "border-primary bg-sage",
  bad: "border-urgent bg-urgent-soft",
  warn: "border-ink-2 bg-sand",
  neutral: "border-divider bg-surface",
};

/** Offline certificate verifier: everything below runs in the browser against root-signed, cached lists. */
export function Verifier({ demoSamples }: { demoSamples: boolean }) {
  const t = useTranslations("verify");
  const locale = useLocale();
  const [lists, setLists] = useState<ListsState>({ trust: null, revocations: null, fetchedAt: null });
  const [online, setOnline] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [updateError, setUpdateError] = useState(false);
  const [text, setText] = useState("");
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [photo, setPhoto] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [now, setNow] = useState(0);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  const update = useCallback(async (prev: ListsState) => {
    setUpdating(true);
    setUpdateError(false);
    try {
      setLists(await refreshLists(prev));
    } catch {
      setUpdateError(true);
    } finally {
      setUpdating(false);
      setNow(Date.now());
    }
  }, []);

  useEffect(() => {
    const id = window.setTimeout(() => {
      const cached = loadCachedLists();
      setLists(cached);
      setOnline(navigator.onLine);
      setNow(Date.now());
      if (navigator.onLine) {
        void update(cached);
        void prepareOffline().catch(() => undefined);
      }
    }, 0);
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, [update]);

  const check = useCallback(
    async (qr: string) => {
      const result = await verifyCertificate(qr, lists.trust, lists.revocations, today());
      setOutcome(result);
      setPhoto(null);
      requestAnimationFrame(() => resultRef.current?.focus());
      if (navigator.onLine && (result.status === "genuine" || result.status === "revoked")) {
        try {
          const r = await fetch(`/api/v1/public/credentials/${result.cert.credentialId}/photo`, { cache: "no-store" });
          if (r.ok) setPhoto(((await r.json()) as { photo_url: string | null }).photo_url);
        } catch {
          /* photo is optional */
        }
      }
    },
    [lists],
  );

  // A code handed over in the URL fragment (sample page "Check it in the verifier"); the fragment never reaches the
  // server. It is checked once the lists have finished loading, then removed from the address bar.
  const linked = useRef<string | null>(null);
  useEffect(() => {
    const hash = window.location.hash;
    if (!hash.startsWith("#qr=")) return;
    try {
      linked.current = decodeURIComponent(hash.slice(4));
    } catch {
      linked.current = null;
    }
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }, []);
  useEffect(() => {
    if (!linked.current || now === 0 || updating) return;
    const qr = linked.current;
    linked.current = null;
    const id = window.setTimeout(() => {
      setText(qr);
      void check(qr);
    }, 0);
    return () => window.clearTimeout(id);
  }, [now, updating, check]);

  const stopCamera = useCallback(() => {
    stream.current?.getTracks().forEach((tr) => tr.stop());
    stream.current = null;
    setScanning(false);
  }, []);

  useEffect(() => stopCamera, [stopCamera]);

  async function startCamera() {
    setOutcome(null);
    try {
      // Permission is asked only now, after the person tapped "Scan".
      stream.current = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
    } catch {
      setOutcome({ status: "unreadable" });
      return;
    }
    setScanning(true);
    const detector = await getDetector();
    requestAnimationFrame(async () => {
      if (!video.current || !stream.current) return;
      video.current.srcObject = stream.current;
      await video.current.play().catch(() => undefined);
      const tick = async () => {
        if (!stream.current || !video.current) return;
        try {
          const found = await detector.detect(video.current);
          if (found[0]?.rawValue) {
            stopCamera();
            setText(found[0].rawValue);
            await check(found[0].rawValue);
            return;
          }
        } catch {
          /* keep trying */
        }
        window.setTimeout(() => void tick(), 300);
      };
      void tick();
    });
  }

  async function onFile(file: File | undefined) {
    if (!file) return;
    setOutcome(null);
    try {
      const qr = await readImage(file);
      if (!qr) {
        setOutcome({ status: "unreadable" });
        return;
      }
      setText(qr);
      await check(qr);
    } catch {
      setOutcome({ status: "unreadable" });
    }
  }

  const stale = isStale(lists, now);
  const fmt = (d?: string) => formatPartialDate(d, "day", locale, "—");

  return (
    <div className="space-y-6">
      <section aria-labelledby="lists-h" className="space-y-2 rounded-card border border-divider bg-surface p-4 text-sm">
        <h2 id="lists-h" className="sr-only">
          {t("listsTitle")}
        </h2>
        <p data-testid="lists-freshness">
          {lists.fetchedAt
            ? t("listsUpdated", { time: formatDateTime(new Date(lists.fetchedAt).toISOString(), locale, Intl.DateTimeFormat().resolvedOptions().timeZone) })
            : t("listsNever")}
        </p>
        {!online ? (
          <p className="flex items-center gap-1.5 font-semibold">
            <WifiOff aria-hidden className="size-4" /> {t("offline")}
          </p>
        ) : null}
        {stale ? <p className="font-semibold text-urgent">{t("stale")}</p> : null}
        {updateError && online ? <p className="text-ink-2">{t("updateFailed")}</p> : null}
        {online ? (
          <Button type="button" size="sm" variant="quiet" disabled={updating} onClick={() => void update(lists)}>
            <RefreshCw aria-hidden className={cn("size-4", updating && "motion-safe:animate-spin")} />
            {t("updateNow")}
          </Button>
        ) : null}
      </section>

      <section aria-labelledby="scan-h" className="space-y-3">
        <h2 id="scan-h" className="text-xl">
          {t("scanTitle")}
        </h2>
        <div className="flex flex-wrap gap-2">
          {scanning ? (
            <Button type="button" variant="secondary" onClick={stopCamera}>
              {t("stopCamera")}
            </Button>
          ) : (
            <Button type="button" onClick={() => void startCamera()}>
              <Camera aria-hidden className="size-5" />
              {t("scan")}
            </Button>
          )}
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-control border border-control bg-surface px-4 font-display font-semibold hover:bg-sage">
            <ImageUp aria-hidden className="size-5" />
            {t("upload")}
            <input type="file" accept="image/*" className="sr-only" onChange={(e) => void onFile(e.target.files?.[0])} />
          </label>
        </div>
        {scanning ? (
          <video ref={video} className="aspect-square w-full max-w-sm rounded-card bg-ink object-cover" muted playsInline aria-label={t("cameraView")} />
        ) : null}
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            void check(text);
          }}
        >
          <label htmlFor="qr-text" className="block font-semibold">
            {t("pasteLabel")}
          </label>
          <textarea
            id="qr-text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={3}
            maxLength={2100}
            spellCheck={false}
            className="w-full rounded-control border border-control bg-surface p-2 font-mono text-xs break-all"
            placeholder="PG1:…"
          />
          <Button type="submit" variant="secondary" disabled={!text.trim()}>
            {t("check")}
          </Button>
        </form>
      </section>

      {outcome ? (
        <div ref={resultRef} tabIndex={-1} role="status" aria-live="polite" data-testid="verify-result" className="outline-none">
          <Result outcome={outcome} photo={photo} fmt={fmt} />
        </div>
      ) : null}

      {demoSamples ? (
        <p className="text-sm">
          <a href={`/${locale}/verify/samples`}>{t("samplesLink")}</a>
        </p>
      ) : null}

      <p className="border-t border-divider pt-4 text-sm text-ink-2">{t("footerNote")}</p>
    </div>
  );
}

function Panel({ tone, icon: Icon, title, children, testId }: { tone: Tone; icon: typeof CheckCircle2; title: string; children?: React.ReactNode; testId: string }) {
  return (
    <section className={cn("space-y-2 rounded-card border-l-4 p-4", TONE[tone])} data-result={testId}>
      <h2 className="flex items-center gap-2 text-xl">
        <Icon aria-hidden className={cn("size-6", tone === "ok" ? "text-primary" : tone === "bad" ? "text-urgent" : "text-ink")} />
        {title}
      </h2>
      {children}
    </section>
  );
}

function Result({ outcome, photo, fmt }: { outcome: Outcome; photo: string | null; fmt: (d?: string) => string }) {
  const t = useTranslations("verify");
  switch (outcome.status) {
    case "unreadable":
      return (
        <Panel tone="neutral" icon={HelpCircle} title={t("unreadableTitle")} testId="unreadable">
          <p>{t("unreadableBody")}</p>
        </Panel>
      );
    case "no_lists":
      return (
        <Panel tone="neutral" icon={WifiOff} title={t("noListsTitle")} testId="no_lists">
          <p>{t("noListsBody")}</p>
        </Panel>
      );
    case "altered":
      return (
        <Panel tone="bad" icon={XCircle} title={t("alteredTitle")} testId="altered">
          <p>{t("alteredBody")}</p>
        </Panel>
      );
    case "untrusted":
      return (
        <Panel tone="bad" icon={ShieldX} title={t("untrustedTitle")} testId="untrusted">
          <p>{t(`untrusted.${outcome.reason}`)}</p>
        </Panel>
      );
    case "revoked":
      return (
        <Panel tone="warn" icon={AlertTriangle} title={t("revokedTitle")} testId="revoked">
          <p>{t("revokedBody")}</p>
          <p className="text-sm">{t("revokedDetail", { clinic: outcome.clinicName, given: fmt(outcome.cert.vaccine.givenOn) })}</p>
        </Panel>
      );
    case "genuine": {
      const c = outcome.cert;
      return (
        <div className="space-y-3">
          <Panel tone="ok" icon={CheckCircle2} title={t("genuineTitle")} testId="genuine">
            <p>
              {t("genuineBody", {
                clinic: outcome.clinicName,
                vet: c.vetName,
                issued: new Date(c.issuedAt * 1000).toLocaleDateString(),
                vaccine: c.vaccine.product ?? "—",
                given: fmt(c.vaccine.givenOn),
                due: fmt(c.vaccine.nextDueOn),
              })}
            </p>
            {c.vaccine.lot ? <p className="text-sm">{t("lot", { lot: c.vaccine.lot })}</p> : null}
            <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              <dt className="font-semibold">{t("pet")}</dt>
              <dd>{[c.pet.name, c.pet.species, c.pet.sex, c.pet.description].filter(Boolean).join(" · ")}</dd>
              <dt className="font-semibold">{t("reference")}</dt>
              <dd className="font-mono">{c.pet.reference}</dd>
            </dl>
            {photo ? (
              // eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL
              <img src={photo} alt={t("photoAlt")} className="size-40 rounded-card object-cover" />
            ) : null}
            <p className="font-semibold">{t("matchAnimal")}</p>
            {outcome.demo ? <p className="text-sm font-semibold">{t("demoIssuer")}</p> : null}
          </Panel>
          {outcome.overdue ? (
            <Panel tone="warn" icon={AlertTriangle} title={t("overdueTitle")} testId="overdue">
              <p>{t("overdueBody")}</p>
            </Panel>
          ) : null}
        </div>
      );
    }
  }
}
