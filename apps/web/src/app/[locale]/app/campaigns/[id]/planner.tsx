"use client";

import type { Schemas } from "@pawguard/api-client";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Button, Card, Dialog, Field, Notice, Select, StatusChip, TextInput, Textarea } from "@pawguard/ui";

import { Link, useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

type Campaign = Schemas["CampaignOut"];
type Area = Schemas["CampaignAreaOut"];
type Team = Schemas["TeamOut"];
type Plan = Schemas["PlanOut"];
type Stop = { area_id: string; name: string; travel_minutes: number; arrive: string; start: string; finish: string; animals: number; doses: number };
type Route = { team_id: string; name: string; shift: string; stops: Stop[]; travel_minutes: number; doses_used: number; doses_available: number; ends_at: string };
type Totals = { areas_total: number; areas_planned: number; animals_total: number; animals_planned: number; travel_minutes: number; high_priority_unplanned: number };
type Result = { routes: Route[]; unassigned: { area_id: string; name: string; animals: number; priority: number; reasons: string[] }[]; totals: Totals; baseline: { totals: Totals }; notes: string[]; solver: string };

const PLAN_CHIP = { solving: "submitted", ready: "submitted", failed: "rejected", approved: "verified", published: "verified", superseded: "neutral" } as const;

export function Planner(props: { campaign: Campaign; teams: Team[]; plans: Plan[]; selected: Plan | null; canPublish: boolean; defaultDate: string }) {
  const t = useTranslations("campaigns");
  return (
    <div className="space-y-6">
      <section aria-labelledby="inputs" className="space-y-2">
        <h2 id="inputs" className="text-lg">{t("inputsTitle")}</h2>
        <p className="text-sm text-ink-2">{t("inputsIntro")}</p>
        <div className="space-y-2">
          {props.campaign.areas.map((a) => (
            <AreaRow key={a.area_id} campaignId={props.campaign.id} area={a} />
          ))}
        </div>
      </section>
      <PlanForm campaign={props.campaign} teams={props.teams} defaultDate={props.defaultDate} latest={props.plans[0] ?? null} />
      {props.selected ? <PlanView key={props.selected.id} plan={props.selected} campaign={props.campaign} canPublish={props.canPublish} /> : null}
      {props.plans.length > 1 ? (
        <section aria-labelledby="versions" className="space-y-2">
          <h2 id="versions" className="text-lg">{t("versions")}</h2>
          <ul className="space-y-1">
            {props.plans.map((p) => (
              <li key={p.id} className="flex items-center gap-2">
                <Link href={`/app/campaigns/${props.campaign.id}?plan=${p.id}`}>{t("versionLabel", { v: p.version, date: p.plan_date })}</Link>
                <StatusChip kind={PLAN_CHIP[p.state as keyof typeof PLAN_CHIP] ?? "neutral"}>{t(`planState.${p.state}` as "planState.ready")}</StatusChip>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}

function AreaRow({ campaignId, area }: { campaignId: string; area: Area }) {
  const t = useTranslations("campaigns");
  const router = useRouter();
  const [est, setEst] = useState(area.est_animals?.toString() ?? "");
  const [minutes, setMinutes] = useState(area.service_minutes_per_animal.toString());
  const [from, setFrom] = useState(area.access_start ?? "");
  const [to, setTo] = useState(area.access_end ?? "");
  const [accessible, setAccessible] = useState(area.accessible);
  const [priority, setPriority] = useState(area.priority.toString());
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const id = area.area_id.slice(0, 8);

  async function save() {
    setBusy(true);
    setMsg(null);
    const { error } = await browserApi.PUT("/api/v1/campaigns/{campaign_id}/areas/{area_id}", {
      params: { path: { campaign_id: campaignId, area_id: area.area_id } },
      body: {
        est_animals: est === "" ? null : Number(est),
        service_minutes_per_animal: Number(minutes) || 4,
        access_start: from || null,
        access_end: to || null,
        accessible,
        access_note: area.access_note,
        priority: Number(priority),
        row_version: area.row_version,
      },
    });
    setBusy(false);
    if (error) setMsg(parseApiError(error).message);
    else {
      setMsg(t("saved"));
      router.refresh();
    }
  }

  const suggestion = area.suggested_animals != null ? t("suggested", { n: area.suggested_animals, source: t(`source.${area.suggested_source}` as "source.survey") }) : t("noSuggestion");
  return (
    <Card className="space-y-2">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-display font-semibold">{area.name}</p>
        {!area.has_location ? <StatusChip kind="rejected">{t("noLocation")}</StatusChip> : null}
      </div>
      {area.access_note ? <p className="text-sm text-ink-2">{area.access_note}</p> : null}
      <div className="grid gap-3 sm:grid-cols-6">
        <Field id={`est-${id}`} label={t("estimate")} hint={area.est_animals == null ? suggestion : t(`source.${area.est_source}` as "source.manual")}>
          {(aria) => <TextInput {...aria} inputMode="numeric" value={est} placeholder={area.suggested_animals?.toString() ?? ""} onChange={(e) => setEst(e.target.value.replace(/\D/g, ""))} />}
        </Field>
        <Field id={`min-${id}`} label={t("minutesPerAnimal")}>
          {(aria) => <TextInput {...aria} inputMode="decimal" value={minutes} onChange={(e) => setMinutes(e.target.value)} />}
        </Field>
        <Field id={`from-${id}`} label={t("accessFrom")}>
          {(aria) => <TextInput {...aria} type="time" value={from} onChange={(e) => setFrom(e.target.value)} />}
        </Field>
        <Field id={`to-${id}`} label={t("accessTo")}>
          {(aria) => <TextInput {...aria} type="time" value={to} onChange={(e) => setTo(e.target.value)} />}
        </Field>
        <Field id={`prio-${id}`} label={t("priority")}>
          {(aria) => (
            <Select {...aria} value={priority} onChange={(e) => setPriority(e.target.value)}>
              <option value="1">{t("prio.1")}</option>
              <option value="2">{t("prio.2")}</option>
              <option value="3">{t("prio.3")}</option>
            </Select>
          )}
        </Field>
        <div className="flex flex-col justify-end gap-2">
          <label className="inline-flex min-h-11 items-center gap-2">
            <input type="checkbox" className="size-5 accent-primary" checked={accessible} onChange={(e) => setAccessible(e.target.checked)} />
            {t("accessible")}
          </label>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <Button size="sm" variant="secondary" onClick={save} loading={busy}>
          {t("saveArea")}
        </Button>
        {msg ? <span role="status" className="text-sm">{msg}</span> : null}
      </div>
    </Card>
  );
}

/** Starts from the latest version's choices (pins, exclusions, team settings) so decisions carry into re-plans. */
function initialChoices(latest: Plan | null): Record<string, string> {
  const o = (latest?.inputs as { overrides?: { pinned?: Record<string, string>; excluded?: string[] } } | undefined)?.overrides;
  const out: Record<string, string> = { ...(o?.pinned ?? {}) };
  for (const a of o?.excluded ?? []) out[a] = "exclude";
  return out;
}

function PlanForm({ campaign, teams, defaultDate, latest }: { campaign: Campaign; teams: Team[]; defaultDate: string; latest: Plan | null }) {
  const t = useTranslations("campaigns");
  const tc = useTranslations("common");
  const router = useRouter();
  const [date, setDate] = useState(defaultDate);
  const prevTeams = new Map(((latest?.inputs as { teams?: { team_id: string; shift_start: string; shift_end: string; doses: number }[] } | undefined)?.teams ?? []).map((x) => [x.team_id, x]));
  const [use, setUse] = useState<Record<string, { on: boolean; start: string; end: string; doses: string }>>(
    Object.fromEntries(
      teams.map((tm) => {
        const prev = prevTeams.get(tm.id);
        return [tm.id, { on: latest ? Boolean(prev) : true, start: prev?.shift_start ?? tm.shift_start, end: prev?.shift_end ?? tm.shift_end, doses: String(prev?.doses ?? tm.doses_per_day) }];
      }),
    ),
  );
  const [speed, setSpeed] = useState("15");
  const [choice, setChoice] = useState<Record<string, string>>(() => initialChoices(latest));
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function makePlan() {
    const chosen = teams.filter((tm) => use[tm.id]?.on);
    if (!chosen.length) return setError(t("chooseTeam"));
    setBusy(true);
    setError(null);
    const pinned: Record<string, string> = {};
    const excluded: string[] = [];
    for (const [area, c] of Object.entries(choice)) {
      if (c === "exclude") excluded.push(area);
      else if (c) pinned[area] = c;
    }
    const { data, error: apiError } = await browserApi.POST("/api/v1/campaigns/{campaign_id}/plans", {
      params: { path: { campaign_id: campaign.id } },
      body: {
        plan_date: date,
        teams: chosen.map((tm) => ({ team_id: tm.id, shift_start: use[tm.id]!.start, shift_end: use[tm.id]!.end, doses: Number(use[tm.id]!.doses) })),
        speed_kmh: Number(speed) || 15,
        pinned,
        excluded,
      },
    });
    setBusy(false);
    if (data) router.push(`/app/campaigns/${campaign.id}?plan=${data.id}`);
    else setError(parseApiError(apiError).message || tc("tryAgainLater"));
  }

  return (
    <Card className="space-y-4">
      <h2 className="text-lg">{t("planTitle")}</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id="plan-date" label={t("planDate")}>
          {(aria) => <TextInput {...aria} type="date" value={date} onChange={(e) => setDate(e.target.value)} />}
        </Field>
        <Field id="plan-speed" label={t("speed")} hint={t("speedHint")}>
          {(aria) => <TextInput {...aria} inputMode="numeric" value={speed} onChange={(e) => setSpeed(e.target.value.replace(/[^\d.]/g, ""))} />}
        </Field>
      </div>
      <fieldset className="space-y-2">
        <legend className="font-semibold">{t("teams")}</legend>
        {teams.length === 0 ? <p className="text-ink-2">{t("noTeams")}</p> : null}
        {teams.map((tm) => (
          <div key={tm.id} className="grid items-end gap-2 sm:grid-cols-[1fr_8rem_8rem_8rem]">
            <label className="inline-flex min-h-11 items-center gap-2">
              <input type="checkbox" className="size-5 accent-primary" checked={use[tm.id]?.on ?? false} onChange={(e) => setUse((u) => ({ ...u, [tm.id]: { ...u[tm.id]!, on: e.target.checked } }))} />
              {tm.name}
            </label>
            <Field id={`ts-${tm.id.slice(0, 8)}`} label={t("shiftStart")}>
              {(aria) => <TextInput {...aria} type="time" value={use[tm.id]?.start ?? ""} onChange={(e) => setUse((u) => ({ ...u, [tm.id]: { ...u[tm.id]!, start: e.target.value } }))} />}
            </Field>
            <Field id={`te-${tm.id.slice(0, 8)}`} label={t("shiftEnd")}>
              {(aria) => <TextInput {...aria} type="time" value={use[tm.id]?.end ?? ""} onChange={(e) => setUse((u) => ({ ...u, [tm.id]: { ...u[tm.id]!, end: e.target.value } }))} />}
            </Field>
            <Field id={`td-${tm.id.slice(0, 8)}`} label={t("doses")}>
              {(aria) => <TextInput {...aria} inputMode="numeric" value={use[tm.id]?.doses ?? ""} onChange={(e) => setUse((u) => ({ ...u, [tm.id]: { ...u[tm.id]!, doses: e.target.value.replace(/\D/g, "") } }))} />}
            </Field>
          </div>
        ))}
      </fieldset>
      <fieldset className="space-y-2">
        <legend className="font-semibold">{t("overrides")}</legend>
        <p className="text-sm text-ink-2">{t("overridesHint")}</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {campaign.areas.map((a) => (
            <Field key={a.area_id} id={`ov-${a.area_id.slice(0, 8)}`} label={a.name}>
              {(aria) => (
                <Select {...aria} value={choice[a.area_id] ?? ""} onChange={(e) => setChoice((c) => ({ ...c, [a.area_id]: e.target.value }))}>
                  <option value="">{t("anyTeam")}</option>
                  {teams.map((tm) => (
                    <option key={tm.id} value={tm.id}>{t("onlyTeam", { team: tm.name })}</option>
                  ))}
                  <option value="exclude">{t("exclude")}</option>
                </Select>
              )}
            </Field>
          ))}
        </div>
      </fieldset>
      {error ? (
        <p role="alert" className="font-semibold text-urgent">
          {error}
        </p>
      ) : null}
      <Button onClick={makePlan} loading={busy} disabled={!teams.length}>
        {t("makePlan")}
      </Button>
    </Card>
  );
}

function PlanView({ plan, campaign, canPublish }: { plan: Plan; campaign: Campaign; canPublish: boolean }) {
  const t = useTranslations("campaigns");
  const tc = useTranslations("common");
  const router = useRouter();
  const [current, setCurrent] = useState(plan);
  const [confirm, setConfirm] = useState<"approve" | "publish" | null>(null);
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (current.state !== "solving") return;
    const timer = setTimeout(async () => {
      const { data } = await browserApi.GET("/api/v1/plans/{plan_id}", { params: { path: { plan_id: current.id } } });
      if (data) setCurrent(data);
    }, 1500);
    return () => clearTimeout(timer);
  }, [current]);

  async function act() {
    setBusy(true);
    setError(null);
    const body = { row_version: current.row_version, note: note.trim() || null };
    const res =
      confirm === "approve"
        ? await browserApi.POST("/api/v1/plans/{plan_id}/approve", { params: { path: { plan_id: current.id } }, body })
        : await browserApi.POST("/api/v1/plans/{plan_id}/publish", { params: { path: { plan_id: current.id } }, body });
    setBusy(false);
    if (res.error) return setError(parseApiError(res.error).message || tc("tryAgainLater"));
    setCurrent(res.data);
    setConfirm(null);
    router.refresh();
  }

  const r = current.result as unknown as Result;
  const nameOf = (id: string) => campaign.areas.find((a) => a.area_id === id)?.name ?? id;
  return (
    <section aria-labelledby="plan" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id="plan" className="text-lg">{t("planHeading", { v: current.version, date: current.plan_date })}</h2>
        <StatusChip kind={PLAN_CHIP[current.state as keyof typeof PLAN_CHIP] ?? "neutral"}>{t(`planState.${current.state}` as "planState.ready")}</StatusChip>
      </div>
      {current.state === "solving" ? <Card aria-live="polite"><p>{t("solving")}</p></Card> : null}
      {current.state === "failed" ? <Notice tone="urgent" title={t("failedTitle")}><p>{t("failedBody")}</p></Notice> : null}
      {r?.routes ? (
        <>
          <Notice tone="info" title={t("proposalTitle")}>
            <p>{t("proposalBody")}</p>
            {r.notes.map((n) => (
              <p key={n}>{n}</p>
            ))}
          </Notice>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Stat label={t("areasPlanned")} value={`${r.totals.areas_planned} / ${r.totals.areas_total}`} />
            <Stat label={t("animalsPlanned")} value={`${r.totals.animals_planned} / ${r.totals.animals_total}`} />
            <Stat label={t("travel")} value={t("minutes", { n: r.totals.travel_minutes })} />
            <Stat label={t("baseline")} value={t("baselineValue", { areas: r.baseline.totals.areas_planned, animals: r.baseline.totals.animals_planned, minutes: r.baseline.totals.travel_minutes })} />
          </dl>
          <p className="text-sm text-ink-2">{t("solverUsed", { solver: t(`solver.${r.solver}` as "solver.ortools") })}</p>
          {r.routes.map((route) => (
            <Card key={route.team_id} className="space-y-2">
              <p className="font-display font-semibold">
                {route.name} · {route.shift} · {t("dosesUsed", { used: route.doses_used, total: route.doses_available })}
              </p>
              {route.stops.length ? (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-xl text-left text-sm">
                    <thead>
                      <tr className="border-b border-divider">
                        <th scope="col" className="p-2">#</th>
                        <th scope="col" className="p-2">{t("colArea")}</th>
                        <th scope="col" className="p-2">{t("colArrive")}</th>
                        <th scope="col" className="p-2">{t("colWork")}</th>
                        <th scope="col" className="p-2">{t("colAnimals")}</th>
                        <th scope="col" className="p-2">{t("colTravel")}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {route.stops.map((s, i) => (
                        <tr key={s.area_id} className="border-b border-divider">
                          <td className="p-2">{i + 1}</td>
                          <td className="p-2">{s.name}</td>
                          <td className="p-2">{s.arrive}</td>
                          <td className="p-2">{s.start}–{s.finish}</td>
                          <td className="p-2">{s.animals}</td>
                          <td className="p-2">{t("minutes", { n: s.travel_minutes })}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <p className="text-ink-2">{t("noStops")}</p>
              )}
            </Card>
          ))}
          {r.unassigned.length ? (
            <Card className="space-y-2">
              <h3 className="font-display font-semibold">{t("unplannedTitle")}</h3>
              <ul className="space-y-1">
                {r.unassigned.map((u) => (
                  <li key={u.area_id}>
                    <span className="font-semibold">{nameOf(u.area_id)}</span>: {u.reasons.map((code) => t(`reason.${code}` as "reason.no_location")).join(" ")}
                  </li>
                ))}
              </ul>
            </Card>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {current.state === "ready" ? <Button onClick={() => setConfirm("approve")}>{t("approve")}</Button> : null}
            {current.state === "approved" && canPublish ? <Button onClick={() => setConfirm("publish")}>{t("publish")}</Button> : null}
            {current.approved_at ? <p className="text-sm text-ink-2">{t("approvedBy", { name: current.approved_by_name ?? "—" })}{current.approval_note ? ` — ${current.approval_note}` : ""}</p> : null}
            {current.state === "published" ? <p role="status">{t("publishedTasks", { n: current.task_count })} <Link href="/app/tasks">{t("seeTasks")}</Link></p> : null}
          </div>
        </>
      ) : null}
      <Dialog
        open={confirm !== null}
        onOpenChange={(o) => !o && setConfirm(null)}
        title={confirm === "approve" ? t("approveTitle") : t("publishTitle", { n: r?.routes?.reduce((n, x) => n + x.stops.length, 0) ?? 0 })}
        description={confirm === "approve" ? t("approveBody") : t("publishBody")}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setConfirm(null)}>
              {tc("cancel")}
            </Button>
            <Button onClick={act} loading={busy}>
              {tc("confirm")}
            </Button>
          </>
        }
      >
        {confirm === "approve" ? (
          <Field id="approve-note" label={t("approveNote")} marker={tc("optional")}>
            {(aria) => <Textarea {...aria} value={note} maxLength={500} onChange={(e) => setNote(e.target.value)} />}
          </Field>
        ) : null}
        {error ? (
          <p role="alert" className="font-semibold text-urgent">
            {error}
          </p>
        ) : null}
      </Dialog>
    </section>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control bg-canvas p-3">
      <dt className="text-sm text-ink-2">{label}</dt>
      <dd className="font-display text-lg font-bold">{value}</dd>
    </div>
  );
}
