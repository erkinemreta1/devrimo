"use client";

import { useEffect, useMemo, useState } from "react";
import { CalendarDaysIcon, ClipboardIcon, DownloadIcon, PlusIcon, RotateCcwIcon, SaveIcon, SparklesIcon, Trash2Icon } from "lucide-react";
import { toast } from "sonner";
import { useLocale } from "@/components/locale-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { jsonFetch } from "@/lib/api/fetcher";
import { cn } from "@/lib/utils";

type Day = "Mon" | "Tue" | "Wed" | "Thu" | "Fri";
type Entry = { id: string; code: string; name: string; section: string; day: Day; start: number; duration: number; startLabel: string; endLabel: string; room: string; credits: number; color: number; kind: "course" | "block" };
type CourseChoice = { code: string; name: string };
type SavedPlan = { entries: Entry[]; term: string; courses: CourseChoice[]; emptyDay: string; earliestStart: string; latestEnd: string; minCredits: number; maxCredits: number };
type PlanCourse = { course_code: string; section: string; title: string; credits: number; schedule: Array<{ day?: string; start?: string; end?: string; room?: string; location?: string }> };
type PlanResponse = { status: "ok" | "constraints_unsatisfied" | "needs_academic_snapshot"; detail?: string; courses?: PlanCourse[]; selected_credits?: number; missing_required_courses?: string[]; excluded_options?: Array<{ course_code: string; section: string; reason: string }>; assumptions?: string[] };

const DAYS: Day[] = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const HOURS = Array.from({ length: 12 }, (_, index) => index + 8);
const COLORS = ["bg-rose-500/14 border-rose-500/35 text-rose-950 dark:text-rose-100", "bg-sky-500/14 border-sky-500/35 text-sky-950 dark:text-sky-100", "bg-amber-500/16 border-amber-500/40 text-amber-950 dark:text-amber-100", "bg-emerald-500/14 border-emerald-500/35 text-emerald-950 dark:text-emerald-100", "bg-violet-500/14 border-violet-500/35 text-violet-950 dark:text-violet-100"];
const STORAGE_KEY = "devrimo:schedule:v2";
const FULL_DAY: Record<Day, string> = { Mon: "monday", Tue: "tuesday", Wed: "wednesday", Thu: "thursday", Fri: "friday" };

function parseDay(value: string): Day | null {
  const day = value.toLowerCase();
  if (/monday|pazartesi|\bmon\b/.test(day)) return "Mon";
  if (/tuesday|salı|sali|\btue\b/.test(day)) return "Tue";
  if (/wednesday|çarşamba|carsamba|\bwed\b/.test(day)) return "Wed";
  if (/thursday|perşembe|persembe|\bthu\b/.test(day)) return "Thu";
  if (/friday|cuma|\bfri\b/.test(day)) return "Fri";
  return null;
}

function minutes(value: string | undefined, fallback: number) {
  const match = value?.match(/^(\d{1,2}):(\d{2})/);
  return match ? Number(match[1]) * 60 + Number(match[2]) : fallback;
}

function planEntries(courses: PlanCourse[]): Entry[] {
  return courses.flatMap((course, courseIndex) => (course.schedule ?? []).flatMap((meeting, meetingIndex) => {
    const day = parseDay(meeting.day ?? "");
    if (!day) return [];
    const startMinutes = minutes(meeting.start, 8 * 60);
    const endMinutes = minutes(meeting.end, startMinutes + 60);
    return [{ id: crypto.randomUUID(), code: course.course_code, name: course.title || course.course_code, section: course.section, day, start: Math.floor(startMinutes / 60), duration: Math.max(1, Math.ceil((endMinutes - startMinutes) / 60)), startLabel: meeting.start ?? "08:00", endLabel: meeting.end ?? "09:00", room: meeting.room ?? meeting.location ?? "", credits: meetingIndex === 0 ? Number(course.credits || 0) : 0, color: courseIndex % COLORS.length, kind: "course" as const }];
  }));
}

function overlaps(a: Entry, b: Entry) {
  return a.day === b.day && a.start < b.start + b.duration && b.start < a.start + a.duration;
}

export function DeterministicSchedulePlanner() {
  const { pick } = useLocale();
  const t = (tr: string, en: string) => pick({ tr, en });
  const [entries, setEntries] = useState<Entry[]>([]);
  const [term, setTerm] = useState("20261");
  const [department, setDepartment] = useState("");
  const [courses, setCourses] = useState<CourseChoice[]>([]);
  const [courseDraft, setCourseDraft] = useState<CourseChoice>({ code: "", name: "" });
  const [emptyDay, setEmptyDay] = useState("");
  const [earliestStart, setEarliestStart] = useState("08:00");
  const [latestEnd, setLatestEnd] = useState("20:00");
  const [minCredits, setMinCredits] = useState(0);
  const [maxCredits, setMaxCredits] = useState(20);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [details, setDetails] = useState<PlanResponse | null>(null);
  const [draft, setDraft] = useState({ code: "", name: "", section: "1", day: "Mon" as Day, start: 9, duration: 1, room: "", credits: 3 });

  useEffect(() => {
    let cancelled = false;
    void jsonFetch<{ department?: string | null }>("/api/student/context").then((context) => { if (!cancelled) setDepartment(context.department ?? ""); }).catch(() => { if (!cancelled) setDepartment(""); });
    return () => { cancelled = true; };
  }, []);

  const conflicts = useMemo(() => new Set(entries.flatMap((entry, index) => entries.slice(index + 1).filter((other) => overlaps(entry, other)).flatMap((other) => [entry.id, other.id]))), [entries]);
  const uniqueCourses = new Set(entries.filter((entry) => entry.kind === "course").map((entry) => entry.code)).size;
  const totalCredits = entries.reduce((sum, entry) => sum + entry.credits, 0);
  const totalHours = entries.reduce((sum, entry) => sum + entry.duration, 0);
  const groupedEntries = useMemo(() => {
    const groups = new Map<string, Entry[]>();
    for (const entry of entries) groups.set(`${entry.code}::${entry.section}`, [...(groups.get(`${entry.code}::${entry.section}`) ?? []), entry]);
    return [...groups.values()];
  }, [entries]);
  const dayLabel = (day: Day) => ({ Mon: t("Pzt", "Mon"), Tue: t("Sal", "Tue"), Wed: t("Çar", "Wed"), Thu: t("Per", "Thu"), Fri: t("Cum", "Fri") })[day];

  function addCourse() {
    const code = courseDraft.code.toUpperCase().replace(/\s+/g, "").trim();
    if (!code) return toast.error(t("Ders kodu gerekli.", "A course code is required."));
    if (courses.some((course) => course.code === code)) return toast.error(t("Bu ders zaten listede.", "This course is already listed."));
    setCourses((current) => [...current, { code, name: courseDraft.name.trim() }]);
    setCourseDraft({ code: "", name: "" });
  }

  async function generateSchedule() {
    setBusy(true);
    setNotice("");
    try {
      const result = await jsonFetch<PlanResponse>("/api/student/plan", { method: "POST", body: { term: term.trim(), required_courses: courses.map((course) => course.code), min_credits: minCredits, max_credits: maxCredits, days_off: emptyDay ? [FULL_DAY[emptyDay as Day]] : [], earliest_start: earliestStart, latest_end: latestEnd } });
      setDetails(result);
      if (result.status === "needs_academic_snapshot") {
        setEntries([]);
        setNotice(result.detail ?? t("SAIS akademik verisi gerekli.", "SAIS academic data is required."));
        return;
      }
      const planned = planEntries(result.courses ?? []);
      setEntries(planned);
      const missing = result.missing_required_courses ?? [];
      setNotice(missing.length ? t(`Eksik zorunlu dersler: ${missing.join(", ")}`, `Missing required courses: ${missing.join(", ")}`) : t(`${result.selected_credits ?? 0} kredilik doğrulanmış program oluşturuldu.`, `A verified ${result.selected_credits ?? 0}-credit schedule was generated.`));
      if (planned.length) toast.success(t("Program oluşturuldu.", "Schedule generated."));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t("Program oluşturulamadı.", "The schedule could not be generated."));
    } finally {
      setBusy(false);
    }
  }

  function addManualEntry() {
    const code = draft.code.trim().toUpperCase();
    if (!code) return toast.error(t("Ders kodu veya blok adı gerekli.", "A course code or block name is required."));
    const next: Entry = { ...draft, id: crypto.randomUUID(), code, name: draft.name.trim() || code, room: draft.room.trim(), color: uniqueCourses % COLORS.length, kind: code.startsWith("BLOCK:") ? "block" : "course", startLabel: `${String(draft.start).padStart(2, "0")}:00`, endLabel: `${String(draft.start + draft.duration).padStart(2, "0")}:00` };
    if (emptyDay === next.day || entries.some((entry) => overlaps(entry, next))) return toast.error(t("Bu oturum seçili kısıtlarla çakışıyor.", "This session conflicts with the selected constraints."));
    setEntries((current) => [...current, next]);
    setDraft((current) => ({ ...current, code: "", name: "", room: "" }));
  }

  function save() {
    const payload: SavedPlan = { entries, term, courses, emptyDay, earliestStart, latestEnd, minCredits, maxCredits };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    toast.success(t("Program bu cihazda kaydedildi.", "Schedule saved on this device."));
  }

  function load() {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return toast.error(t("Kaydedilmiş program bulunamadı.", "No saved schedule was found."));
    try {
      const saved = JSON.parse(raw) as SavedPlan;
      setEntries(Array.isArray(saved.entries) ? saved.entries : []); setTerm(saved.term || "20261"); setCourses(Array.isArray(saved.courses) ? saved.courses : []); setEmptyDay(saved.emptyDay || ""); setEarliestStart(saved.earliestStart || "08:00"); setLatestEnd(saved.latestEnd || "20:00"); setMinCredits(Number(saved.minCredits || 0)); setMaxCredits(Number(saved.maxCredits || 20));
      toast.success(t("Program yüklendi.", "Schedule loaded."));
    } catch { toast.error(t("Kayıt okunamadı.", "The saved schedule could not be read.")); }
  }

  async function copySummary() {
    const summary = DAYS.map((day) => `${dayLabel(day)}: ${entries.filter((entry) => entry.day === day).sort((a, b) => a.start - b.start).map((entry) => `${entry.startLabel} ${entry.code}-${entry.section}${entry.room ? ` (${entry.room})` : ""}`).join(", ") || "—"}`).join("\n");
    await navigator.clipboard.writeText(summary);
    toast.success(t("Program özeti kopyalandı.", "Schedule summary copied."));
  }

  useEffect(() => {
    if (!window.location.hash.startsWith("#plan=")) return;
    const timer = window.setTimeout(() => {
      try { setEntries(JSON.parse(decodeURIComponent(escape(atob(window.location.hash.slice(6))))) as Entry[]); }
      catch { toast.error(t("Paylaşılan program okunamadı.", "The shared schedule could not be read.")); }
    }, 0);
    return () => window.clearTimeout(timer);
  // The hash is read once when this page opens.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function copyShareLink() {
    const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(entries))));
    await navigator.clipboard.writeText(`${window.location.origin}/schedule#plan=${encoded}`);
    toast.success(t("Salt okunur paylaşım bağlantısı kopyalandı.", "Read-only share link copied."));
  }

  function exportWallpaper() {
    const escapeXml = (value: string) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
    const cells = entries.map((entry) => `<rect x="${460 + DAYS.indexOf(entry.day) * 650}" y="${330 + (entry.start - 8) * 150}" width="610" height="${entry.duration * 140}" rx="24" fill="#e31837" opacity=".9"/><text x="${490 + DAYS.indexOf(entry.day) * 650}" y="${390 + (entry.start - 8) * 150}" fill="white" font-size="36" font-family="Arial" font-weight="700">${escapeXml(entry.code)}</text>`).join("");
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 3840 2160"><rect width="100%" height="100%" fill="#171312"/><text x="180" y="170" fill="white" font-size="72" font-family="Arial" font-weight="700">Devrimo · ${escapeXml(term)}</text>${DAYS.map((day, index) => `<text x="${500 + index * 650}" y="285" fill="#aaa" font-size="36" font-family="Arial">${escapeXml(dayLabel(day))}</text>`).join("")}${cells}</svg>`;
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    const link = document.createElement("a"); link.href = url; link.download = "devrimo-schedule-4k.svg"; link.click(); URL.revokeObjectURL(url);
  }

  return <div className="h-full overflow-y-auto bg-[radial-gradient(circle_at_85%_0%,rgb(227_24_55/8%),transparent_32%)] px-4 py-6 sm:px-6 lg:px-8"><div className="mx-auto max-w-[1500px] space-y-5">
    <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between"><div><p className="text-sm font-semibold text-primary">{t("Akademik planlayıcı", "Academic planner")}</p><h1 className="text-3xl font-semibold tracking-tight">{t("Ders programı", "Schedule")}</h1><p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t("Mevcut SAIS anlık görüntüsü ve yönetilen ders kataloğundan çakışmasız bir program oluştur.", "Build a conflict-free schedule from your current SAIS snapshot and the managed course catalog.")}</p></div><div className="flex flex-wrap gap-2"><Button variant="outline" onClick={load}>{t("Yükle", "Load")}</Button><Button variant="outline" onClick={save}><SaveIcon />{t("Kaydet", "Save")}</Button><Button variant="outline" onClick={() => { setEntries([]); setNotice(""); setDetails(null); }}><RotateCcwIcon />{t("Temizle", "Clear")}</Button></div></div>

    <div className="grid gap-5 xl:grid-cols-[330px_minmax(0,1fr)]"><aside className="space-y-5">
      <Card><CardHeader><CardTitle>{t("Plan kısıtları", "Plan constraints")}</CardTitle></CardHeader><CardContent className="grid gap-3">
        <Field label={t("Akademik dönem", "Academic term")}><Input value={term} onChange={(event) => setTerm(event.target.value)} placeholder="20261" /></Field>
        <Field label={t("Doğrulanmış bölüm", "Verified department")}><Input value={department || t("Henüz doğrulanmadı", "Not verified yet")} readOnly className="bg-muted/40" /></Field>
        <div className="grid grid-cols-2 gap-2"><Field label={t("En erken", "Earliest")}><Input type="time" value={earliestStart} onChange={(event) => setEarliestStart(event.target.value)} /></Field><Field label={t("En geç", "Latest")}><Input type="time" value={latestEnd} onChange={(event) => setLatestEnd(event.target.value)} /></Field></div>
        <div className="grid grid-cols-2 gap-2"><Field label={t("En az kredi", "Min credits")}><Input type="number" min={0} max={60} value={minCredits} onChange={(event) => setMinCredits(Number(event.target.value))} /></Field><Field label={t("En çok kredi", "Max credits")}><Input type="number" min={0} max={60} value={maxCredits} onChange={(event) => setMaxCredits(Number(event.target.value))} /></Field></div>
        <Field label={t("Boş gün", "Day off")}><select value={emptyDay} onChange={(event) => setEmptyDay(event.target.value)} className="h-10 w-full rounded-md border bg-background px-3 text-sm"><option value="">{t("Fark etmez", "No preference")}</option>{DAYS.map((day) => <option key={day} value={day}>{dayLabel(day)}</option>)}</select></Field>
        <Button onClick={() => void generateSchedule()} disabled={busy || !term.trim() || maxCredits < minCredits}><SparklesIcon />{busy ? t("Doğrulanıyor…", "Verifying…") : t("Program oluştur", "Generate schedule")}</Button>
        {notice ? <p className="rounded-lg border bg-muted/30 p-2 text-xs leading-5 text-muted-foreground">{notice}</p> : null}
      </CardContent></Card>

      <Card><CardHeader><CardTitle>{t("Zorunlu dersler", "Required courses")}</CardTitle></CardHeader><CardContent className="grid gap-3">
        <p className="text-xs leading-5 text-muted-foreground">{t("Boş bırakırsan planlayıcı, uygun dersler arasından kredi ve zaman kısıtlarına göre seçim yapar.", "Leave this empty to let the planner choose among eligible offerings using your credit and time constraints.")}</p>
        <Input value={courseDraft.code} onChange={(event) => setCourseDraft({ ...courseDraft, code: event.target.value })} placeholder="CENG213" /><Input value={courseDraft.name} onChange={(event) => setCourseDraft({ ...courseDraft, name: event.target.value })} placeholder={t("Ders adı (isteğe bağlı)", "Course name (optional)")} /><Button variant="outline" onClick={addCourse}><PlusIcon />{t("Ders ekle", "Add course")}</Button>
        {courses.map((course) => <div key={course.code} className="flex items-center justify-between gap-2 rounded-lg border px-3 py-2"><div className="min-w-0"><p className="font-semibold">{course.code}</p>{course.name ? <p className="truncate text-xs text-muted-foreground">{course.name}</p> : null}</div><Button size="icon" variant="ghost" aria-label={t(`${course.code} dersini kaldır`, `Remove ${course.code}`)} onClick={() => setCourses((current) => current.filter((item) => item.code !== course.code))}><Trash2Icon /></Button></div>)}
      </CardContent></Card>

      <Card><CardHeader><CardTitle>{t("Elle oturum ekle", "Add a session manually")}</CardTitle></CardHeader><CardContent className="grid gap-3">
        <div className="grid grid-cols-2 gap-2"><Field label={t("Kod", "Code")}><Input value={draft.code} onChange={(event) => setDraft({ ...draft, code: event.target.value })} placeholder="CENG213" /></Field><Field label={t("Şube", "Section")}><Input value={draft.section} onChange={(event) => setDraft({ ...draft, section: event.target.value })} /></Field></div><Field label={t("Ad", "Name")}><Input value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} /></Field>
        <div className="grid grid-cols-3 gap-2"><Field label={t("Gün", "Day")}><select value={draft.day} onChange={(event) => setDraft({ ...draft, day: event.target.value as Day })} className="h-10 w-full rounded-md border bg-background px-2 text-sm">{DAYS.map((day) => <option key={day} value={day}>{dayLabel(day)}</option>)}</select></Field><Field label={t("Başlangıç", "Start")}><select value={draft.start} onChange={(event) => setDraft({ ...draft, start: Number(event.target.value) })} className="h-10 w-full rounded-md border bg-background px-2 text-sm">{HOURS.map((hour) => <option key={hour} value={hour}>{String(hour).padStart(2, "0")}:00</option>)}</select></Field><Field label={t("Süre", "Hours")}><select value={draft.duration} onChange={(event) => setDraft({ ...draft, duration: Number(event.target.value) })} className="h-10 w-full rounded-md border bg-background px-2 text-sm">{[1, 2, 3].map((hour) => <option key={hour}>{hour}</option>)}</select></Field></div>
        <div className="grid grid-cols-2 gap-2"><Field label={t("Derslik", "Room")}><Input value={draft.room} onChange={(event) => setDraft({ ...draft, room: event.target.value })} /></Field><Field label={t("Kredi", "Credits")}><Input type="number" min={0} max={10} value={draft.credits} onChange={(event) => setDraft({ ...draft, credits: Number(event.target.value) })} /></Field></div><Button variant="outline" onClick={addManualEntry}><PlusIcon />{t("Programa ekle", "Add to schedule")}</Button>
      </CardContent></Card>
    </aside>

    <main className="min-w-0 space-y-5"><div className="grid grid-cols-3 gap-3">{[[t("Toplam kredi", "Total credits"), totalCredits], [t("Haftalık saat", "Weekly hours"), totalHours], [t("Ders", "Courses"), uniqueCourses]].map(([label, value]) => <Card key={String(label)}><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p></CardContent></Card>)}</div>
      <Card className="overflow-hidden"><CardHeader className="flex-row items-center justify-between gap-3"><div><CardTitle>{term}</CardTitle><p className="mt-1 text-xs text-muted-foreground">{conflicts.size ? t(`${conflicts.size} çakışan oturum`, `${conflicts.size} conflicting sessions`) : t("Çakışma yok", "No conflicts")}</p></div><Button size="icon" variant="ghost" aria-label={t("Özeti kopyala", "Copy summary")} onClick={() => void copySummary()}><ClipboardIcon /></Button></CardHeader><CardContent className="overflow-x-auto p-0"><div className="grid min-w-[820px] grid-cols-[72px_repeat(5,minmax(140px,1fr))] border-t text-sm"><div className="border-b border-r bg-muted/30" />{DAYS.map((day) => <div key={day} className={cn("border-b border-r px-3 py-2 text-center font-semibold", emptyDay === day && "bg-primary/7 text-primary")}>{dayLabel(day)}</div>)}{HOURS.flatMap((hour) => [<div key={`h-${hour}`} className="border-b border-r bg-muted/30 px-2 py-3 text-xs tabular-nums text-muted-foreground">{String(hour).padStart(2, "0")}:00</div>, ...DAYS.map((day) => <div key={`${day}-${hour}`} className={cn("relative min-h-20 border-b border-r p-1", emptyDay === day && "bg-muted/20")}>{entries.filter((entry) => entry.day === day && entry.start === hour).map((entry) => <button key={entry.id} onClick={() => setEntries((current) => current.filter((item) => item.id !== entry.id))} title={t("Kaldırmak için tıkla", "Click to remove")} style={{ minHeight: `${entry.duration * 4.5}rem` }} className={cn("relative z-10 w-full rounded-lg border p-2 text-left shadow-sm", COLORS[entry.color], conflicts.has(entry.id) && "ring-2 ring-destructive")}><span className="block font-semibold">{entry.code} · {entry.section}</span><span className="mt-1 block text-xs opacity-80">{entry.startLabel}–{entry.endLabel}</span>{entry.room ? <span className="mt-1 block text-xs font-medium">{entry.room}</span> : null}</button>)}</div>)] )}</div></CardContent></Card>
      <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={copyShareLink}><ClipboardIcon />{t("Paylaşım bağlantısı", "Share link")}</Button><Button variant="outline" onClick={() => window.print()}><DownloadIcon />{t("Yazdır", "Print")}</Button><Button variant="outline" onClick={exportWallpaper}><DownloadIcon />{t("4K duvar kâğıdı", "4K wallpaper")}</Button></div>
      {details ? <Card><CardHeader><CardTitle className="flex items-center gap-2"><CalendarDaysIcon className="size-4" />{t("Plan ayrıntıları", "Plan details")}</CardTitle></CardHeader><CardContent className="space-y-3 text-sm"><p><span className="font-medium">{t("Durum", "Status")}:</span> {details.status}</p>{details.excluded_options?.length ? <p className="text-muted-foreground">{t(`${details.excluded_options.length} uygun olmayan şube gerekçesiyle birlikte elendi.`, `${details.excluded_options.length} ineligible sections were excluded with reasons.`)}</p> : null}{details.assumptions?.length ? <ul className="list-disc space-y-1 pl-5 text-xs text-muted-foreground">{details.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul> : null}</CardContent></Card> : null}
      {entries.length ? <Card><CardHeader><CardTitle>{t("Eklenen dersler", "Added courses")}</CardTitle></CardHeader><CardContent className="space-y-2">{groupedEntries.map((group) => { const entry = group[0]; return <div key={`${entry.code}-${entry.section}`} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"><div className="min-w-0"><p className="truncate font-medium">{entry.code} · {entry.name}</p><p className="text-xs text-muted-foreground">{group.map((meeting) => `${dayLabel(meeting.day)} ${meeting.startLabel}`).join(" / ")} · {t("Şube", "Section")} {entry.section}</p></div><Button size="icon" variant="ghost" aria-label={t("Dersi kaldır", "Remove course")} onClick={() => { const ids = new Set(group.map((item) => item.id)); setEntries((current) => current.filter((item) => !ids.has(item.id))); }}><Trash2Icon /></Button></div>; })}</CardContent></Card> : null}
    </main></div>
  </div></div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="space-y-1.5"><Label>{label}</Label>{children}</div>;
}
