"use client";

import type { Schemas } from "@pawguard/api-client";
import { useTranslations } from "next-intl";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button, Card, Dialog, Notice, StatusChip } from "@pawguard/ui";

import type { SubjectChoice } from "@/components/prevention/subject-picker";
import { Uploader } from "@/components/prevention/uploader";
import { Link, useRouter } from "@/i18n/navigation";
import { browserApi, newKey, parseApiError } from "@/lib/api-browser";
import { todayIso } from "@/lib/format";

type Search = Schemas["IdentitySearchOut"];
type Candidate = Schemas["IdentityCandidateOut"];

const POLL_MS = 1500;
const POLL_LIMIT = 40;

/**
 * Photo lookup: the person chooses the animal in their photo, asks for possible matches and decides. Nothing is
 * linked until they confirm; "same animal" then records this photo as a sighting of the chosen animal.
 */
export function PhotoLookup({ mode, canRegister }: { mode: "assisted" | "research_preview"; canRegister: boolean }) {
  const t = useTranslations("identity");
  const tc = useTranslations("common");
  const router = useRouter();
  const [media, setMedia] = useState<string[]>([]);
  const [subjects, setSubjects] = useState<SubjectChoice[]>([]);
  const [search, setSearch] = useState<Search | null>(null);
  const [queryUrl, setQueryUrl] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<Candidate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const polls = useRef(0);
  const op = useRef(newKey());
  const onMedia = useCallback((ids: string[]) => setMedia(ids), []);
  const onSubjects = useCallback((c: SubjectChoice[]) => setSubjects(c), []);
  const mediaId = media[0];
  const subject = subjects.find((s) => s.mediaId === mediaId);

  useEffect(() => {
    if (!search || search.state !== "pending") return;
    if (polls.current >= POLL_LIMIT) {
      setError(t("tookTooLong"));
      return;
    }
    const timer = setTimeout(async () => {
      polls.current += 1;
      const { data } = await browserApi.GET("/api/v1/identity/searches/{search_id}", {
        params: { path: { search_id: search.id } },
      });
      if (data) setSearch(data);
    }, POLL_MS);
    return () => clearTimeout(timer);
  }, [search, t]);

  async function lookFor() {
    if (!mediaId) return;
    setError(null);
    setBusy(true);
    polls.current = 0;
    const [{ data, error: apiError }, link] = await Promise.all([
      browserApi.POST("/api/v1/identity/searches", { body: { media_id: mediaId, box: subject?.box ?? null } }),
      browserApi.GET("/api/v1/media/{media_id}/url", { params: { path: { media_id: mediaId }, query: { variant: "display" } } }),
    ]);
    setBusy(false);
    if (link.data) setQueryUrl(link.data.url);
    if (data) setSearch(data);
    else setError(parseApiError(apiError).message || tc("tryAgainLater"));
  }

  async function decide(decision: "same_animal" | "new_animal" | "not_sure", animalId?: string) {
    if (!search) return;
    setBusy(true);
    setError(null);
    const res = await browserApi.POST("/api/v1/identity/searches/{search_id}/decision", {
      params: { path: { search_id: search.id } },
      body: { decision, animal_id: animalId ?? null },
    });
    if (res.error) {
      setBusy(false);
      setError(parseApiError(res.error).message || tc("tryAgainLater"));
      return;
    }
    if (decision === "same_animal" && animalId && mediaId) {
      const obs = await browserApi.POST("/api/v1/observations", {
        headers: { "Idempotency-Key": op.current },
        body: {
          animal_id: animalId,
          observed_on: todayIso(),
          time_precision: "day",
          media_ids: [mediaId],
          subjects: subject ? [{ media_id: mediaId, source: subject.source, box: subject.box, dog_count: subject.dogCount }] : [],
          quality_override_reason: subject?.overrideReason.trim() || null,
          client_operation_id: op.current,
        },
      });
      setBusy(false);
      if (obs.error) {
        setError(parseApiError(obs.error).message || tc("tryAgainLater"));
        return;
      }
      router.push(`/app/animals/${animalId}?tab=sightings`);
      router.refresh();
      return;
    }
    setBusy(false);
    if (decision === "new_animal") router.push("/app/animals/new");
    else setSearch(res.data);
  }

  const done = search && search.state !== "pending";
  return (
    <div className="space-y-4">
      {mode === "research_preview" ? (
        <Notice tone="pending" title={t("previewTitle")}>
          <p>{t("previewBody")}</p>
        </Notice>
      ) : null}
      <Card className="space-y-3">
        <h2 className="text-base">{t("step1")}</h2>
        <Uploader purpose="animal_photo" onChange={onMedia} onSubjects={onSubjects} subjectPurpose="lookup" idPrefix="lookup-photo" />
        {mediaId && !search ? (
          <Button onClick={lookFor} loading={busy} disabled={!subject}>
            {t("lookFor")}
          </Button>
        ) : null}
        {mediaId && !subject ? <p className="text-sm text-ink-2">{t("chooseSubjectFirst")}</p> : null}
      </Card>
      {search?.state === "pending" ? (
        <Card aria-live="polite">
          <p>{t("searching")}</p>
        </Card>
      ) : null}
      {done ? (
        <section aria-labelledby="lookup-results" className="space-y-3">
          <h2 id="lookup-results" className="text-lg">
            {t("resultsTitle")}
          </h2>
          <ResultNotice search={search} />
          {search.candidates.length ? (
            <ul className="space-y-3">
              {search.candidates.map((c) => (
                <li key={c.animal.id}>
                  <Card className="space-y-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-display font-semibold">
                        {t("possibleMatch", { rank: c.rank })} · <span className="font-mono">{c.animal.reference_code}</span>
                      </p>
                      {search.decided_animal_id === c.animal.id ? <StatusChip kind="verified">{t("chosen")}</StatusChip> : null}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                      <figure className="space-y-1">
                        {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL */}
                        {queryUrl ? <img src={queryUrl} alt={t("yourPhoto")} className="aspect-square w-full rounded-control object-cover" /> : null}
                        <figcaption className="text-sm text-ink-2">{t("yourPhoto")}</figcaption>
                      </figure>
                      {c.photos.map((p, i) =>
                        p.url ? (
                          <figure key={p.media_id} className="space-y-1">
                            {/* eslint-disable-next-line @next/next/no-img-element -- short-lived signed URL */}
                            <img src={p.url} alt={t("candidatePhoto", { ref: c.animal.reference_code, n: i + 1 })} className="aspect-square w-full rounded-control object-cover" />
                            <figcaption className="text-sm text-ink-2">{t("onRecord", { n: i + 1 })}</figcaption>
                          </figure>
                        ) : null,
                      )}
                    </div>
                    <dl className="grid gap-1 text-sm sm:grid-cols-2">
                      <div><dt className="inline font-semibold">{t("nickname")}: </dt><dd className="inline">{c.animal.nickname ?? "—"}</dd></div>
                      <div><dt className="inline font-semibold">{t("area")}: </dt><dd className="inline">{c.animal.home_area_name ?? "—"}</dd></div>
                      <div><dt className="inline font-semibold">{t("coat")}: </dt><dd className="inline">{c.animal.coat_description ?? "—"}</dd></div>
                      <div><dt className="inline font-semibold">{t("marks")}: </dt><dd className="inline">{c.animal.identifying_marks ?? "—"}</dd></div>
                    </dl>
                    <div className="flex flex-wrap gap-2">
                      <Button onClick={() => setConfirm(c)} disabled={busy}>
                        {t("sameAnimal")}
                      </Button>
                      <Button asChild variant="secondary">
                        <Link href={`/app/animals/${c.animal.id}`}>{t("openProfile")}</Link>
                      </Button>
                    </div>
                  </Card>
                </li>
              ))}
            </ul>
          ) : null}
          <Card className="flex flex-wrap gap-2">
            {search.state === "stale_index" || search.state === "failed" ? (
              <Button variant="secondary" onClick={lookFor} disabled={busy}>
                {t("searchAgain")}
              </Button>
            ) : null}
            {canRegister ? (
              <Button variant="secondary" onClick={() => decide("new_animal")} disabled={busy}>
                {t("noneNew")}
              </Button>
            ) : null}
            <Button variant="secondary" onClick={() => decide("not_sure")} disabled={busy}>
              {t("notSure")}
            </Button>
            <Button asChild variant="quiet">
              <Link href="/app/animals">{t("searchManually")}</Link>
            </Button>
          </Card>
          {search.decision === "not_sure" ? <p role="status">{t("notSureSaved")}</p> : null}
        </section>
      ) : null}
      {error ? (
        <p role="alert" className="font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      <Dialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={t("confirmTitle", { ref: confirm?.animal.reference_code ?? "" })}
        description={t("confirmBody")}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button onClick={() => confirm && decide("same_animal", confirm.animal.id)} loading={busy}>
              {t("confirmAction")}
            </Button>
          </>
        }
      />
    </div>
  );
}

function ResultNotice({ search }: { search: Search }) {
  const t = useTranslations("identity");
  switch (search.state) {
    case "completed":
      return <Notice tone="info" title={t("completedTitle")}><p>{t("completedBody")}</p></Notice>;
    case "no_candidate":
      return (
        <Notice tone="info" title={t("noCandidateTitle")}>
          <p>{t("noCandidateBody", { n: search.gallery_animals ?? 0 })}</p>
        </Notice>
      );
    case "stale_index":
      return <Notice tone="pending" title={t("staleTitle")}><p>{t("staleBody")}</p></Notice>;
    case "insufficient_quality":
      return <Notice tone="pending" title={t("qualityTitle")}><p>{t("qualityBody")}</p></Notice>;
    default:
      return <Notice tone="urgent" title={t("failedTitle")}><p>{t("failedBody")}</p></Notice>;
  }
}
