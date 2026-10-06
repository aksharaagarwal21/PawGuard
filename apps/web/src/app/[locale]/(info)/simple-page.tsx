import { PublicPage } from "@/components/public-shell";

export function SimplePage({ locale, title, children }: { locale: string; title: string; children: React.ReactNode }) {
  return (
    <PublicPage locale={locale}>
      <div className="container-pg py-10">
        <h1 className="text-3xl">{title}</h1>
        <div className="prose-pg mt-4 space-y-4 text-lg">{children}</div>
      </div>
    </PublicPage>
  );
}
