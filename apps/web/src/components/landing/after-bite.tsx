import { BellRing, CalendarCheck, Moon, QrCode, ShieldCheck } from "lucide-react";
import { getTranslations } from "next-intl/server";

import { FirstAid } from "@/components/bite/first-aid";
import { Link } from "@/i18n/navigation";

const HELPS = [
  { key: "scan", Icon: QrCode, href: null },
  { key: "watch", Icon: CalendarCheck, href: null },
  { key: "verify", Icon: ShieldCheck, href: "/verify" },
  { key: "protect", Icon: BellRing, href: "/sign-in" },
] as const;

/** After the story: first aid (same sourced wording as bite mode), then where PawGuard helps, then prevention. */
export async function AfterBite() {
  const t = await getTranslations("story.after");
  return (
    <section id="what-to-do" aria-labelledby="what-to-do-h" className="scroll-mt-4 bg-surface py-14">
      <div className="container-pg">
        <h2 id="what-to-do-h" className="text-2xl md:text-3xl">
          {t("title")}
        </h2>
        <p className="mt-2 max-w-prose text-lg text-ink-2">{t("intro")}</p>
        <div className="mt-8 grid items-start gap-8 lg:grid-cols-[1fr_1.15fr]">
          <FirstAid headingLevel={3} />
          <div>
            <h3 className="text-xl">{t("helpsTitle")}</h3>
            <ol className="mt-5 space-y-5">
              {HELPS.map(({ key, Icon, href }, i) => (
                <li key={key} className="flex gap-4">
                  <span className="flex size-10 shrink-0 items-center justify-center rounded-full bg-primary font-display font-bold text-white">
                    {i + 1}
                  </span>
                  <div>
                    <p className="font-display text-lg font-semibold">
                      <Icon aria-hidden className="mr-1.5 inline size-5 align-[-3px] text-primary" />
                      {t(`helps.${key}.title`)}
                    </p>
                    <p className="mt-1 text-ink-2">{t(`helps.${key}.body`)}</p>
                    {href ? (
                      <Link href={href} className="mt-1 inline-block font-semibold">
                        {t(`helps.${key}.link`)}
                      </Link>
                    ) : null}
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
        <div className="mt-10 flex gap-4 rounded-card bg-sand p-5">
          <Moon aria-hidden className="mt-1 size-6 shrink-0 text-primary" />
          <div>
            <h3 className="text-lg">{t("preventTitle")}</h3>
            <p className="mt-1">{t("preventBody")}</p>
          </div>
        </div>
      </div>
    </section>
  );
}
