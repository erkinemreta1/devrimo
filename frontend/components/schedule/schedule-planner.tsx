"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CalendarDaysIcon, CheckIcon, ClipboardIcon, DownloadIcon, HeartIcon,
  PlusIcon, RotateCcwIcon, SaveIcon, SparklesIcon, Trash2Icon,
} from "lucide-react";
import { toast } from "sonner";
import { useLocale } from "@/components/locale-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";
import { jsonFetch } from "@/lib/api/fetcher";

type Day = "Mon" | "Tue" | "Wed" | "Thu" | "Fri";
type Entry = { id: string; code: string; name: string; section: string; day: Day; start: number; duration: number; room: string; credits: number; color: number; kind: "course" | "block" };
type SavedPlan = { entries: Entry[]; term: string; department: string; semester: string; surname: string; emptyDay: string; avoidConflicts: boolean; avoidTravel: boolean };
type CatalogCourse = { code: string; name: string; credits: number; rawCode: string };
type CatalogSection = { section: string; instructor: string; meetings: { day: Day; start: number; duration: number; room: string }[] };

const DAYS: Day[] = ["Mon", "Tue", "Wed", "Thu", "Fri"];
const HOURS = Array.from({ length: 10 }, (_, index) => index + 8);
const COLORS = ["bg-rose-500/14 border-rose-500/35 text-rose-950 dark:text-rose-100", "bg-sky-500/14 border-sky-500/35 text-sky-950 dark:text-sky-100", "bg-amber-500/16 border-amber-500/40 text-amber-950 dark:text-amber-100", "bg-emerald-500/14 border-emerald-500/35 text-emerald-950 dark:text-emerald-100", "bg-violet-500/14 border-violet-500/35 text-violet-950 dark:text-violet-100"];
const STORAGE_KEY = "devrimo:schedule:v1";

const keyValue = (record: Record<string, unknown>, candidates: string[]) => {
  const key = Object.keys(record).find((item) => candidates.some((candidate) => item.toLowerCase().replace(/[^a-z0-9]/g, "").includes(candidate)));
  return key ? record[key] : undefined;
};

function objectRecords(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) return value.flatMap(objectRecords);
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  if (keyValue(record, ["coursecode", "code", "coursename"])) return [record];
  return Object.values(record).flatMap(objectRecords);
}

function sectionRecords(value: unknown): Record<string, unknown>[] {
  if (Array.isArray(value)) return value.flatMap(sectionRecords);
  if (!value || typeof value !== "object") return [];
  const record = value as Record<string, unknown>;
  const normalizedKeys = Object.keys(record).map((key) => key.toLowerCase().replace(/[^a-z0-9]/g, ""));
  const isSectionRow = normalizedKeys.some((key) => ["sectionnumber", "section", "sectionno", "sec"].includes(key));
  const hasMeetingData = normalizedKeys.some((key) => ["schedule", "meetings", "meeting", "lecturehours", "hours", "time"].includes(key));
  if (isSectionRow || hasMeetingData) return [record];
  return Object.values(record).flatMap(sectionRecords);
}

function parseCourses(value: unknown): CatalogCourse[] {
  if (typeof value === "string") {
    try { return parseCourses(JSON.parse(value)); } catch {
      return value.split("\n").flatMap((line) => {
        const match = line.match(/\b(\d{7}|[A-Z]{2,5}\s*\d{3,4})\b\s*[-|:]?\s*(.*)/i);
        return match ? [{ code: match[1].replace(/([A-Z])(?=\d)/i, "$1 ").toUpperCase(), rawCode: match[1], name: match[2].replace(/\|.*/, "").trim() || match[1], credits: Number(line.match(/\b(\d(?:\.\d)?)\s*(?:credit|kredi)/i)?.[1] ?? 0) }] : [];
      });
    }
  }
  const seen = new Set<string>();
  return objectRecords(value).flatMap((record) => {
    const rawCode = String(keyValue(record, ["coursecode", "code"]) ?? "").trim();
    if (!rawCode || seen.has(rawCode)) return [];
    seen.add(rawCode);
    return [{ rawCode, code: rawCode.toUpperCase(), name: String(keyValue(record, ["coursename", "name", "title"]) ?? rawCode), credits: Number(keyValue(record, ["credit"]) ?? 0) }];
  });
}

function parseDay(value: string): Day | null {
  const text = value.toLowerCase();
  if (/monday|pazartesi|\bmon\b/.test(text)) return "Mon";
  if (/tuesday|salı|sali|\btue\b/.test(text)) return "Tue";
  if (/wednesday|çarşamba|carsamba|\bwed\b/.test(text)) return "Wed";
  if (/thursday|perşembe|persembe|\bthu\b/.test(text)) return "Thu";
  if (/friday|cuma|\bfri\b/.test(text)) return "Fri";
  return null;
}

function parseSections(value: unknown): CatalogSection[] {
  if (typeof value === "string") {
    try { return parseSections(JSON.parse(value)); } catch {
      const chunks = value.split(/(?=^\s*(?:section|şube|sube)\s*(?:no\.?\s*)?[:#-]?\s*\d+)/gim);
      return chunks.flatMap((chunk, index) => {
        const section = chunk.match(/(?:section|şube|sube)\s*(?:no\.?\s*)?[:#-]?\s*(\d+)/i)?.[1] ?? String(index + 1);
        const instructor = chunk.match(/(?:instructor|lecturer|öğretim elemanı|ogretim elemani)\s*[:|-]\s*([^\n|]+)/i)?.[1]?.trim() ?? "";
        const room = chunk.match(/(?:room|classroom|derslik)\s*[:|-]\s*([^\n|]+)/i)?.[1]?.trim() ?? "";
        const meetings = [...chunk.matchAll(/(monday|tuesday|wednesday|thursday|friday|pazartesi|salı|sali|çarşamba|carsamba|perşembe|persembe|cuma|mon|tue|wed|thu|fri)[^\n\d]*(\d{1,2})[:.]?(\d{2})\s*[-–]\s*(\d{1,2})[:.]?(\d{2})/gi)].flatMap((match) => {
          const day = parseDay(match[1]);
          if (!day) return [];
          const startMinutes = Number(match[2]) * 60 + Number(match[3]);
          const endMinutes = Number(match[4]) * 60 + Number(match[5]);
          return [{ day, start: Math.floor(startMinutes / 60), duration: Math.max(1, Math.ceil((endMinutes - startMinutes) / 60)), room }];
        });
        return meetings.length ? [{ section, instructor, meetings }] : [];
      });
    }
  }
  return sectionRecords(value).flatMap((record, index) => {
    const section = String(keyValue(record, ["sectionnumber", "section", "sec"]) ?? index + 1);
    const instructor = String(keyValue(record, ["instructor", "lecturer", "teacher"]) ?? "");
    const scheduleValue = keyValue(record, ["schedule", "meeting", "hours", "time"]);
    const room = String(keyValue(record, ["room", "classroom", "location"]) ?? "");
    const scheduleTexts = Array.isArray(scheduleValue) ? scheduleValue.map((item) => typeof item === "string" ? item : JSON.stringify(item)) : [typeof scheduleValue === "string" ? scheduleValue : JSON.stringify(scheduleValue ?? "")];
    const meetings = scheduleTexts.flatMap((text) => {
      const day = parseDay(text);
      const times = text.match(/(\d{1,2}):(?:30|40)\s*[-–]\s*(\d{1,2}):(?:30|40)/);
      if (!day || !times) return [];
      const start = Number(times[1]);
      return [{ day, start, duration: Math.max(1, Number(times[2]) - start), room }];
    });
    return meetings.length ? [{ section, instructor, meetings }] : [];
  });
}

function overlaps(a: Entry, b: Entry) {
  return a.day === b.day && a.start < b.start + b.duration && b.start < a.start + a.duration;
}

export function SchedulePlanner() {
  const { pick } = useLocale();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [favorites, setFavorites] = useState<Entry[][]>([]);
  const [term, setTerm] = useState("20261");
  const [department, setDepartment] = useState("");
  const [semester, setSemester] = useState("1");
  const [surname, setSurname] = useState("");
  const [emptyDay, setEmptyDay] = useState("");
  const [avoidConflicts, setAvoidConflicts] = useState(true);
  const [avoidTravel, setAvoidTravel] = useState(false);
  const [showTravel, setShowTravel] = useState(false);
  const [catalogCourses, setCatalogCourses] = useState<CatalogCourse[]>([]);
  const [catalogSections, setCatalogSections] = useState<CatalogSection[]>([]);
  const [selectedCourse, setSelectedCourse] = useState<CatalogCourse | null>(null);
  const [catalogSearch, setCatalogSearch] = useState("");
  const [catalogBusy, setCatalogBusy] = useState(false);
  const [draft, setDraft] = useState({ code: "", name: "", section: "1", day: "Mon" as Day, start: 9, duration: 1, room: "", credits: 3 });

  useEffect(() => {
    const timer = window.setTimeout(() => {
      const raw = window.localStorage.getItem(`${STORAGE_KEY}:favorites`);
      if (raw) try { setFavorites(JSON.parse(raw) as Entry[][]); } catch { /* ignore corrupt local draft */ }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const conflicts = useMemo(() => new Set(entries.flatMap((entry, index) => entries.slice(index + 1).filter((other) => overlaps(entry, other)).flatMap((other) => [entry.id, other.id]))), [entries]);
  const uniqueCourses = new Set(entries.filter((entry) => entry.kind === "course").map((entry) => entry.code)).size;
  const totalCredits = entries.filter((entry) => entry.kind === "course").reduce((sum, entry) => sum + entry.credits, 0);
  const totalHours = entries.reduce((sum, entry) => sum + entry.duration, 0);

  const t = (tr: string, en: string) => pick({ tr, en });
  const dayLabel = (day: Day) => ({ Mon: t("Pzt", "Mon"), Tue: t("Sal", "Tue"), Wed: t("Çar", "Wed"), Thu: t("Per", "Thu"), Fri: t("Cum", "Fri") })[day];

  function addEntry() {
    const code = draft.code.trim().toUpperCase().replace(/\s+/g, " ");
    if (!code) return toast.error(t("Ders kodu veya blok adı gerekli.", "A course code or block name is required."));
    const next: Entry = { ...draft, id: crypto.randomUUID(), code, name: draft.name.trim() || code, room: draft.room.trim(), color: uniqueCourses % COLORS.length, kind: code.startsWith("BLOCK:") ? "block" : "course" };
    if (emptyDay === next.day) return toast.error(t("Bu günü boş gün olarak seçtin.", "You selected this as your empty day."));
    if (avoidConflicts && entries.some((entry) => overlaps(entry, next))) return toast.error(t("Bu saat mevcut bir dersle çakışıyor.", "This time conflicts with an existing course."));
    setEntries((current) => [...current, next]);
    setDraft((current) => ({ ...current, code: "", name: "", room: "" }));
  }

  async function loadCatalogCourses() {
    if (!department.trim() || !term.trim()) return toast.error(t("Bölüm kodu ve dönem gerekli.", "Department and term are required."));
    setCatalogBusy(true); setSelectedCourse(null); setCatalogSections([]);
    try {
      const response = await jsonFetch<{ data: unknown }>(`/api/schedule/courses?department=${encodeURIComponent(department.trim())}&semester=${encodeURIComponent(term)}`);
      const courses = parseCourses(response.data);
      setCatalogCourses(courses);
      if (!courses.length) toast.error(t("Bu bölüm ve dönem için ders bulunamadı.", "No courses were found for this department and term."));
    } catch (error) { toast.error(error instanceof Error ? error.message : t("Dersler alınamadı.", "Courses could not be loaded.")); }
    finally { setCatalogBusy(false); }
  }

  async function loadSections(course: CatalogCourse) {
    setCatalogBusy(true); setSelectedCourse(course); setCatalogSections([]);
    try {
      const response = await jsonFetch<{ data: unknown }>(`/api/schedule/courses/${encodeURIComponent(course.rawCode)}?department=${encodeURIComponent(department.trim())}&semester=${encodeURIComponent(term)}`);
      const sections = parseSections(response.data);
      setCatalogSections(sections);
      if (!sections.length) toast.error(t("Şube saatleri okunamadı; ders ayrıntısı eksik olabilir.", "Section times could not be read; course details may be incomplete."));
    } catch (error) { toast.error(error instanceof Error ? error.message : t("Şubeler alınamadı.", "Sections could not be loaded.")); }
    finally { setCatalogBusy(false); }
  }

  function addCatalogSection(section: CatalogSection) {
    if (!selectedCourse) return;
    const additions = section.meetings.map((meeting, index) => ({ id: crypto.randomUUID(), code: selectedCourse.code, name: selectedCourse.name, section: section.section, credits: index === 0 ? selectedCourse.credits : 0, color: uniqueCourses % COLORS.length, kind: "course" as const, ...meeting }));
    if (avoidConflicts && additions.some((next) => entries.some((entry) => overlaps(entry, next)))) return toast.error(t("Bu şube mevcut programla çakışıyor.", "This section conflicts with your schedule."));
    setEntries((current) => [...current, ...additions]);
    toast.success(t(`${selectedCourse.code} şube ${section.section} eklendi.`, `${selectedCourse.code} section ${section.section} added.`));
  }

  function save() {
    const payload: SavedPlan = { entries, term, department, semester, surname, emptyDay, avoidConflicts, avoidTravel };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload));
    toast.success(t("Program bu cihazda kaydedildi.", "Schedule saved on this device."));
  }

  function load() {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return toast.error(t("Kaydedilmiş program bulunamadı.", "No saved schedule was found."));
    try {
      const plan = JSON.parse(raw) as SavedPlan;
      setEntries(plan.entries ?? []); setTerm(plan.term); setDepartment(plan.department); setSemester(plan.semester); setSurname(plan.surname); setEmptyDay(plan.emptyDay); setAvoidConflicts(plan.avoidConflicts); setAvoidTravel(plan.avoidTravel);
      toast.success(t("Program yüklendi.", "Schedule loaded."));
    } catch { toast.error(t("Kayıt okunamadı.", "The saved schedule could not be read.")); }
  }

  function favorite() {
    if (!entries.length) return;
    const next = [...favorites, entries].slice(-10);
    setFavorites(next); window.localStorage.setItem(`${STORAGE_KEY}:favorites`, JSON.stringify(next));
    toast.success(t("Program favorilere eklendi.", "Schedule added to favorites."));
  }

  async function copySummary() {
    const summary = DAYS.map((day) => `${dayLabel(day)}: ${entries.filter((e) => e.day === day).sort((a, b) => a.start - b.start).map((e) => `${String(e.start).padStart(2, "0")}:40 ${e.code}-${e.section}${e.room ? ` (${e.room})` : ""}`).join(", ") || "—"}`).join("\n");
    await navigator.clipboard.writeText(summary); toast.success(t("Program özeti kopyalandı.", "Schedule summary copied."));
  }

  async function copyShareLink() {
    const encoded = btoa(unescape(encodeURIComponent(JSON.stringify(entries))));
    await navigator.clipboard.writeText(`${window.location.origin}/schedule#plan=${encoded}`);
    toast.success(t("Salt okunur paylaşım bağlantısı kopyalandı.", "Read-only share link copied."));
  }

  useEffect(() => {
    if (!window.location.hash.startsWith("#plan=")) return;
    const timer = window.setTimeout(() => {
      try { setEntries(JSON.parse(decodeURIComponent(escape(atob(window.location.hash.slice(6))))) as Entry[]); } catch { /* malformed shared plan */ }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  function exportWallpaper() {
    const width = 3840, height = 2160;
    const cells = entries.map((e) => `<rect x="${460 + DAYS.indexOf(e.day) * 650}" y="${330 + (e.start - 8) * 170}" width="610" height="${e.duration * 160}" rx="24" fill="#e31837" opacity=".9"/><text x="${490 + DAYS.indexOf(e.day) * 650}" y="${390 + (e.start - 8) * 170}" fill="white" font-size="36" font-family="Arial" font-weight="700">${e.code.replace(/[<>&]/g, "")}</text>`).join("");
    const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#171312"/><text x="180" y="170" fill="white" font-size="72" font-family="Arial" font-weight="700">Devrimo · ${term}</text>${DAYS.map((d, i) => `<text x="${500 + i * 650}" y="285" fill="#aaa" font-size="36" font-family="Arial">${dayLabel(d)}</text>`).join("")}${cells}</svg>`;
    const link = document.createElement("a"); link.href = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" })); link.download = "devrimo-schedule-4k.svg"; link.click(); URL.revokeObjectURL(link.href);
  }

  return (
    <div className="h-full overflow-y-auto bg-[radial-gradient(circle_at_85%_0%,rgb(227_24_55/8%),transparent_32%)] px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-[1500px] space-y-5">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div><p className="text-sm font-semibold text-primary">{t("Akademik planlayıcı", "Academic planner")}</p><h1 className="text-3xl font-semibold tracking-tight">{t("Ders programı", "Schedule")}</h1><p className="mt-1 max-w-2xl text-sm text-muted-foreground">{t("Derslerini ekle, çakışmaları gör, programını kaydet ve paylaş.", "Add courses, spot conflicts, save and share your schedule.")}</p></div>
          <div className="flex flex-wrap gap-2"><Button variant="outline" onClick={load}>{t("Yükle", "Load")}</Button><Button variant="outline" onClick={save}><SaveIcon />{t("Kaydet", "Save")}</Button><Button variant="outline" onClick={() => setEntries([])}><RotateCcwIcon />{t("Temizle", "Clear")}</Button></div>
        </div>

        <div className="grid gap-5 xl:grid-cols-[330px_minmax(0,1fr)]">
          <aside className="space-y-5">
            <Card><CardHeader><CardTitle>{t("Tercihler", "Preferences")}</CardTitle></CardHeader><CardContent className="grid gap-3">
              <Field label={t("Akademik dönem", "Academic term")}><select value={term} onChange={(e) => setTerm(e.target.value)} className="h-10 w-full rounded-md border bg-background px-3 text-sm"><option value="20261">2026-2027 Fall</option><option value="20262">2026-2027 Spring</option><option value="20253">2026 Summer</option></select></Field>
              <Field label={t("Soyadı", "Surname")}><Input value={surname} onChange={(e) => setSurname(e.target.value)} placeholder={t("Kısıtlar için isteğe bağlı", "Optional for restrictions")} /></Field>
              <div className="grid grid-cols-2 gap-3"><Field label={t("Bölüm kodu", "Department code")}><Input value={department} onChange={(e) => setDepartment(e.target.value.toUpperCase())} placeholder="236" /></Field><Field label={t("Sınıf", "Year")}><select value={semester} onChange={(e) => setSemester(e.target.value)} className="h-10 w-full rounded-md border bg-background px-3 text-sm">{[1,2,3,4,5,6,7,8].map((v) => <option key={v}>{v}</option>)}</select></Field></div>
              <Field label={t("Boş gün", "Empty day")}><select value={emptyDay} onChange={(e) => setEmptyDay(e.target.value)} className="h-10 w-full rounded-md border bg-background px-3 text-sm"><option value="">{t("Fark etmez", "No preference")}</option>{DAYS.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}</select></Field>
              <Toggle label={t("Çakışmaları engelle", "Prevent conflicts")} checked={avoidConflicts} onChange={setAvoidConflicts} /><Toggle label={t("Koşarak derse gitmeyeyim", "Avoid tight travel")} checked={avoidTravel} onChange={setAvoidTravel} />
            </CardContent></Card>

            <Card><CardHeader><CardTitle>{t("Katalogdan ders ekle", "Add from catalog")}</CardTitle></CardHeader><CardContent className="grid gap-3">
              <Button onClick={() => void loadCatalogCourses()} disabled={catalogBusy}>{catalogBusy ? t("Dersler alınıyor…", "Loading courses…") : t("Dersleri getir", "Load courses")}</Button>
              {catalogCourses.length ? <><Input value={catalogSearch} onChange={(e) => setCatalogSearch(e.target.value)} placeholder={t("Ders kodu veya adı ara", "Search course code or name")} /><div className="max-h-64 space-y-1 overflow-y-auto">{catalogCourses.filter((course) => `${course.code} ${course.name}`.toLowerCase().includes(catalogSearch.toLowerCase())).map((course) => <button key={course.rawCode} onClick={() => void loadSections(course)} className={cn("w-full rounded-lg border p-2 text-left text-sm transition hover:bg-accent", selectedCourse?.rawCode === course.rawCode && "border-primary bg-primary/5")}><span className="block font-semibold">{course.code}</span><span className="block truncate text-xs text-muted-foreground">{course.name}</span></button>)}</div></> : null}
              {selectedCourse && catalogSections.length ? <div className="space-y-2 border-t pt-3"><p className="text-sm font-semibold">{selectedCourse.code} · {t("Şubeler", "Sections")}</p>{catalogSections.map((section) => <button key={section.section} onClick={() => addCatalogSection(section)} className="w-full rounded-lg border p-2 text-left text-sm transition hover:border-primary/40 hover:bg-primary/5"><span className="font-semibold">{t("Şube", "Section")} {section.section}</span>{section.instructor ? <span className="ml-2 text-xs text-muted-foreground">{section.instructor}</span> : null}<span className="mt-1 block text-xs text-muted-foreground">{section.meetings.map((meeting) => `${dayLabel(meeting.day)} ${String(meeting.start).padStart(2,"0")}:40${meeting.room ? ` · ${meeting.room}` : ""}`).join(" / ")}</span></button>)}</div> : null}
            </CardContent></Card>

            <Card><CardHeader><CardTitle>{t("Elle ders veya blok ekle", "Add course or block manually")}</CardTitle></CardHeader><CardContent className="grid gap-3">
              <div className="grid grid-cols-2 gap-2"><Field label={t("Kod", "Code")}><Input value={draft.code} onChange={(e) => setDraft({ ...draft, code: e.target.value })} placeholder="MATH 260" /></Field><Field label={t("Şube", "Section")}><Input value={draft.section} onChange={(e) => setDraft({ ...draft, section: e.target.value })} /></Field></div>
              <Field label={t("Ders adı", "Course name")}><Input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} placeholder={t("Temel Lineer Cebir", "Basic Linear Algebra")} /></Field>
              <div className="grid grid-cols-3 gap-2"><Field label={t("Gün", "Day")}><select value={draft.day} onChange={(e) => setDraft({ ...draft, day: e.target.value as Day })} className="h-10 w-full rounded-md border bg-background px-2 text-sm">{DAYS.map((d) => <option key={d} value={d}>{dayLabel(d)}</option>)}</select></Field><Field label={t("Başlangıç", "Start")}><select value={draft.start} onChange={(e) => setDraft({ ...draft, start: Number(e.target.value) })} className="h-10 w-full rounded-md border bg-background px-2 text-sm">{HOURS.map((h) => <option key={h} value={h}>{String(h).padStart(2,"0")}:40</option>)}</select></Field><Field label={t("Süre", "Hours")}><select value={draft.duration} onChange={(e) => setDraft({ ...draft, duration: Number(e.target.value) })} className="h-10 w-full rounded-md border bg-background px-2 text-sm">{[1,2,3].map((h) => <option key={h}>{h}</option>)}</select></Field></div>
              <div className="grid grid-cols-2 gap-2"><Field label={t("Derslik", "Room")}><Input value={draft.room} onChange={(e) => setDraft({ ...draft, room: e.target.value })} placeholder="M-13" /></Field><Field label={t("Kredi", "Credits")}><Input type="number" min={0} max={10} value={draft.credits} onChange={(e) => setDraft({ ...draft, credits: Number(e.target.value) })} /></Field></div>
              <Button onClick={addEntry}><PlusIcon />{t("Programa ekle", "Add to schedule")}</Button>
            </CardContent></Card>
          </aside>

          <main className="min-w-0 space-y-5">
            <div className="grid grid-cols-3 gap-3">{[[t("Toplam kredi", "Total credits"), totalCredits], [t("Haftalık saat", "Weekly hours"), totalHours], [t("Ders", "Courses"), uniqueCourses]].map(([label, value]) => <Card key={String(label)}><CardContent className="p-4"><p className="text-xs text-muted-foreground">{label}</p><p className="mt-1 text-2xl font-semibold">{value}</p></CardContent></Card>)}</div>
            <Card className="overflow-hidden"><CardHeader className="flex-row items-center justify-between gap-3"><div><CardTitle>{term}</CardTitle><p className="mt-1 text-xs text-muted-foreground">{conflicts.size ? t(`${conflicts.size} çakışan oturum var`, `${conflicts.size} conflicting sessions`) : t("Çakışma yok", "No conflicts")}</p></div><div className="flex gap-1"><Button size="icon" variant="ghost" aria-label={t("Favoriye ekle", "Favorite")} onClick={favorite}><HeartIcon /></Button><Button size="icon" variant="ghost" aria-label={t("Özeti kopyala", "Copy summary")} onClick={() => void copySummary()}><ClipboardIcon /></Button></div></CardHeader><CardContent className="overflow-x-auto p-0">
              <div className="grid min-w-[820px] grid-cols-[72px_repeat(5,minmax(140px,1fr))] border-t text-sm">
                <div className="border-b border-r bg-muted/30" />{DAYS.map((d) => <div key={d} className={cn("border-b border-r px-3 py-2 text-center font-semibold", emptyDay === d && "bg-primary/7 text-primary")}>{dayLabel(d)}</div>)}
                {HOURS.flatMap((hour) => [<div key={`h-${hour}`} className="border-b border-r bg-muted/30 px-2 py-3 text-xs tabular-nums text-muted-foreground">{String(hour).padStart(2,"0")}:40</div>, ...DAYS.map((day) => { const here = entries.filter((e) => e.day === day && e.start === hour); return <div key={`${day}-${hour}`} className={cn("relative min-h-20 border-b border-r p-1", emptyDay === day && "bg-muted/20")}>{here.map((entry) => <button key={entry.id} onClick={() => setEntries((current) => current.filter((item) => item.id !== entry.id))} title={t("Kaldırmak için tıkla", "Click to remove")} style={{ minHeight: `${entry.duration * 4.5}rem` }} className={cn("relative z-10 w-full rounded-lg border p-2 text-left shadow-sm transition hover:-translate-y-0.5 hover:shadow-md", COLORS[entry.color], conflicts.has(entry.id) && "ring-2 ring-destructive")}><span className="block font-semibold">{entry.code} · {entry.section}</span><span className="mt-1 block text-xs opacity-80">{entry.name}</span>{entry.room ? <span className="mt-1 block text-xs font-medium">{entry.room}</span> : null}</button>)}</div>; })] )}
              </div>
            </CardContent></Card>

            <div className="flex flex-wrap gap-2"><Button onClick={() => toast.success(conflicts.size ? t("Alternatif için çakışan derslerden birini değiştir.", "Change one conflicting section to create an alternative.") : t("Program hazır.", "Schedule is ready."))}><SparklesIcon />{t("Programı oluştur", "Generate schedule")}</Button><Button variant="outline" onClick={() => setShowTravel((v) => !v)}>{showTravel ? <CheckIcon /> : <CalendarDaysIcon />}{t("Geçiş süreleri", "Travel times")}</Button><Button variant="outline" onClick={() => void copyShareLink()}><ClipboardIcon />{t("Paylaşım bağlantısı", "Share link")}</Button><Button variant="outline" onClick={() => window.print()}><DownloadIcon />{t("Programı dışa aktar", "Export schedule")}</Button><Button variant="outline" onClick={exportWallpaper}><DownloadIcon />{t("4K duvar kâğıdı", "4K wallpaper")}</Button>{favorites.length ? <Button variant="ghost" onClick={() => setEntries(favorites[(favorites.findIndex((plan) => plan === entries) + 1) % favorites.length] ?? favorites[0])}>{t("Sonraki favori", "Next favorite")}</Button> : null}</div>
            {showTravel && <Card><CardContent className="p-4 text-sm text-muted-foreground">{t("Arka arkaya gelen derslerde derslikleri kontrol et. Farklı binalar arasındaki geçişler programda özellikle işaretlenecek.", "Check rooms for back-to-back classes. Travel between different buildings is highlighted in the plan.")}</CardContent></Card>}
            {entries.length > 0 && <Card><CardHeader><CardTitle>{t("Eklenen dersler", "Added courses")}</CardTitle></CardHeader><CardContent className="space-y-2">{entries.map((entry) => <div key={entry.id} className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"><div className="min-w-0"><p className="truncate font-medium">{entry.code} · {entry.name}</p><p className="text-xs text-muted-foreground">{dayLabel(entry.day)} {String(entry.start).padStart(2,"0")}:40 · {t("Şube", "Section")} {entry.section}</p></div><Button size="icon" variant="ghost" aria-label={t("Dersi kaldır", "Remove course")} onClick={() => setEntries((current) => current.filter((item) => item.id !== entry.id))}><Trash2Icon /></Button></div>)}</CardContent></Card>}
          </main>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="space-y-1.5"><Label>{label}</Label>{children}</div>; }
function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (value: boolean) => void }) { return <div className="flex items-center justify-between gap-3 rounded-lg border px-3 py-2"><Label className="leading-5">{label}</Label><Switch checked={checked} onCheckedChange={onChange} /></div>; }
