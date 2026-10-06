"use client";

import { Plus } from "lucide-react";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { Button, Dialog, Field, Select, TextInput, Textarea, useToast } from "@pawguard/ui";

import { useRouter } from "@/i18n/navigation";
import { browserApi, parseApiError } from "@/lib/api-browser";

const TYPES = ["vaccination_round", "survey", "animal_followup", "identity_review", "other"] as const;

export function CreateTask({
  members,
  areas,
}: {
  members: { membership_id: string; name: string | null }[];
  areas: { id: string; name: string }[];
}) {
  const t = useTranslations("tasks");
  const tc = useTranslations("common");
  const router = useRouter();
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [v, setV] = useState({ task_type: "vaccination_round" as (typeof TYPES)[number], title: "", instructions: "", area_id: "", assignee: "", due_on: "" });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!v.title.trim()) return setErrors({ title: t("taskTitle") });
    setBusy(true);
    const { error } = await browserApi.POST("/api/v1/tasks", {
      body: {
        task_type: v.task_type,
        title: v.title.trim(),
        instructions: v.instructions.trim() || null,
        area_id: v.area_id || null,
        assignee_membership_id: v.assignee || null,
        due_on: v.due_on || null,
      },
    });
    setBusy(false);
    if (error) {
      const p = parseApiError(error);
      return setErrors(Object.keys(p.fields).length ? p.fields : { title: p.message });
    }
    setOpen(false);
    toast({ title: t("created"), tone: "success" });
    router.refresh();
  }

  return (
    <>
      <Button onClick={() => setOpen(true)}>
        <Plus aria-hidden className="size-4" />
        {t("create")}
      </Button>
      <Dialog
        open={open}
        onOpenChange={setOpen}
        title={t("createTitle")}
        closeLabel={tc("close")}
        footer={
          <>
            <Button variant="secondary" onClick={() => setOpen(false)}>
              {tc("cancel")}
            </Button>
            <Button onClick={save} loading={busy}>
              {tc("save")}
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Field id="task_type" label={t("type")}>
            {(aria) => (
              <Select {...aria} value={v.task_type} onChange={(e) => setV({ ...v, task_type: e.target.value as (typeof TYPES)[number] })}>
                {TYPES.map((x) => (
                  <option key={x} value={x}>{t(`types.${x}`)}</option>
                ))}
              </Select>
            )}
          </Field>
          <Field id="title" label={t("taskTitle")} error={errors.title}>
            {(aria) => <TextInput {...aria} maxLength={200} value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} />}
          </Field>
          <Field id="instructions" label={t("instructions")} marker={tc("optional")}>
            {(aria) => <Textarea {...aria} maxLength={2000} value={v.instructions} onChange={(e) => setV({ ...v, instructions: e.target.value })} />}
          </Field>
          <Field id="area" label={t("area")} marker={tc("optional")}>
            {(aria) => (
              <Select {...aria} value={v.area_id} onChange={(e) => setV({ ...v, area_id: e.target.value })}>
                <option value="">—</option>
                {areas.map((a) => (
                  <option key={a.id} value={a.id}>{a.name}</option>
                ))}
              </Select>
            )}
          </Field>
          <Field id="assignee" label={t("assignee")} marker={tc("optional")} error={errors.assignee_membership_id}>
            {(aria) => (
              <Select {...aria} value={v.assignee} onChange={(e) => setV({ ...v, assignee: e.target.value })}>
                <option value="">{t("unassigned")}</option>
                {members.map((m) => (
                  <option key={m.membership_id} value={m.membership_id}>{m.name ?? m.membership_id}</option>
                ))}
              </Select>
            )}
          </Field>
          <Field id="due_on" label={t("due")} marker={tc("optional")}>
            {(aria) => <TextInput {...aria} type="date" value={v.due_on} onChange={(e) => setV({ ...v, due_on: e.target.value })} />}
          </Field>
        </div>
      </Dialog>
    </>
  );
}
