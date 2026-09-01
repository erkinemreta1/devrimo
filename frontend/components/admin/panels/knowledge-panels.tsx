"use client";

import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { DatabaseIcon, EyeIcon, PlayIcon, PlusIcon, RefreshCwIcon, SaveIcon, Trash2Icon, TriangleAlertIcon } from "lucide-react";
import { toast } from "sonner";
import { useLocale } from "@/components/locale-provider";
import { Detail, EmptyState, ErrorState, LoadingCards, PanelHeader, StatusBadge, formatDate } from "@/components/admin/admin-shared";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { adminGet, adminMutate } from "@/lib/admin/client";
import type {
  CampusSource,
  CampusSourceList,
  CampusSourcePreview,
  CampusSourceRun,
  CuratedEntry,
  GradePolicy,
  KnowledgeOverview,
} from "@/lib/admin/types";
import { cn } from "@/lib/utils";

const BLANK: SourceForm = {
  slug: "",
  name: "",
  adapter: "drupal_listing",
  kind: "announcement",
  base_url: "https://",
  configText: JSON.stringify(
    { listings: { tr: "/tr/announcements", en: "/en/announcements" }, item_pattern: "^/(tr|en)/(duyurular|announcements)/[^/]+$" },
    null,
    2,
  ),
  audienceText: "{}",
  encoding: "",
  languages: ["tr", "en"],
  departmentsText: "",
  refresh_seconds: 10800,
  max_pages: 2,
  max_items: 100,
  priority: 100,
  enabled: true,
};

type SourceForm = {
  slug: string;
  name: string;
  adapter: string;
  kind: string;
  base_url: string;
  configText: string;
  audienceText: string;
  encoding: string;
  languages: string[];
  departmentsText: string;
  refresh_seconds: number;
  max_pages: number;
  max_items: number;
  priority: number;
  enabled: boolean;
};

function toForm(source: CampusSource): SourceForm {
  return {
    slug: source.slug,
    name: source.name,
    adapter: source.adapter,
    kind: source.kind,
    base_url: source.base_url,
    configText: JSON.stringify(source.config ?? {}, null, 2),
    audienceText: JSON.stringify(source.audience_rules ?? {}, null, 2),
    encoding: source.encoding ?? "",
    languages: source.languages?.length ? source.languages : ["tr"],
    departmentsText: (source.departments ?? []).join(", "),
    refresh_seconds: source.refresh_seconds,
    max_pages: source.max_pages,
    max_items: source.max_items,
    priority: source.priority,
    enabled: source.enabled,
  };
}

function parseJson(text: string): Record<string, unknown> | null {
  try {
    const value = JSON.parse(text || "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function toBody(form: SourceForm, reason: string) {
  return {
    slug: form.slug.trim(),
    name: form.name.trim(),
    adapter: form.adapter,
    kind: form.kind,
    base_url: form.base_url.trim(),
    config: parseJson(form.configText) ?? {},
    audience_rules: parseJson(form.audienceText) ?? {},
    encoding: form.encoding.trim() || null,
    languages: form.languages,
    departments: form.departmentsText.split(",").map((value) => value.trim()).filter(Boolean),
    degree_levels: [],
    refresh_seconds: form.refresh_seconds,
    max_pages: form.max_pages,
    max_items: form.max_items,
    priority: form.priority,
    enabled: form.enabled,
    reason: reason.trim(),
  };
}

export function KnowledgePanel({ title, description }: { title: string; description: string }) {
  const { pick } = useLocale();
  const sources = useQuery({ queryKey: ["admin", "sources"], queryFn: () => adminGet<CampusSourceList>("sources") });
  const overview = useQuery({ queryKey: ["admin", "knowledge"], queryFn: () => adminGet<KnowledgeOverview>("knowledge") });
  const [editing, setEditing] = useState<CampusSource | "new" | null>(null);
  const [runsFor, setRunsFor] = useState<CampusSource | null>(null);

  if (sources.isLoading) return <><PanelHeader title={title} description={description} /><LoadingCards /></>;
  if (sources.error) return <><PanelHeader title={title} description={description} /><ErrorState error={sources.error as Error} retry={() => void sources.refetch()} /></>;

  const data = sources.data!;
  return (
    <>
      <PanelHeader title={title} description={description} />
      {overview.data && !overview.data.configured ? (
        <Card className="surface-raised mb-4 border-0 ring-1 ring-amber-500/25">
          <CardContent className="flex items-start gap-3 py-4 text-sm">
            <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-amber-500" />
            <p className="text-muted-foreground">
              {pick({
                tr: "Gömme (embedding) yapılandırılmadığı için kampüs bilgi tabanı arama yapamaz. Kaynaklar yine de ayrıştırılır ve önizlenebilir; belgeler yalnızca yapılandırma tamamlandığında saklanır.",
                en: "No embedding is configured, so the campus knowledge base cannot be searched. Sources still parse and preview; documents are stored only once it is configured.",
              })}
            </p>
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
        <Card className="surface-raised border-0 ring-1 ring-foreground/8">
          <CardHeader className="border-b">
            <div className="flex items-start justify-between gap-3">
              <div>
                <CardTitle>{pick({ tr: "Kampüs kaynakları", en: "Campus sources" })}</CardTitle>
                <CardDescription className="mt-1">
                  {pick({
                    tr: "Her kaynak bir satırdır. Yeni bir bölüm eklemek kod değil yapılandırma işidir — kaydetmeden önce Önizle ile ayrıştığını doğrulayın.",
                    en: "Each source is a row. Adding a department is configuration, not code — use Preview to confirm it parses before saving.",
                  })}
                </CardDescription>
              </div>
              {data.editable ? (
                <Button size="sm" onClick={() => setEditing("new")}>
                  <PlusIcon />
                  {pick({ tr: "Kaynak ekle", en: "Add source" })}
                </Button>
              ) : null}
            </div>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.sources.length === 0 ? (
              <EmptyState title={pick({ tr: "Kaynak yok", en: "No sources" })} />
            ) : (
              data.sources.map((source) => (
                <SourceRow
                  key={source.id}
                  source={source}
                  list={data}
                  onEdit={() => setEditing(source)}
                  onRuns={() => setRunsFor(source)}
                />
              ))
            )}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <KnowledgeCard overview={overview.data} loading={overview.isLoading} />
          <CuratedCard />
        </div>
      </div>

      {editing ? (
        <SourceDialog
          source={editing === "new" ? null : editing}
          adapters={data.adapters}
          kinds={data.kinds}
          onClose={() => setEditing(null)}
        />
      ) : null}
      {runsFor ? <RunsDialog source={runsFor} onClose={() => setRunsFor(null)} /> : null}
    </>
  );
}

function SourceRow({ source, list, onEdit, onRuns }: { source: CampusSource; list: CampusSourceList; onEdit: () => void; onRuns: () => void }) {
  const { locale, pick } = useLocale();
  const client = useQueryClient();
  const run = useMutation({
    mutationFn: () => adminMutate<{ status: string; items_seen: number; error: string | null }>(`sources/${source.id}/run`, "POST", {}),
    onSuccess: (result) => {
      if (result.status === "failed") toast.error(result.error ?? pick({ tr: "Kaynak başarısız oldu", en: "The source failed" }));
      else toast.success(pick({ tr: `${result.items_seen} öğe ayrıştırıldı`, en: `Parsed ${result.items_seen} items` }));
      void client.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <div className={cn("rounded-xl border p-3", !source.enabled && "opacity-60")}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="truncate font-medium">{source.name}</span>
            <Badge variant="outline" className="font-mono text-[11px]">{source.adapter}</Badge>
            <Badge variant="outline" className="text-[11px]">{source.kind}</Badge>
            {source.departments.length ? <Badge className="text-[11px]">{source.departments.join(", ")}</Badge> : null}
            {source.last_status ? <StatusBadge value={source.last_status} /> : null}
          </div>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{source.base_url}</p>
          {source.last_error ? <p className="mt-1 line-clamp-2 text-xs text-destructive">{source.last_error}</p> : null}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button variant="ghost" size="sm" onClick={onRuns}>
            <EyeIcon />
            {pick({ tr: "Çalışmalar", en: "Runs" })}
          </Button>
          {list.runnable ? (
            <Button variant="outline" size="sm" disabled={run.isPending} onClick={() => run.mutate()}>
              <PlayIcon />
              {run.isPending ? pick({ tr: "Çalışıyor…", en: "Running…" }) : pick({ tr: "Şimdi çalıştır", en: "Run now" })}
            </Button>
          ) : null}
          {list.editable ? <Button variant="outline" size="sm" onClick={onEdit}>{pick({ tr: "Düzenle", en: "Edit" })}</Button> : null}
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
        <span>{pick({ tr: "Belgeler", en: "Documents" })}: {source.documents}</span>
        <span>{pick({ tr: "Yenileme", en: "Refresh" })}: {Math.round(source.refresh_seconds / 60)}m</span>
        <span>{pick({ tr: "Diller", en: "Languages" })}: {source.languages.join(", ")}</span>
        <span>{pick({ tr: "Son çalışma", en: "Last run" })}: {formatDate(source.last_run_at, locale)}</span>
      </div>
    </div>
  );
}

function SourceDialog({ source, adapters, kinds, onClose }: { source: CampusSource | null; adapters: string[]; kinds: string[]; onClose: () => void }) {
  const { pick } = useLocale();
  const client = useQueryClient();
  const [form, setForm] = useState<SourceForm>(source ? toForm(source) : BLANK);
  const [reason, setReason] = useState("");
  const [preview, setPreview] = useState<CampusSourcePreview | null>(null);

  const configValid = parseJson(form.configText) !== null && parseJson(form.audienceText) !== null;
  const valid = configValid && form.slug.trim().length >= 2 && form.name.trim().length >= 2 && form.base_url.startsWith("http");

  const previewMutation = useMutation({
    mutationFn: () => adminMutate<CampusSourcePreview>("sources/preview", "POST", { ...toBody(form, "preview"), limit: 8 }),
    onSuccess: setPreview,
    onError: (error: Error) => toast.error(error.message),
  });
  const saveMutation = useMutation({
    mutationFn: () =>
      source
        ? adminMutate<CampusSource>(`sources/${source.id}`, "PUT", toBody(form, reason))
        : adminMutate<CampusSource>("sources", "POST", toBody(form, reason)),
    onSuccess: () => {
      toast.success(pick({ tr: "Kaynak kaydedildi", en: "Source saved" }));
      void client.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
    onError: (error: Error) => toast.error(error.message),
  });
  const deleteMutation = useMutation({
    mutationFn: () => adminMutate(`sources/${source!.id}`, "DELETE", { reason: reason.trim() }),
    onSuccess: () => {
      toast.success(pick({ tr: "Kaynak silindi", en: "Source deleted" }));
      void client.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Dialog open onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-h-[90vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{source ? pick({ tr: "Kaynağı düzenle", en: "Edit source" }) : pick({ tr: "Kaynak ekle", en: "Add source" })}</DialogTitle>
          <DialogDescription>
            {pick({
              tr: "Ayrıştırma yapılandırması adaptöre aittir ve ham JSON olarak düzenlenir. Kaydetmeden önce Önizle.",
              en: "Parsing configuration belongs to the adapter and is edited as raw JSON. Preview before you save.",
            })}
          </DialogDescription>
        </DialogHeader>

        <form
          className="space-y-4"
          onSubmit={(event: FormEvent) => {
            event.preventDefault();
            saveMutation.mutate();
          }}
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="source-slug">{pick({ tr: "Kısa ad", en: "Slug" })}</Label>
              <Input id="source-slug" value={form.slug} onChange={(event) => setForm({ ...form, slug: event.target.value })} placeholder="psy-announcements" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-name">{pick({ tr: "Ad", en: "Name" })}</Label>
              <Input id="source-name" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} />
            </div>
            <div className="space-y-2 sm:col-span-2">
              <Label htmlFor="source-url">{pick({ tr: "Temel adres", en: "Base URL" })}</Label>
              <Input id="source-url" value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} />
            </div>
            <div className="space-y-2">
              <Label>{pick({ tr: "Adaptör", en: "Adapter" })}</Label>
              <Select value={form.adapter} onValueChange={(value) => setForm({ ...form, adapter: value ?? form.adapter })}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{adapters.map((adapter) => <SelectItem key={adapter} value={adapter}>{adapter}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>{pick({ tr: "Tür", en: "Kind" })}</Label>
              <Select value={form.kind} onValueChange={(value) => setForm({ ...form, kind: value ?? form.kind })}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>{kinds.map((kind) => <SelectItem key={kind} value={kind}>{kind}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-departments">{pick({ tr: "Bölümler (virgülle)", en: "Departments (comma separated)" })}</Label>
              <Input id="source-departments" value={form.departmentsText} onChange={(event) => setForm({ ...form, departmentsText: event.target.value })} placeholder="CENG" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-encoding">{pick({ tr: "Kodlama (isteğe bağlı)", en: "Encoding (optional)" })}</Label>
              <Input id="source-encoding" value={form.encoding} onChange={(event) => setForm({ ...form, encoding: event.target.value })} placeholder="iso8859-9" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-refresh">{pick({ tr: "Yenileme (sn)", en: "Refresh (s)" })}</Label>
              <Input id="source-refresh" type="number" min={60} value={form.refresh_seconds} onChange={(event) => setForm({ ...form, refresh_seconds: Number(event.target.value) })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-pages">{pick({ tr: "En fazla sayfa", en: "Max pages" })}</Label>
              <Input id="source-pages" type="number" min={1} max={50} value={form.max_pages} onChange={(event) => setForm({ ...form, max_pages: Number(event.target.value) })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="source-items">{pick({ tr: "En fazla öğe", en: "Max items" })}</Label>
              <Input id="source-items" type="number" min={1} max={1000} value={form.max_items} onChange={(event) => setForm({ ...form, max_items: Number(event.target.value) })} />
            </div>
            <label className="flex items-center justify-between gap-3 rounded-xl border bg-muted/25 p-3 sm:col-span-2">
              <span className="text-sm font-medium">{pick({ tr: "Etkin", en: "Enabled" })}</span>
              <Switch checked={form.enabled} onCheckedChange={(checked) => setForm({ ...form, enabled: checked })} />
            </label>
          </div>

          <div className="space-y-2">
            <Label htmlFor="source-config">{pick({ tr: "Adaptör yapılandırması (JSON)", en: "Adapter configuration (JSON)" })}</Label>
            <Textarea id="source-config" className="min-h-40 font-mono text-xs" value={form.configText} onChange={(event) => setForm({ ...form, configText: event.target.value })} />
            {parseJson(form.configText) === null ? <p className="text-xs text-destructive">{pick({ tr: "Geçersiz JSON", en: "Invalid JSON" })}</p> : null}
          </div>

          <div className="space-y-2">
            <Label htmlFor="source-audience">{pick({ tr: "Hedef kitle kuralları (JSON)", en: "Audience rules (JSON)" })}</Label>
            <Textarea id="source-audience" className="min-h-24 font-mono text-xs" value={form.audienceText} onChange={(event) => setForm({ ...form, audienceText: event.target.value })} />
            <p className="text-xs text-muted-foreground">
              {pick({
                tr: "Örnek: {\"lisansüstü\": \"degree_level:graduate\"} — akademik takvimde hedef kitle sütun değil düz metin olduğu için etiketleme burada yapılır.",
                en: 'Example: {"lisansüstü": "degree_level:graduate"} — the calendar states its audience in prose rather than a column, so tagging happens here.',
              })}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" disabled={!configValid || previewMutation.isPending} onClick={() => previewMutation.mutate()}>
              <EyeIcon />
              {previewMutation.isPending ? pick({ tr: "Önizleniyor…", en: "Previewing…" }) : pick({ tr: "Önizle", en: "Preview" })}
            </Button>
            {preview ? (
              <span className={cn("text-xs", preview.ok ? "text-muted-foreground" : "text-destructive")}>
                {preview.ok
                  ? pick({ tr: `${preview.items_seen} öğe · ${preview.duration_ms}ms`, en: `${preview.items_seen} items · ${preview.duration_ms}ms` })
                  : preview.error}
              </span>
            ) : null}
          </div>

          {preview?.items?.length ? (
            <div className="max-h-56 space-y-1 overflow-y-auto rounded-xl border bg-muted/20 p-2">
              {preview.items.map((item, index) => (
                <div key={`${item.url}-${index}`} className="rounded-lg bg-background/70 p-2 text-xs">
                  <p className="font-medium">{item.title || "—"}</p>
                  <p className="truncate font-mono text-[11px] text-muted-foreground">{item.url}</p>
                  <p className="mt-1 line-clamp-2 text-muted-foreground">{item.body_preview}</p>
                </div>
              ))}
            </div>
          ) : null}

          <div className="space-y-2">
            <Label htmlFor="source-reason">{pick({ tr: "Değişiklik gerekçesi", en: "Change reason" })}</Label>
            <Textarea id="source-reason" value={reason} onChange={(event) => setReason(event.target.value)} />
          </div>

          <DialogFooter className="gap-2">
            {source ? (
              <Button type="button" variant="destructive" disabled={reason.trim().length < 3 || deleteMutation.isPending} onClick={() => deleteMutation.mutate()}>
                <Trash2Icon />
                {pick({ tr: "Sil", en: "Delete" })}
              </Button>
            ) : null}
            <Button type="button" variant="ghost" onClick={onClose}>{pick({ tr: "Vazgeç", en: "Cancel" })}</Button>
            <Button type="submit" disabled={!valid || reason.trim().length < 3 || saveMutation.isPending}>
              <SaveIcon />
              {saveMutation.isPending ? pick({ tr: "Kaydediliyor…", en: "Saving…" }) : pick({ tr: "Kaydet", en: "Save" })}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function RunsDialog({ source, onClose }: { source: CampusSource; onClose: () => void }) {
  const { locale, pick } = useLocale();
  const query = useQuery({ queryKey: ["admin", "sources", source.id, "runs"], queryFn: () => adminGet<{ runs: CampusSourceRun[] }>(`sources/${source.id}/runs`) });
  return (
    <Dialog open onOpenChange={(open) => (!open ? onClose() : undefined)}>
      <DialogContent className="max-h-[80vh] max-w-2xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{source.name}</DialogTitle>
          <DialogDescription>
            {pick({
              tr: "Her deneme kaydedilir. Sıfır öğe ayrıştıran bir kaynak, sessiz bir haftadan ayırt edilemez olmasın diye başarısızlık sayılır.",
              en: "Every attempt is recorded. A source that parses zero items counts as a failure, so it is not mistaken for a quiet week.",
            })}
          </DialogDescription>
        </DialogHeader>
        {query.isLoading ? (
          <Skeleton className="h-40 rounded-xl" />
        ) : query.data?.runs.length ? (
          <div className="space-y-2">
            {query.data.runs.map((run) => (
              <div key={run.id} className="rounded-xl border p-3 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <StatusBadge value={run.status} />
                  <span className="text-muted-foreground">{formatDate(run.started_at, locale)}</span>
                </div>
                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                  <span>{pick({ tr: "görülen", en: "seen" })}: {run.items_seen}</span>
                  <span>{pick({ tr: "yazılan", en: "written" })}: {run.items_written}</span>
                  <span>{pick({ tr: "değişmeyen", en: "unchanged" })}: {run.items_unchanged}</span>
                  <span>{pick({ tr: "istek", en: "requests" })}: {run.requests_made}</span>
                  <span>{run.duration_ms}ms</span>
                </div>
                {run.error ? <p className="mt-1 text-destructive">{run.error}</p> : null}
              </div>
            ))}
          </div>
        ) : (
          <EmptyState title={pick({ tr: "Henüz çalışma yok", en: "No runs yet" })} />
        )}
      </DialogContent>
    </Dialog>
  );
}

function KnowledgeCard({ overview, loading }: { overview: KnowledgeOverview | undefined; loading: boolean }) {
  const { pick } = useLocale();
  const client = useQueryClient();
  const [reason, setReason] = useState("");
  const reindex = useMutation({
    mutationFn: () => adminMutate<{ documents_removed: number }>("knowledge/reindex", "POST", { reason: reason.trim() }),
    onSuccess: (result) => {
      toast.success(pick({ tr: `${result.documents_removed} belge silindi; kaynaklar yeniden taranacak`, en: `${result.documents_removed} documents removed; sources will re-crawl` }));
      setReason("");
      void client.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (loading) return <Skeleton className="h-56 rounded-xl" />;
  if (!overview) return null;

  return (
    <Card className="surface-raised border-0 ring-1 ring-foreground/8">
      <CardHeader className="border-b">
        <CardTitle className="flex items-center gap-2"><DatabaseIcon className="size-4" />{pick({ tr: "Bilgi tabanı", en: "Knowledge base" })}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Detail label={pick({ tr: "Durum", en: "Status" })}>{overview.configured ? pick({ tr: "Yapılandırıldı", en: "Configured" }) : pick({ tr: "Yapılandırılmadı", en: "Not configured" })}</Detail>
        <Detail label={pick({ tr: "Belge", en: "Documents" })}>{overview.documents_total}</Detail>
        <Detail label={pick({ tr: "Gömme modeli", en: "Embedding model" })}>{overview.embedding_model}</Detail>
        <Detail label={pick({ tr: "Boyut", en: "Dimensions" })}>{overview.embedding_dimensions}</Detail>
        {overview.can_manage ? (
          <div className="space-y-2 border-t pt-3">
            <p className="text-xs leading-5 text-muted-foreground">
              {pick({
                tr: "Gömme modeli veya boyutu değişirse saklı vektörler geçersizdir; yeniden dizinleme gerekir.",
                en: "Changing the embedding model or dimension invalidates the stored vectors; a reindex is required.",
              })}
            </p>
            <Textarea placeholder={pick({ tr: "Gerekçe", en: "Reason" })} value={reason} onChange={(event) => setReason(event.target.value)} className="min-h-16" />
            <Button variant="outline" size="sm" className="w-full" disabled={reason.trim().length < 3 || reindex.isPending} onClick={() => reindex.mutate()}>
              <RefreshCwIcon />
              {reindex.isPending ? pick({ tr: "Yeniden dizinleniyor…", en: "Reindexing…" }) : pick({ tr: "Yeniden dizinle", en: "Reindex" })}
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CuratedCard() {
  const { pick } = useLocale();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "curated"], queryFn: () => adminGet<{ entries: CuratedEntry[]; editable: boolean }>("curated") });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ kind: "whatsapp_group", entry_key: "", title: "", body: "", url: "", reason: "" });

  const create = useMutation({
    mutationFn: () =>
      adminMutate<CuratedEntry>("curated", "POST", {
        kind: form.kind,
        entry_key: form.entry_key.trim() || null,
        title: form.title.trim(),
        body: form.body,
        url: form.url.trim() || null,
        language: "tr",
        departments: [],
        degree_levels: [],
        tags: [],
        enabled: true,
        reason: form.reason.trim(),
      }),
    onSuccess: () => {
      toast.success(pick({ tr: "Kayıt eklendi", en: "Entry added" }));
      setOpen(false);
      setForm({ kind: "whatsapp_group", entry_key: "", title: "", body: "", url: "", reason: "" });
      void client.invalidateQueries({ queryKey: ["admin", "curated"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  return (
    <Card className="surface-raised border-0 ring-1 ring-foreground/8">
      <CardHeader className="border-b">
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle>{pick({ tr: "Elle girilen kayıtlar", en: "Curated entries" })}</CardTitle>
            <CardDescription className="mt-1">
              {pick({ tr: "Hiçbir sayfada bulunmayan bilgiler: ders WhatsApp grupları, topluluklar, etkinlikler.", en: "Knowledge no page carries: course WhatsApp groups, clubs, events." })}
            </CardDescription>
          </div>
          {query.data?.editable ? <Button size="sm" variant="outline" onClick={() => setOpen(true)}><PlusIcon /></Button> : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {query.isLoading ? (
          <Skeleton className="h-24 rounded-xl" />
        ) : query.data?.entries.length ? (
          query.data.entries.map((entry) => (
            <div key={entry.id} className="rounded-lg border p-2 text-xs">
              <div className="flex items-center gap-2">
                <Badge variant="outline" className="text-[10px]">{entry.kind}</Badge>
                {entry.entry_key ? <span className="font-mono">{entry.entry_key}</span> : null}
              </div>
              <p className="mt-1 truncate font-medium">{entry.title}</p>
            </div>
          ))
        ) : (
          <EmptyState title={pick({ tr: "Kayıt yok", en: "No entries" })} />
        )}
      </CardContent>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{pick({ tr: "Kayıt ekle", en: "Add entry" })}</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-2">
              <Label>{pick({ tr: "Tür", en: "Kind" })}</Label>
              <Select value={form.kind} onValueChange={(value) => setForm({ ...form, kind: value ?? form.kind })}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="whatsapp_group">whatsapp_group</SelectItem>
                  <SelectItem value="club">club</SelectItem>
                  <SelectItem value="event">event</SelectItem>
                  <SelectItem value="note">note</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="curated-key">{pick({ tr: "Anahtar (ör. ders kodu)", en: "Key (e.g. course code)" })}</Label>
              <Input id="curated-key" value={form.entry_key} onChange={(event) => setForm({ ...form, entry_key: event.target.value })} placeholder="CENG315" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="curated-title">{pick({ tr: "Başlık", en: "Title" })}</Label>
              <Input id="curated-title" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="curated-url">URL</Label>
              <Input id="curated-url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} placeholder="https://chat.whatsapp.com/…" />
            </div>
            <div className="space-y-2">
              <Label htmlFor="curated-body">{pick({ tr: "Açıklama", en: "Body" })}</Label>
              <Textarea id="curated-body" value={form.body} onChange={(event) => setForm({ ...form, body: event.target.value })} />
            </div>
            <div className="space-y-2">
              <Label htmlFor="curated-reason">{pick({ tr: "Gerekçe", en: "Reason" })}</Label>
              <Textarea id="curated-reason" value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>{pick({ tr: "Vazgeç", en: "Cancel" })}</Button>
            <Button disabled={form.title.trim().length < 2 || form.reason.trim().length < 3 || create.isPending} onClick={() => create.mutate()}>
              {pick({ tr: "Ekle", en: "Add" })}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

/** METU's grade scale, shown beside the agent defaults it feeds. */
export function GradePolicyCard() {
  const { pick } = useLocale();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "grade-policy"], queryFn: () => adminGet<GradePolicy>("grade-policy") });
  const [scaleText, setScaleText] = useState<string | null>(null);
  const [reason, setReason] = useState("");

  const policy = query.data;
  const text = scaleText ?? (policy ? JSON.stringify(policy.scale, null, 2) : "");
  const scaleValid = parseJson(text) !== null;

  const mutation = useMutation({
    mutationFn: () =>
      adminMutate<GradePolicy>("grade-policy", "PUT", {
        scale: parseJson(text) ?? {},
        non_graded: policy!.non_graded,
        passing_grades: policy!.passing_grades,
        weight_basis: policy!.weight_basis,
        retake_replaces: policy!.retake_replaces,
        max_credits_per_semester: policy!.max_credits_per_semester,
        notes: policy!.notes,
        reason: reason.trim(),
      }),
    onSuccess: () => {
      toast.success(pick({ tr: "Not politikası güncellendi", en: "Grading policy updated" }));
      setScaleText(null);
      setReason("");
      void client.invalidateQueries({ queryKey: ["admin"] });
    },
    onError: (error: Error) => toast.error(error.message),
  });

  if (query.isLoading) return <Skeleton className="h-64 rounded-xl" />;
  if (!policy) return null;

  return (
    <Card className="surface-raised border-0 ring-1 ring-foreground/8">
      <CardHeader className="border-b">
        <CardTitle>{pick({ tr: "Not politikası", en: "Grading policy" })}</CardTitle>
        <CardDescription className="mt-1">
          {pick({
            tr: "Harf–puan karşılıkları ve ağırlıklandırma yönetmelikle belirlenir; dönem planlayıcı bunları kullanır. Kaydetmek yerleşik ajanları yeniler.",
            en: "The letter scale and weighting are set by regulation and the semester planner uses them. Saving rebuilds resident agents.",
          })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <Detail label={pick({ tr: "Ağırlık", en: "Weight basis" })}>{policy.weight_basis}</Detail>
        <Detail label={pick({ tr: "Tekrar notu değiştirir", en: "Retake replaces" })}>{policy.retake_replaces ? pick({ tr: "Evet", en: "Yes" }) : pick({ tr: "Hayır", en: "No" })}</Detail>
        <Detail label={pick({ tr: "Revizyon", en: "Revision" })}>{policy.revision}</Detail>
        <div className="space-y-2">
          <Label htmlFor="grade-scale">{pick({ tr: "Harf ölçeği (JSON)", en: "Letter scale (JSON)" })}</Label>
          <Textarea id="grade-scale" className="min-h-32 font-mono text-xs" value={text} disabled={!policy.editable} onChange={(event) => setScaleText(event.target.value)} />
          {!scaleValid ? <p className="text-xs text-destructive">{pick({ tr: "Geçersiz JSON", en: "Invalid JSON" })}</p> : null}
        </div>
        {policy.editable ? (
          <>
            <Textarea placeholder={pick({ tr: "Gerekçe", en: "Reason" })} value={reason} onChange={(event) => setReason(event.target.value)} className="min-h-16" />
            <Button size="sm" className="w-full" disabled={!scaleValid || reason.trim().length < 3 || mutation.isPending} onClick={() => mutation.mutate()}>
              <SaveIcon />
              {mutation.isPending ? pick({ tr: "Kaydediliyor…", en: "Saving…" }) : pick({ tr: "Politikayı kaydet", en: "Save policy" })}
            </Button>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
