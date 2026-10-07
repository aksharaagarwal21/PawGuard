"use client";

import {
  ArrowDown,
  Brain,
  ChevronLeft,
  ChevronRight,
  Droplets,
  Eye,
  Pause,
  Play,
  RotateCcw,
  Stethoscope,
  Thermometer,
  Wind,
  Zap,
  Activity,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Link } from "@/i18n/navigation";

const MOTION_QUERY = "(prefers-reduced-motion: reduce)";
const prefersReducedMotion = () => window.matchMedia(MOTION_QUERY).matches;
function subscribeMotion(onChange: () => void) {
  const mq = window.matchMedia(MOTION_QUERY);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

/** How long each scene stays on screen while playing (ms). The last scene stays until the viewer moves on. */
const DURATIONS = [3400, 3800, 3200, 3400, 10000, 0];
const LAST = DURATIONS.length - 1;

const SYMPTOMS = [
  { key: "fever", Icon: Thermometer },
  { key: "tingling", Icon: Zap },
  { key: "fear", Icon: Wind },
  { key: "agitation", Icon: Brain },
  { key: "paralysis", Icon: Activity },
] as const;

/**
 * Landing story: a child pats a sleeping dog and is bitten; what rabies can do later; what to do today.
 * Illustration is inline SVG; motion is CSS keyed on `data-scene` (globals.css, "Landing story"). With reduced motion
 * nothing plays by itself and the scenes are stepped with the buttons. Health wording: WHO rabies fact sheet (S01) and
 * WHO FAQ (S30) — CONTENT_REGISTER C-LAND-01..03, pending clinical review.
 */
export function BiteStory() {
  const t = useTranslations("story");
  const tf = useTranslations("bite.firstAid");
  const [scene, setScene] = useState(0);
  // Plays by itself only when motion is welcome; otherwise the viewer steps through (or presses Play).
  const reduced = useSyncExternalStore(subscribeMotion, prefersReducedMotion, () => true);
  const [choice, setChoice] = useState<boolean | null>(null);
  const playing = choice ?? !reduced;
  const setPlaying = (next: (p: boolean) => boolean) => setChoice(next(playing));

  useEffect(() => {
    if (!playing || scene >= LAST) return;
    const id = window.setTimeout(() => setScene((s) => Math.min(s + 1, LAST)), DURATIONS[scene]);
    return () => window.clearTimeout(id);
  }, [playing, scene]);

  const go = (s: number) => setScene(Math.max(0, Math.min(LAST, s)));
  const replay = () => {
    setScene(0);
    setChoice(true);
  };

  return (
    <div className="story overflow-hidden rounded-card border border-divider bg-surface shadow-card" data-scene={scene} data-playing={playing}>
      <div className="relative">
        <StoryArt label={t(`alt.${scene}`)} badge15={t("art.fifteen")} badgeWatch={t("art.watch")} />
        <span className="absolute top-3 left-3 rounded-full bg-surface/90 px-3 py-1 text-xs font-semibold text-ink-2 shadow-sm">
          {t("sceneOf", { n: scene + 1, total: LAST + 1 })}
        </span>
      </div>

      <div className="relative h-1 bg-divider" aria-hidden>
        {scene < LAST ? (
          <span
            key={scene}
            className="story-progress absolute inset-y-0 left-0 bg-primary"
            style={{ animationDuration: `${DURATIONS[scene]}ms`, animationPlayState: playing ? "running" : "paused" }}
          />
        ) : (
          <span className="absolute inset-0 bg-primary" />
        )}
      </div>

      <div className="space-y-4 p-5 md:p-6">
        <p aria-live="polite" className="min-h-14 font-display text-xl font-semibold md:text-2xl">
          {t(`scenes.${scene}`)}
        </p>

        {scene === 4 ? (
          <div className="story-fade rounded-card border-l-8 border-urgent bg-urgent-soft p-4" data-testid="story-symptoms">
            <h3 className="text-lg text-urgent">{t("symptoms.title")}</h3>
            <p className="mt-1">{t("symptoms.when")}</p>
            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
              {SYMPTOMS.map(({ key, Icon }) => (
                <li key={key} className="flex items-center gap-2 rounded-control bg-surface px-3 py-2">
                  <Icon aria-hidden className="size-5 shrink-0 text-urgent" />
                  <span>{t(`symptoms.${key}`)}</span>
                </li>
              ))}
            </ul>
            <p className="mt-3 font-semibold">{t("symptoms.fatal")}</p>
            <p className="mt-1 text-xs text-ink-2">{t("symptoms.source")}</p>
          </div>
        ) : null}

        {scene === LAST ? (
          <div className="story-fade space-y-4" data-testid="story-actions">
            <ol className="grid gap-3 md:grid-cols-3">
              <li className="flex gap-3 rounded-card bg-sky p-4">
                <Droplets aria-hidden className="mt-0.5 size-6 shrink-0 text-primary" />
                <span className="font-semibold">{tf("wash")}</span>
              </li>
              <li className="flex gap-3 rounded-card bg-sage p-4">
                <Stethoscope aria-hidden className="mt-0.5 size-6 shrink-0 text-primary" />
                <span className="font-semibold">{t("doctor")}</span>
              </li>
              <li className="flex gap-3 rounded-card bg-lavender p-4">
                <Eye aria-hidden className="mt-0.5 size-6 shrink-0 text-primary" />
                <span className="font-semibold">{t("watch")}</span>
              </li>
            </ol>
            <div className="flex flex-wrap gap-3">
              <a
                href="#what-to-do"
                className="inline-flex min-h-12 items-center gap-2 rounded-control bg-urgent px-5 font-display font-semibold text-white no-underline"
              >
                <ArrowDown aria-hidden className="size-5" />
                {t("whatToDo")}
              </a>
              <Link
                href="/sign-in"
                className="inline-flex min-h-12 items-center rounded-control border-2 border-primary px-5 font-display font-semibold text-primary no-underline"
              >
                {t("signIn")}
              </Link>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 border-t border-divider pt-4">
          <button type="button" onClick={() => go(scene - 1)} disabled={scene === 0} className="story-btn" aria-label={t("back")}>
            <ChevronLeft aria-hidden className="size-5" />
          </button>
          {scene < LAST ? (
            <button type="button" onClick={() => setPlaying((p) => !p)} className="story-btn px-4">
              {playing ? <Pause aria-hidden className="size-4" /> : <Play aria-hidden className="size-4" />}
              {playing ? t("pause") : t("play")}
            </button>
          ) : (
            <button type="button" onClick={replay} className="story-btn px-4">
              <RotateCcw aria-hidden className="size-4" />
              {t("replay")}
            </button>
          )}
          <button type="button" onClick={() => go(scene + 1)} disabled={scene === LAST} className="story-btn" aria-label={t("next")}>
            <ChevronRight aria-hidden className="size-5" />
          </button>
          <ol className="ml-1 flex items-center gap-1.5" aria-label={t("scenesLabel")}>
            {DURATIONS.map((_, i) => (
              <li key={i}>
                <button
                  type="button"
                  onClick={() => go(i)}
                  aria-label={t("goTo", { n: i + 1 })}
                  aria-current={i === scene ? "step" : undefined}
                  className="flex size-6 items-center justify-center"
                >
                  <span className={`block h-2 rounded-full transition-all ${i === scene ? "w-5 bg-primary" : "w-2 bg-divider"}`} />
                </button>
              </li>
            ))}
          </ol>
          <a href="#what-to-do" className="ml-auto text-sm font-semibold">
            {t("skip")}
          </a>
        </div>
      </div>
    </div>
  );
}

/** The illustration. Kid drawn with feet at (0,0) facing right; positions and poses come from CSS per scene. */
function StoryArt({ label, badge15, badgeWatch }: { label: string; badge15: string; badgeWatch: string }) {
  const skin = "#A0673C";
  const skinBack = "#8C5A35";
  const shirt = "#F2A541";
  const fur = "#C68642";
  const furDark = "#8B5A2B";
  return (
    <svg
      viewBox="0 0 800 400"
      preserveAspectRatio="xMidYMax slice"
      role="img"
      aria-label={label}
      className="block h-60 w-full sm:h-auto"
    >
      <defs>
        <linearGradient id="story-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#CFE8EF" />
          <stop offset="1" stopColor="#F4EEDF" />
        </linearGradient>
      </defs>

      {/* Street */}
      <rect width="800" height="400" fill="url(#story-sky)" />
      <circle cx="690" cy="70" r="30" fill="#F6C453" opacity="0.85" />
      <g fill="#FFFFFF" opacity="0.7">
        <ellipse cx="160" cy="70" rx="46" ry="12" />
        <ellipse cx="200" cy="60" rx="30" ry="12" />
        <ellipse cx="470" cy="96" rx="40" ry="10" />
      </g>
      <path d="M20 192 l72 -42 l72 42z" fill="#C9B79C" />
      <rect x="30" y="190" width="124" height="150" rx="4" fill="#E6DCCB" />
      <rect x="162" y="222" width="92" height="118" rx="4" fill="#EADFCF" />
      <g fill="#CDBFA6">
        <rect x="50" y="216" width="22" height="26" rx="2" />
        <rect x="104" y="216" width="22" height="26" rx="2" />
        <rect x="76" y="282" width="30" height="58" rx="3" />
        <rect x="182" y="246" width="20" height="24" rx="2" />
        <rect x="216" y="246" width="20" height="24" rx="2" />
      </g>
      <rect x="692" y="182" width="18" height="158" rx="6" fill="#8A6A4A" />
      <g fill="#86B88A">
        <circle cx="700" cy="160" r="58" />
        <circle cx="648" cy="192" r="42" />
        <circle cx="754" cy="194" r="40" />
      </g>
      <rect y="338" width="800" height="62" fill="#DCCBA8" />
      <path d="M0 339 H800" stroke="#C9B48C" strokeWidth="3" />
      <g fill="#C9B48C" opacity="0.6">
        <ellipse cx="120" cy="368" rx="30" ry="3" />
        <ellipse cx="420" cy="384" rx="40" ry="3" />
        <ellipse cx="690" cy="372" rx="26" ry="3" />
      </g>
      <ellipse cx="590" cy="347" rx="170" ry="11" fill="#000000" opacity="0.07" />

      {/* Tap (scene 6) */}
      <g className="tap">
        <rect x="372" y="214" width="10" height="126" rx="3" fill="#7B8A96" />
        <rect x="368" y="206" width="18" height="8" rx="3" fill="#5F6E7A" />
        <path d="M377 221 H346 V229" stroke="#7B8A96" strokeWidth="8" strokeLinecap="round" fill="none" />
        <rect className="water" x="343" y="232" width="6" height="24" rx="3" fill="#6EC1E4" />
        <g fill="#6EC1E4">
          <circle className="drop" cx="346" cy="272" r="2.6" />
          <circle className="drop" cx="342" cy="272" r="2.2" />
          <circle className="drop" cx="350" cy="272" r="2.2" />
        </g>
        <g transform="translate(398 168)">
          <rect width="86" height="32" rx="16" fill="#FFFFFF" stroke="#205C4F" strokeWidth="2" />
          <circle cx="17" cy="16" r="8" fill="none" stroke="#205C4F" strokeWidth="2" />
          <path d="M17 11 V16 H21" stroke="#205C4F" strokeWidth="2" fill="none" strokeLinecap="round" />
          <text x="31" y="21" fontSize="14" fill="#205C4F">
            {badge15}
          </text>
        </g>
      </g>

      {/* Dog, asleep with its head on its paws */}
      <g className="dog">
        <path d="M652 320 q30 -4 34 -24 q2 -10 -6 -8" stroke={fur} strokeWidth="9" strokeLinecap="round" fill="none" />
        <ellipse className="dog-body" cx="570" cy="312" rx="92" ry="36" fill={fur} />
        <ellipse cx="588" cy="296" rx="24" ry="13" fill={furDark} opacity="0.45" />
        <ellipse cx="625" cy="322" rx="34" ry="24" fill="#B8783A" />
        <ellipse cx="604" cy="343" rx="20" ry="7" fill="#B8783A" />
        <ellipse cx="468" cy="343" rx="28" ry="8" fill="#B8783A" />
        <ellipse cx="500" cy="345" rx="24" ry="7" fill="#B8783A" />
        <g className="dog-head">
          <path d="M488 282 q16 -10 30 6 q-6 12 -20 8z" fill={furDark} />
          <circle cx="478" cy="306" r="32" fill={fur} />
          <ellipse cx="446" cy="318" rx="22" ry="15" fill="#E8C39E" />
          <ellipse cx="428" cy="312" rx="7" ry="5.5" fill="#2B1B12" />
          <path d="M494 284 q22 -6 24 22 q-14 4 -22 -6z" fill={furDark} />
          <g className="dog-asleep">
            <path d="M465 301 q7 6 14 0" stroke="#2B1B12" strokeWidth="3" fill="none" strokeLinecap="round" />
          </g>
          <g className="dog-awake">
            <circle cx="472" cy="300" r="4.5" fill="#2B1B12" />
            <circle cx="473.5" cy="298.5" r="1.4" fill="#FFFFFF" />
          </g>
          <path className="dog-brow" d="M461 290 l17 5" stroke="#2B1B12" strokeWidth="3" strokeLinecap="round" />
          <path className="dog-mouth-closed" d="M430 325 q12 6 26 0" stroke="#5A3A22" strokeWidth="2.5" fill="none" strokeLinecap="round" />
          <g className="dog-mouth-open">
            <path d="M424 322 q20 24 42 6 l-5 -4 q-16 10 -33 -4z" fill="#7A2E2E" />
            <path d="M430 323 l3 6 l3 -6z M441 326 l3 6 l3 -6z M452 325 l3 6 l3 -6z" fill="#FFFFFF" />
          </g>
        </g>
        <g className="zzz" fill="#5B6B7A" fontWeight="700">
          <text x="520" y="262" fontSize="18">z</text>
          <text x="540" y="244" fontSize="22">z</text>
          <text x="562" y="222" fontSize="28">z</text>
        </g>
        <text className="alert" x="430" y="252" fontSize="44" fontWeight="800" fill="#A43E35">
          !
        </text>
        <g className="watch-badge" transform="translate(512 228)">
          <rect width="118" height="32" rx="16" fill="#FFFFFF" stroke="#205C4F" strokeWidth="2" />
          <rect x="12" y="9" width="16" height="15" rx="2" fill="none" stroke="#205C4F" strokeWidth="2" />
          <path d="M12 14 H28" stroke="#205C4F" strokeWidth="2" />
          <text x="35" y="21" fontSize="14" fill="#205C4F">
            {badgeWatch}
          </text>
        </g>
      </g>

      <rect className="dim" width="800" height="400" fill="#0B1F1A" />
      <path className="burst" d="M455 236 l7 18 l18 -6 l-10 16 l16 10 l-19 2 l2 19 l-14 -13 l-12 14 l1 -19 l-19 -1 l15 -12 l-11 -16 l18 6z" fill="#F6C453" stroke="#A43E35" strokeWidth="2" />

      {/* Child */}
      <g transform="translate(0 340)">
        <g className="kid-move">
          <ellipse cx="-2" cy="2" rx="24" ry="4" fill="#000000" opacity="0.1" />
          <g className="kid-lean">
            <g className="kid-bob">
              <g className="kid-limb kid-arm-back">
                <rect x="-16" y="-136" width="13" height="18" rx="6" fill={shirt} />
                <rect x="-14" y="-132" width="9" height="58" rx="4.5" fill={skinBack} />
                <circle cx="-9.5" cy="-72" r="6" fill={skinBack} />
              </g>
              <g className="kid-limb kid-leg-b">
                <rect x="-11" y="-74" width="10" height="68" rx="5" fill={skinBack} />
                <ellipse cx="-4" cy="-4" rx="10" ry="5" fill="#33415C" />
              </g>
              <g className="kid-limb kid-leg-a">
                <rect x="1" y="-74" width="10" height="68" rx="5" fill={skin} />
                <ellipse cx="8" cy="-4" rx="10" ry="5" fill="#3E4C6E" />
              </g>
              <path d="M-17 -88 h34 v22 h-15 l-2 -6 l-2 6 h-15z" fill="#2F4B7C" />
              <rect x="-31" y="-136" width="14" height="40" rx="5" fill="#3B7A57" />
              <rect x="-19" y="-142" width="38" height="58" rx="11" fill={shirt} />
              <path d="M-19 -112 h38" stroke="#E08E2B" strokeWidth="5" />
              <rect x="-5" y="-148" width="10" height="9" fill={skin} />
              <circle cx="0" cy="-165" r="21" fill={skin} />
              <path d="M-21 -168 q2 -22 24 -21 q16 2 19 16 q-10 -6 -22 -4 q-12 2 -21 9z" fill="#2B1B12" />
              <circle cx="-13" cy="-162" r="4" fill={skinBack} />
              <g className="kid-happy">
                <circle cx="10" cy="-167" r="2.3" fill="#1B1B1B" />
                <path d="M6 -155 q6 5 12 0" stroke="#1B1B1B" strokeWidth="2" fill="none" strokeLinecap="round" />
              </g>
              <g className="kid-calm">
                <circle cx="10" cy="-167" r="2.3" fill="#1B1B1B" />
                <path d="M7 -154 h9" stroke="#1B1B1B" strokeWidth="2" strokeLinecap="round" />
              </g>
              <g className="kid-hurt">
                <path d="M5 -173 l9 -2" stroke="#1B1B1B" strokeWidth="2" strokeLinecap="round" />
                <circle cx="10" cy="-166" r="2.6" fill="#1B1B1B" />
                <ellipse cx="12" cy="-154" rx="3.2" ry="4" fill="#5A1E1E" />
                <path d="M14 -162 q2.5 5 0 8 q-3 -2 0 -8z" fill="#6EC1E4" />
              </g>
              <circle className="head-glow" cx="0" cy="-165" r="27" fill="none" stroke="#E5484D" strokeWidth="3" />
              <g className="kid-limb kid-arm">
                <rect x="4" y="-136" width="13" height="18" rx="6" fill={shirt} />
                <rect x="6" y="-132" width="9" height="60" rx="4.5" fill={skin} />
                <circle cx="10.5" cy="-70" r="6.5" fill={skin} />
                <g className="bite-marks" fill="#B42318">
                  <circle cx="8" cy="-71" r="1.7" />
                  <circle cx="13" cy="-68" r="1.7" />
                </g>
              </g>
              <path className="nerve-line" d="M10.5 -70 V-128 Q6 -142 0 -152" stroke="#E5484D" strokeWidth="2" strokeDasharray="3 4" fill="none" />
              <g className="nerve" fill="#E5484D">
                <circle r="3.4" />
                <circle r="3.4" />
                <circle r="3.4" />
                <circle r="3.4" />
              </g>
            </g>
          </g>
        </g>
      </g>
    </svg>
  );
}
