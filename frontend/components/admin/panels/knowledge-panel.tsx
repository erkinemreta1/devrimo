"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BookOpenIcon,
  CpuIcon,
  DatabaseZapIcon,
  EyeIcon,
  ExternalLinkIcon,
  LayersIcon,
  LinkIcon,
  ListChecksIcon,
  PlusIcon,
  RefreshCwIcon,
  RocketIcon,
  SaveIcon,
  SearchIcon,
  SparklesIcon,
  XIcon,
} from "lucide-react";
import { toast } from "sonner";
import { useLocale } from "@/components/locale-provider";
import { EmptyState, ErrorState, PanelHeader, StatusBadge, formatDate } from "@/components/admin/admin-shared";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress, ProgressLabel, ProgressValue } from "@/components/ui/progress";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { adminGet, adminMutate } from "@/lib/admin/client";
import type {
  AdminPrincipal,
  BatchSourceInput,
  CourseGroup,
  EmbeddingSettings,
  IngestionJob,
  KnowledgeSearchResponse,
  KnowledgeSource,
  KnowledgeSourceDetail,
} from "@/lib/admin/types";
import { cn } from "@/lib/utils";

const SOURCE_KINDS = ["drupal", "html_page", "html_table", "rss", "ical", "json", "pdf", "approved_social", "curated"] as const;

function asJsonObject(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : null;
}

function parseJsonObject(value: string): Record<string, unknown> | null {
  try {
    return asJsonObject(JSON.parse(value));
  } catch {
    return null;
  }
}

export function KnowledgePanel({ principal, title, description }: { principal: AdminPrincipal; title: string; description: string }) {
  const { locale, pick } = useLocale();
  const client = useQueryClient();
  const canWrite = principal.permissions.includes("knowledge:write");
  const canWriteGroups = principal.permissions.includes("groups:write");
  const [creating, setCreating] = useState(false);
  const [selected, setSelected] = useState<KnowledgeSource | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [addingGroup, setAddingGroup] = useState(false);
  const sources = useQuery({ queryKey: ["admin", "sources"], queryFn: () => adminGet<{ items: KnowledgeSource[] }>("sources") });
  const groups = useQuery({ queryKey: ["admin", "course-groups"], queryFn: () => adminGet<{ items: CourseGroup[] }>("course-groups") });
  const embedding = useQuery({ queryKey: ["admin", "embedding-settings"], queryFn: () => adminGet<EmbeddingSettings>("embedding-settings"), refetchInterval: 5000 });
  const jobs = useQuery({ queryKey: ["admin", "ingestion-jobs"], queryFn: () => adminGet<{ items: IngestionJob[] }>("ingestion-jobs?limit=20"), refetchInterval: 3000 });
  const refresh = () => void client.invalidateQueries({ queryKey: ["admin"] });
  const installDefaults = useMutation({
    mutationFn: () => adminMutate<{ created: unknown[] }>("source-templates/install-defaults", "POST", {}),
    onSuccess: (data) => {
      toast.success(`${data.created.length} ${pick({ tr: "önerilen taslak eklendi", en: "recommended drafts added" })}`);
      refresh();
    },
    onError: (error) => toast.error(error.message),
  });
  const allSourceIds = sources.data?.items.map((source) => source.id) ?? [];
  const allSelected = allSourceIds.length > 0 && allSourceIds.every((id) => selectedIds.has(id));
  const draftSources = sources.data?.items.filter((s) => s.status !== "published") ?? [];
  const draftCount = draftSources.length;

  function toggleSource(id: string) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  return <>
    <PanelHeader
      title={title}
      description={description}
      actions={<>
        <Button variant="outline" size="sm" onClick={refresh}><RefreshCwIcon />{pick({ tr: "Yenile", en: "Refresh" })}</Button>
        {canWrite ? <>
          <Button variant="outline" size="sm" disabled={installDefaults.isPending} onClick={() => installDefaults.mutate()}><DatabaseZapIcon />{pick({ tr: "ODTÜ taslaklarını ekle", en: "Add METU drafts" })}</Button>
          <Button size="sm" onClick={() => setCreating(true)}><PlusIcon />{pick({ tr: "Kaynak ekle", en: "Add source" })}</Button>
        </> : null}
      </>}
    />
    <div className="space-y-6">
      <EmbeddingPanel settings={embedding.data} jobs={jobs.data?.items ?? []} loading={embedding.isLoading} canWrite={canWrite} onDone={refresh} />
      <KnowledgeSearchLab />

      <section>
        <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
          <div><h2 className="text-lg font-semibold">{pick({ tr: "Kampüs kaynakları", en: "Campus sources" })}</h2><p className="text-sm text-muted-foreground">{pick({ tr: "Birden fazla kaynağı seçerek yayınla veya çalışma ayarlarını topluca değiştir.", en: "Select multiple sources to publish or change shared operating settings in one action." })}</p></div>
          <div className="flex items-center gap-2">
            {canWrite && draftCount > 0 ? (
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setSelectedIds(new Set(draftSources.map((s) => s.id)));
                }}
              >
                <ListChecksIcon className="size-4" />
                {pick({
                  tr: `${draftCount} taslağı seç`,
                  en: `Select ${draftCount} drafts`,
                })}
              </Button>
            ) : null}
            {selectedIds.size ? <Badge variant="secondary">{selectedIds.size} {pick({ tr: "seçili", en: "selected" })}</Badge> : null}
          </div>
        </div>
        {canWrite && selectedIds.size ? <BulkSourceEditor ids={[...selectedIds]} onClear={() => setSelectedIds(new Set())} onDone={() => { setSelectedIds(new Set()); refresh(); }} /> : null}
        {sources.isLoading ? <Skeleton className="h-72 rounded-xl" /> : sources.error ? <ErrorState error={sources.error} retry={() => void sources.refetch()} /> : <Card className="surface-raised border-0 py-0 ring-1 ring-foreground/8"><CardContent className="px-0">{sources.data?.items.length ? <Table><TableHeader className="bg-muted/45"><TableRow>
          {canWrite ? <TableHead className="w-10 pl-4"><input type="checkbox" className="size-4 accent-primary" aria-label={pick({ tr: "Tüm kaynakları seç", en: "Select all sources" })} checked={allSelected} onChange={() => setSelectedIds(allSelected ? new Set() : new Set(allSourceIds))} /></TableHead> : null}
          <TableHead className={canWrite ? "" : "pl-4"}>{pick({ tr: "Kaynak", en: "Source" })}</TableHead><TableHead>{pick({ tr: "Durum", en: "Status" })}</TableHead><TableHead>{pick({ tr: "Kayıtlar", en: "Records" })}</TableHead><TableHead>{pick({ tr: "Son başarı", en: "Last success" })}</TableHead><TableHead className="pr-4 text-right">{pick({ tr: "İşlemler", en: "Actions" })}</TableHead>
        </TableRow></TableHeader><TableBody>{sources.data.items.map((source) => <TableRow key={source.id} data-state={selectedIds.has(source.id) ? "selected" : undefined}>
          {canWrite ? <TableCell className="pl-4"><input type="checkbox" className="size-4 accent-primary" aria-label={`${source.name} selected`} checked={selectedIds.has(source.id)} onChange={() => toggleSource(source.id)} /></TableCell> : null}
          <TableCell className={canWrite ? "" : "pl-4"}><p className="font-medium">{source.name}</p><p className="max-w-96 truncate text-xs text-muted-foreground">{source.url ?? source.kind}</p></TableCell>
          <TableCell><StatusBadge value={source.enabled ? source.status : "disabled"} /></TableCell>
          <TableCell><span className="font-semibold tabular-nums">{source.records ?? 0}</span><span className="ml-2 text-xs text-muted-foreground">· {source.revisions ?? 0} rev</span></TableCell>
          <TableCell className={cn("text-muted-foreground", source.last_error && "text-destructive")}>{source.last_error ? source.last_error : formatDate(source.last_success_at, locale)}</TableCell>
          <TableCell className="pr-4 text-right"><Button variant="ghost" size="sm" onClick={() => setSelected(source)}><EyeIcon />{pick({ tr: "Yönet", en: "Manage" })}</Button></TableCell>
        </TableRow>)}</TableBody></Table> : <EmptyState title={pick({ tr: "Henüz kaynak yok", en: "No sources yet" })} description={pick({ tr: "Akademik takvim, duyurular, etkinlikler ve hizmet durumları için bir kaynak ekleyin.", en: "Add a source for calendars, announcements, events, or service status." })} icon={<DatabaseZapIcon className="size-4" />} />}</CardContent></Card>}
      </section>

      <section>
        <div className="mb-3 flex items-center justify-between"><div><h2 className="text-lg font-semibold">{pick({ tr: "Korumalı ders grupları", en: "Protected course groups" })}</h2><p className="text-sm text-muted-foreground">{pick({ tr: "Bağlantılar dönemden bağımsızdır; yalnızca etkin ve süresi dolmamış gruplar güncel kayıt doğrulamasından sonra gösterilir.", en: "Links are term-independent; only active, unexpired groups are revealed after current enrollment is verified." })}</p></div>{canWriteGroups ? <Button variant="outline" size="sm" onClick={() => setAddingGroup(true)}><LinkIcon />{pick({ tr: "Grup ekle", en: "Add group" })}</Button> : null}</div>
        {groups.isLoading ? <Skeleton className="h-32 rounded-xl" /> : groups.error ? <ErrorState error={groups.error} retry={() => void groups.refetch()} /> : <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{groups.data?.items.map((group) => {
          const available = group.active && (!group.valid_until || new Date(group.valid_until) >= new Date());
          return <Card key={group.id} className="surface-raised border-0 ring-1 ring-foreground/8"><CardHeader><div className="flex items-start justify-between gap-2"><div><CardTitle>{group.course_code}{group.section ? ` · ${group.section}` : ""}</CardTitle><CardDescription>{pick({ tr: "Dönemden bağımsız bağlantı", en: "Term-independent link" })}</CardDescription></div><StatusBadge value={available ? "active" : "expired"} /></div></CardHeader><CardContent><p className="text-xs text-muted-foreground">{group.valid_until ? `${pick({ tr: "Geçerli olduğu tarih", en: "Valid until" })}: ${formatDate(group.valid_until, locale)}` : pick({ tr: "Süre sonu yok", en: "No expiry" })}</p></CardContent></Card>;
        })}{!groups.data?.items.length ? <Card className="md:col-span-2 xl:col-span-3"><EmptyState title={pick({ tr: "Ders grubu yok", en: "No course groups" })} /></Card> : null}</div>}
      </section>
    </div>
    <CreateSourceDialog open={creating} onOpenChange={setCreating} onDone={() => { setCreating(false); refresh(); }} />
    <SourceDialog source={selected} onOpenChange={(open) => !open && setSelected(null)} onDone={refresh} />
    <CreateGroupDialog open={addingGroup} onOpenChange={setAddingGroup} onDone={() => { setAddingGroup(false); refresh(); }} />
  </>;
}

function KnowledgeSearchLab() {
  const { locale, pick } = useLocale();
  const [query, setQuery] = useState("");
  const [limit, setLimit] = useState("10");
  const search = useMutation({
    mutationFn: (value: string) => {
      const params = new URLSearchParams({ q: value, limit });
      return adminGet<KnowledgeSearchResponse>(`knowledge/search?${params.toString()}`);
    },
  });
  const canSearch = query.trim().length > 0 && !search.isPending;

  return <Card className="surface-raised border-0 ring-1 ring-foreground/8">
    <CardHeader className="border-b bg-muted/20">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2"><SearchIcon className="size-4 text-primary" />{pick({ tr: "Arama laboratuvarı", en: "Search lab" })}</CardTitle>
          <CardDescription className="mt-1">{pick({ tr: "Ajanın kullandığı gerçek hibrit aramayı çalıştır ve sıralanmış eşleşmeleri tek skorla incele.", en: "Run the agent's real hybrid retrieval and inspect ranked matches with one combined score." })}</CardDescription>
        </div>
        {search.data?.embedding_model ? <Badge variant="outline">{search.data.embedding_model}</Badge> : null}
      </div>
    </CardHeader>
    <CardContent className="space-y-4">
      <form className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_8rem_auto]" onSubmit={(event) => { event.preventDefault(); if (canSearch) search.mutate(query.trim()); }}>
        <div className="space-y-2"><Label htmlFor="knowledge-debug-query">{pick({ tr: "Sorgu", en: "Query" })}</Label><Input id="knowledge-debug-query" value={query} maxLength={500} onChange={(event) => setQuery(event.target.value)} placeholder={pick({ tr: "Örn. akademik takvim kayıt tarihleri", en: "E.g. academic calendar registration dates" })} /></div>
        <div className="space-y-2"><Label>{pick({ tr: "Sonuç", en: "Results" })}</Label><Select value={limit} onValueChange={(value) => setLimit(value ?? "10")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{[5, 10, 20, 25].map((value) => <SelectItem key={value} value={String(value)}>{value}</SelectItem>)}</SelectContent></Select></div>
        <div className="flex items-end"><Button className="w-full sm:w-auto" type="submit" disabled={!canSearch}><SearchIcon />{search.isPending ? pick({ tr: "Aranıyor", en: "Searching" }) : pick({ tr: "Ara", en: "Search" })}</Button></div>
      </form>

      {search.error ? <div className="rounded-xl border border-destructive/25 bg-destructive/5 p-4 text-sm text-destructive">{search.error.message}</div> : null}
      {search.isPending ? <div className="space-y-3">{Array.from({ length: 3 }).map((_, index) => <Skeleton key={index} className="h-32 rounded-xl" />)}</div> : search.data ? <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground"><span><span className="font-semibold text-foreground">{search.data.count}</span> {pick({ tr: "eşleşme", en: "matches" })}</span><span className="truncate">“{search.data.query}”</span></div>
        {search.data.items.length ? search.data.items.map((item, index) => <div key={item.id} className="rounded-xl border bg-background/55 p-4">
          <div className="flex items-start gap-4">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2"><Badge variant="secondary">#{index + 1}</Badge><Badge variant="outline">{item.source}</Badge><Badge variant="outline">{item.type.replaceAll("_", " ")}</Badge>{item.language ? <Badge variant="outline">{item.language}</Badge> : null}{item.section ? <Badge variant="outline">{item.section}</Badge> : null}{item.chunk_count > 1 ? <Badge variant="outline">{pick({ tr: `parça ${item.chunk_index + 1}/${item.chunk_count}`, en: `chunk ${item.chunk_index + 1}/${item.chunk_count}` })}</Badge> : null}{item.page_number ? <Badge variant="outline">{pick({ tr: `sayfa ${item.page_number}`, en: `page ${item.page_number}` })}</Badge> : null}</div>
              <h3 className="mt-2 font-semibold">{item.title}</h3>
              <p className="mt-1 max-h-24 overflow-hidden whitespace-pre-line text-sm leading-6 text-muted-foreground">{item.summary || item.content}</p>
              <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">{item.source_last_success_at ? <span>{pick({ tr: "Kaynak güncellendi", en: "Source updated" })}: {formatDate(item.source_last_success_at, locale)}</span> : null}{item.url ? <a href={item.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium text-primary hover:underline">{pick({ tr: "Kaynağı aç", en: "Open source" })}<ExternalLinkIcon className="size-3" /></a> : null}</div>
            </div>
            <div className="shrink-0 rounded-xl border bg-muted/25 px-3 py-2 text-right"><p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{pick({ tr: "Skor", en: "Score" })}</p><p className="font-mono text-lg font-semibold tabular-nums">{item.score.toFixed(4)}</p></div>
          </div>
        </div>) : <EmptyState title={pick({ tr: "Eşleşme bulunamadı", en: "No matches found" })} description={pick({ tr: "Sorguyu değiştir veya kaynakların başarıyla işlendiğini kontrol et.", en: "Try another query or check that sources were ingested successfully." })} icon={<SearchIcon className="size-4" />} />}
      </div> : <div className="rounded-xl border border-dashed p-6 text-center text-sm text-muted-foreground"><SearchIcon className="mx-auto mb-2 size-5" />{pick({ tr: "İndeksteki eşleşmeleri görmek için bir sorgu çalıştır.", en: "Run a query to inspect matches in the index." })}</div>}
    </CardContent>
  </Card>;
}

function EmbeddingPanel(props: { settings?: EmbeddingSettings; jobs: IngestionJob[]; loading: boolean; canWrite: boolean; onDone: () => void }) {
  if (props.loading || !props.settings) return <Skeleton className="h-72 rounded-xl" />;
  const settingsKey = [props.settings.provider, props.settings.model, props.settings.base_url, props.settings.dimensions, props.settings.batch_size, props.settings.query_prefix, props.settings.document_prefix, props.settings.has_api_key].join(":");
  return <EmbeddingPanelEditor key={settingsKey} settings={props.settings} jobs={props.jobs} canWrite={props.canWrite} onDone={props.onDone} />;
}

function EmbeddingPanelEditor({ settings, jobs, canWrite, onDone }: { settings: EmbeddingSettings; jobs: IngestionJob[]; canWrite: boolean; onDone: () => void }) {
  const { pick } = useLocale();
  const [provider, setProvider] = useState<EmbeddingSettings["provider"]>(settings.provider);
  const [model, setModel] = useState(settings.model);
  const [baseUrl, setBaseUrl] = useState(settings.base_url ?? "");
  const [dimensions, setDimensions] = useState(String(settings.dimensions));
  const [batchSize, setBatchSize] = useState(String(settings.batch_size));
  const [queryPrefix, setQueryPrefix] = useState(settings.query_prefix);
  const [documentPrefix, setDocumentPrefix] = useState(settings.document_prefix);
  const [apiKey, setApiKey] = useState("");
  const [dirty, setDirty] = useState(false);

  const save = useMutation({
    mutationFn: () => adminMutate<EmbeddingSettings>("embedding-settings", "PUT", {
      provider,
      model,
      base_url: provider === "disabled" ? null : baseUrl,
      dimensions: Number(dimensions),
      batch_size: Number(batchSize),
      query_prefix: queryPrefix,
      document_prefix: documentPrefix,
      api_key: apiKey || null,
    }),
    onSuccess: () => { setApiKey(""); setDirty(false); toast.success(pick({ tr: "Embedding ayarları kaydedildi", en: "Embedding settings saved" })); onDone(); },
    onError: (error) => toast.error(error.message),
  });
  const reindex = useMutation({
    mutationFn: () => adminMutate<{ queued: number }>("embedding/reindex", "POST", {}),
    onSuccess: (data) => { toast.success(`${data.queued} ${pick({ tr: "yeniden embedding işi sıraya alındı", en: "re-embedding jobs queued" })}`); onDone(); },
    onError: (error) => toast.error(error.message),
  });
  const coverage = settings.total_records ? Math.round((settings.current_model_records / settings.total_records) * 100) : 0;
  const recentEmbeddingJobs = jobs.filter((job) => job.kind === "reembed" || job.embedding_provider).slice(0, 6);
  const valid = provider === "disabled" || (model.trim() && baseUrl.trim() && Number(dimensions) > 0 && Number(dimensions) <= 1536 && Number(batchSize) > 0);

  return <Card className="surface-raised border-0 ring-1 ring-foreground/8">
    <CardHeader className="border-b bg-muted/20"><div className="flex flex-wrap items-start justify-between gap-3"><div><CardTitle className="flex items-center gap-2"><CpuIcon className="size-4 text-primary" />{pick({ tr: "Embedding çalışma zamanı", en: "Embedding runtime" })}</CardTitle><CardDescription className="mt-1">{pick({ tr: "Yerel OpenAI uyumlu bir uç nokta veya uzak sağlayıcı seç; API anahtarı şifreli saklanır.", en: "Choose a local OpenAI-compatible endpoint or a remote provider; API keys are stored encrypted." })}</CardDescription></div><div className="flex gap-2"><Badge variant="outline">{settings?.provider ?? "disabled"}</Badge>{settings?.active_jobs ? <Badge variant="secondary">{settings.active_jobs} {pick({ tr: "aktif iş", en: "active jobs" })}</Badge> : null}</div></div></CardHeader>
    <CardContent className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
        <div className="space-y-2"><Label>{pick({ tr: "Sağlayıcı", en: "Provider" })}</Label><Select value={provider} disabled={!canWrite} onValueChange={(value) => { const next = (value ?? "disabled") as EmbeddingSettings["provider"]; if (next === "local" && (provider === "disabled" || baseUrl.includes("api.openai.com"))) { setBaseUrl("http://host.docker.internal:11434/v1"); setModel("nomic-embed-text"); setDimensions("768"); } if (next === "remote" && (provider === "disabled" || baseUrl.includes("host.docker.internal"))) { setBaseUrl("https://api.openai.com/v1"); setModel("text-embedding-3-small"); setDimensions("1536"); } setProvider(next); setDirty(true); }}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="disabled">{pick({ tr: "Kapalı", en: "Disabled" })}</SelectItem><SelectItem value="local">{pick({ tr: "Yerel uç nokta", en: "Local endpoint" })}</SelectItem><SelectItem value="remote">{pick({ tr: "Uzak sağlayıcı", en: "Remote provider" })}</SelectItem></SelectContent></Select></div>
        <div className="space-y-2"><Label>{pick({ tr: "Model", en: "Model" })}</Label><Input value={model} disabled={!canWrite || provider === "disabled"} onChange={(event) => { setModel(event.target.value); setDirty(true); }} /></div>
        <div className="space-y-2 lg:col-span-2"><Label>{pick({ tr: "Uç nokta", en: "Endpoint" })}</Label><Input value={baseUrl} disabled={!canWrite || provider === "disabled"} onChange={(event) => { setBaseUrl(event.target.value); setDirty(true); }} placeholder={provider === "local" ? "http://host.docker.internal:11434/v1" : "https://api.openai.com/v1"} /></div>
        <div className="space-y-2"><Label>{pick({ tr: "Boyut", en: "Dimensions" })}</Label><Input type="number" min={1} max={1536} value={dimensions} disabled={!canWrite || provider === "disabled"} onChange={(event) => { setDimensions(event.target.value); setDirty(true); }} /></div>
        <div className="space-y-2"><Label>{pick({ tr: "Paket boyutu", en: "Batch size" })}</Label><Input type="number" min={1} max={128} value={batchSize} disabled={!canWrite || provider === "disabled"} onChange={(event) => { setBatchSize(event.target.value); setDirty(true); }} /></div>
        <div className="space-y-2 sm:col-span-2"><Label>{pick({ tr: "Sorgu ön eki", en: "Query prefix" })}</Label><Input value={queryPrefix} disabled={!canWrite || provider === "disabled"} onChange={(event) => { setQueryPrefix(event.target.value); setDirty(true); }} placeholder="query: " /><p className="text-xs text-muted-foreground">{pick({ tr: "Arama sorgusunun önüne eklenir. Sadece sorguları etkiler, mevcut vektörler geçerli kalır.", en: "Prepended to search queries only; stored vectors stay valid." })}</p></div>
        <div className="space-y-2 sm:col-span-2 lg:col-span-3"><Label>{pick({ tr: "Belge ön eki", en: "Document prefix" })}</Label><Input value={documentPrefix} disabled={!canWrite || provider === "disabled"} onChange={(event) => { setDocumentPrefix(event.target.value); setDirty(true); }} placeholder="passage: " /><p className={documentPrefix === settings.document_prefix ? "text-xs text-muted-foreground" : "text-xs text-amber-600 dark:text-amber-500"}>{documentPrefix === settings.document_prefix ? pick({ tr: "Depolanan metinlerin önüne eklenir; asimetrik modeller bunu bekler.", en: "Prepended to stored passages; asymmetric models expect it." }) : pick({ tr: "Bu ön eki değiştirmek mevcut vektörleri geçersiz kılar; kaydettikten sonra yeniden işlemelisin.", en: "Changing this retires the stored vectors; re-embed after saving." })}</p></div>
        {provider === "remote" ? <div className="space-y-2 sm:col-span-2"><Label>{pick({ tr: "API anahtarı", en: "API key" })}</Label><Input type="password" value={apiKey} disabled={!canWrite} onChange={(event) => { setApiKey(event.target.value); setDirty(true); }} placeholder={settings?.has_api_key ? pick({ tr: "Kayıtlı anahtarı korumak için boş bırak", en: "Leave blank to keep the stored key" }) : pick({ tr: "Gerekli", en: "Required" })} /></div> : null}
        <div className="flex items-end gap-2 sm:col-span-2 lg:col-span-3"><Button disabled={!canWrite || !dirty || !valid || save.isPending} onClick={() => save.mutate()}><SaveIcon />{pick({ tr: "Ayarları kaydet", en: "Save settings" })}</Button><Button variant="outline" disabled={!canWrite || provider === "disabled" || reindex.isPending} onClick={() => reindex.mutate()}><RefreshCwIcon />{pick({ tr: "Mevcut kayıtları yeniden işle", en: "Re-embed existing records" })}</Button></div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl border bg-background/55 p-4"><p className="text-xs text-muted-foreground">{pick({ tr: "Geçerli model kapsamı", en: "Current model coverage" })}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{coverage}%</p><p className="text-xs text-muted-foreground">{settings?.current_model_records ?? 0} / {settings?.total_records ?? 0}</p></div>
        <div className="rounded-xl border bg-background/55 p-4"><p className="text-xs text-muted-foreground">{pick({ tr: "Herhangi bir embedding", en: "Any embedding" })}</p><p className="mt-1 text-2xl font-semibold tabular-nums">{settings?.embedded_records ?? 0}</p><p className="text-xs text-muted-foreground">{pick({ tr: "güncel kayıt", en: "current records" })}</p></div>
        <div className="rounded-xl border bg-background/55 p-4"><p className="text-xs text-muted-foreground">{pick({ tr: "Yapılandırma kaynağı", en: "Configuration source" })}</p><p className="mt-1 font-semibold">{settings?.has_database_override ? pick({ tr: "Yönetici ayarı", en: "Admin override" }) : pick({ tr: "Ortam varsayılanı", en: "Environment default" })}</p><p className="truncate text-xs text-muted-foreground">{settings?.model_label ?? pick({ tr: "Embedding kapalı", en: "Embeddings disabled" })}</p></div>
      </div>

      <div>
        <div className="mb-2 flex items-center gap-2"><ListChecksIcon className="size-4 text-primary" /><h3 className="font-semibold">{pick({ tr: "Embedding işlemleri", en: "Embedding activity" })}</h3></div>
        {recentEmbeddingJobs.length ? <div className="space-y-2">{recentEmbeddingJobs.map((job) => {
          const percent = job.total_records ? Math.round((job.processed_records / job.total_records) * 100) : job.status === "completed" ? 100 : 0;
          return <div key={job.id} className="rounded-xl border bg-background/55 p-3"><div className="mb-2 flex flex-wrap items-center justify-between gap-2"><div><span className="font-medium">{job.source_name}</span><span className="ml-2 text-xs text-muted-foreground">{job.kind} · {job.phase}</span></div><StatusBadge value={job.status} /></div><Progress value={percent}><ProgressLabel>{job.embedding_provider ? `${job.embedding_provider} · ${job.embedded_records} embedded` : job.phase}</ProgressLabel><ProgressValue>{() => `${percent}%`}</ProgressValue></Progress>{job.error_detail ? <p className="mt-2 text-xs text-destructive">{job.error_detail}</p> : null}</div>;
        })}</div> : <div className="rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">{pick({ tr: "Henüz embedding işlemi yok.", en: "No embedding activity yet." })}</div>}
      </div>
    </CardContent>
  </Card>;
}

function BulkSourceEditor({ ids, onClear, onDone }: { ids: string[]; onClear: () => void; onDone: () => void }) {
  const { pick } = useLocale();
  const [enabled, setEnabled] = useState("unchanged");
  const [language, setLanguage] = useState("unchanged");
  const [authority, setAuthority] = useState("");
  const [scheduleMinutes, setScheduleMinutes] = useState("");
  const changes = useMemo(() => ({
    ...(enabled !== "unchanged" ? { enabled: enabled === "enabled" } : {}),
    ...(language !== "unchanged" ? { language } : {}),
    ...(authority !== "" ? { authority: Number(authority) } : {}),
    ...(scheduleMinutes !== "" ? { schedule_seconds: Number(scheduleMinutes) * 60 } : {}),
  }), [authority, enabled, language, scheduleMinutes]);
  const updateMutation = useMutation({
    mutationFn: () => adminMutate<{ updated: number }>("sources/bulk", "PUT", { source_ids: ids, changes }),
    onSuccess: (data) => { toast.success(`${data.updated} ${pick({ tr: "kaynak güncellendi", en: "sources updated" })}`); onDone(); },
    onError: (error) => toast.error(error.message),
  });
  const publishMutation = useMutation({
    mutationFn: () => adminMutate<{ count: number; published: unknown[]; failed: { reason: string }[] }>("sources/batch/publish", "POST", { source_ids: ids }),
    onSuccess: (data) => {
      if (data.count > 0) {
        toast.success(`${data.count} ${pick({ tr: "kaynak yayınlandı ve içe aktarma sıraya alındı", en: "sources published and ingestion queued" })}`);
      }
      if (data.failed && data.failed.length > 0) {
        toast.error(`${data.failed.length} ${pick({ tr: "kaynak yayınlanamadı", en: "sources failed to publish" })}: ${data.failed[0].reason}`);
      }
      onDone();
    },
    onError: (error) => toast.error(error.message),
  });
  return (
    <Card className="mb-3 border-primary/20 bg-primary/[0.035]">
      <CardContent className="space-y-3 pt-4">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-primary/10 pb-3">
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="font-semibold">
              {ids.length} {pick({ tr: "kaynak seçildi", en: "sources selected" })}
            </Badge>
            <span className="text-xs text-muted-foreground">
              {pick({
                tr: "Toplu yayınlama geçerli taslakları yayına alır ve hemen veri çekme işlemini sıraya koyar.",
                en: "Batch publishing publishes valid drafts and immediately queues ingestion.",
              })}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="default"
              size="sm"
              disabled={publishMutation.isPending}
              onClick={() => publishMutation.mutate()}
            >
              <RocketIcon className="size-4" />
              {pick({
                tr: `Seçilenleri Yayınla (${ids.length})`,
                en: `Publish Selected (${ids.length})`,
              })}
            </Button>
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onClear}
              aria-label={pick({ tr: "Seçimi temizle", en: "Clear selection" })}
            >
              <XIcon />
            </Button>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1fr_1fr_8rem_10rem_auto]">
          <div className="space-y-2">
            <Label>{pick({ tr: "Çalışma durumu", en: "Operating state" })}</Label>
            <Select value={enabled} onValueChange={(value) => setEnabled(value ?? "unchanged")}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="unchanged">{pick({ tr: "Değiştirme", en: "No change" })}</SelectItem>
                <SelectItem value="enabled">{pick({ tr: "Etkinleştir", en: "Enable" })}</SelectItem>
                <SelectItem value="disabled">{pick({ tr: "Devre dışı bırak", en: "Disable" })}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{pick({ tr: "Dil", en: "Language" })}</Label>
            <Select value={language} onValueChange={(value) => setLanguage(value ?? "unchanged")}
            ><SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="unchanged">{pick({ tr: "Değiştirme", en: "No change" })}</SelectItem>
              <SelectItem value="tr">Türkçe</SelectItem>
              <SelectItem value="en">English</SelectItem>
            </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label>{pick({ tr: "Yetki", en: "Authority" })}</Label>
            <Input type="number" min={0} max={100} value={authority} onChange={(event) => setAuthority(event.target.value)} placeholder="—" />
          </div>
          <div className="space-y-2">
            <Label>{pick({ tr: "Yenileme (dk)", en: "Refresh (min)" })}</Label>
            <Input type="number" min={5} value={scheduleMinutes} onChange={(event) => setScheduleMinutes(event.target.value)} placeholder="—" />
          </div>
          <div className="flex items-end">
            <Button
              variant="outline"
              disabled={!Object.keys(changes).length || updateMutation.isPending}
              onClick={() => updateMutation.mutate()}
            >
              <SaveIcon />
              {pick({ tr: "Ayarları Kaydet", en: "Save Settings" })}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

const SAMPLE_BATCH_TEMPLATES = [
  {
    name: "METU Kafeterya Yemek Menüsü",
    kind: "drupal",
    url: "https://kafeterya.metu.edu.tr",
    language: "tr",
    authority: 95,
    schedule_seconds: 10800,
    config: {
      item_selector: ".views-row, article",
      defaults: { record_type: "announcement" },
    },
  },
  {
    name: "METU Kütüphane Çalışma Saatleri",
    kind: "drupal",
    url: "https://lib.metu.edu.tr/tr",
    language: "tr",
    authority: 95,
    schedule_seconds: 21600,
    config: {
      item_selector: ".views-row, article",
      defaults: { record_type: "service_status" },
    },
  },
  {
    name: "METU Sağlık ve Rehberlik Merkezi (SRM)",
    kind: "drupal",
    url: "https://srm.metu.edu.tr/tr",
    language: "tr",
    authority: 90,
    schedule_seconds: 86400,
    config: {
      item_selector: "article, .views-row",
      defaults: { record_type: "guide" },
    },
  },
  {
    name: "METU Uluslararası İşbirliği Ofisi (ICO)",
    kind: "drupal",
    url: "https://ico.metu.edu.tr",
    language: "en",
    authority: 95,
    schedule_seconds: 21600,
    config: {
      item_selector: "article, .views-row",
      defaults: { record_type: "announcement" },
    },
  },
];

function CreateSourceDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (open: boolean) => void; onDone: () => void }) {
  const { pick } = useLocale();
  const [mode, setMode] = useState<"single" | "batch">("single");

  // Single mode state
  const [name, setName] = useState("");
  const [kind, setKind] = useState<(typeof SOURCE_KINDS)[number]>("drupal");
  const [url, setUrl] = useState("");
  const [recordType, setRecordType] = useState("announcement");
  const [config, setConfig] = useState("{}");
  const parsedConfig = parseJsonObject(config);

  // Batch mode state
  const [batchJson, setBatchJson] = useState("");
  const batchParsed = (() => {
    if (!batchJson.trim()) return { items: [] as BatchSourceInput[], error: null };
    try {
      const parsed: unknown = JSON.parse(batchJson);
      if (!Array.isArray(parsed)) {
        return { items: [] as BatchSourceInput[], error: pick({ tr: "Girdi bir JSON dizisi [...] olmalıdır.", en: "Input must be a JSON array [...]." }) };
      }
      if (parsed.length === 0) {
        return { items: [] as BatchSourceInput[], error: pick({ tr: "En az 1 kaynak gereklidir.", en: "At least 1 source is required." }) };
      }
      if (parsed.length > 100) {
        return { items: [] as BatchSourceInput[], error: pick({ tr: "Tek seferde en fazla 100 kaynak eklenebilir.", en: "Maximum 100 sources per batch." }) };
      }
      const items: BatchSourceInput[] = [];
      for (let i = 0; i < parsed.length; i++) {
        const item = asJsonObject(parsed[i]);
        if (!item) {
          return { items: [] as BatchSourceInput[], error: `#${i + 1} ${pick({ tr: "kaynak geçerli bir nesne değil.", en: "source is not a valid object." })}` };
        }
        if (!item.name || typeof item.name !== "string" || item.name.trim().length < 2) {
          return { items: [] as BatchSourceInput[], error: `#${i + 1} ${pick({ tr: "kaynağın geçerli bir adı olmalı (min 2 karakter).", en: "source must have a valid name (min 2 chars)." })}` };
        }
        if (typeof item.kind !== "string" || !SOURCE_KINDS.includes(item.kind as (typeof SOURCE_KINDS)[number])) {
          return { items: [] as BatchSourceInput[], error: `#${i + 1} ${pick({ tr: "kaynağın geçerli bir türü olmalı.", en: "source must have a valid kind." })}` };
        }
        items.push(item as BatchSourceInput);
      }
      return { items, error: null };
    } catch (err) {
      return { items: [] as BatchSourceInput[], error: err instanceof Error ? err.message : "Invalid JSON" };
    }
  })();

  const singleMutation = useMutation({
    mutationFn: () => {
      if (!parsedConfig) throw new Error("Configuration must be a JSON object");
      const defaults = asJsonObject(parsedConfig.defaults) ?? {};
      return adminMutate("sources", "POST", {
        name,
        kind,
        url: url || null,
        language: "tr",
        authority: 70,
        audience: {},
        schedule_seconds: 3600,
        config: { ...parsedConfig, defaults: { ...defaults, record_type: recordType } },
      });
    },
    onSuccess: () => {
      toast.success(pick({ tr: "Taslak kaynak oluşturuldu", en: "Draft source created" }));
      setName("");
      setUrl("");
      setConfig("{}");
      onDone();
    },
    onError: (error) => toast.error(error.message),
  });

  const batchMutation = useMutation({
    mutationFn: () => {
      if (batchParsed.error || !batchParsed.items.length) {
        throw new Error(batchParsed.error ?? "No valid sources");
      }
      return adminMutate<{ count: number; items: unknown[] }>("sources/batch", "POST", {
        items: batchParsed.items,
      });
    },
    onSuccess: (data) => {
      toast.success(
        `${data.count} ${pick({
          tr: "taslak kaynak topluca oluşturuldu",
          en: "draft sources created in batch",
        })}`
      );
      setBatchJson("");
      onDone();
    },
    onError: (error) => toast.error(error.message),
  });

  const validConfig = parsedConfig !== null;
  const isBatchValid = !batchParsed.error && batchParsed.items.length > 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-3xl max-h-[88vh] flex flex-col p-0 overflow-hidden">
        <DialogHeader className="p-6 pb-2 shrink-0">
          <DialogTitle>{pick({ tr: "Kampüs kaynağı ekle", en: "Add campus source" })}</DialogTitle>
          <DialogDescription>
            {pick({
              tr: "Kaynaklar taslak olarak kaydedilir; önizleme ve yayınlama ayrı adımlardır.",
              en: "Sources are saved as drafts; preview and publish are separate steps.",
            })}
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2 border-b px-6 pb-3 shrink-0">
          <Button
            type="button"
            variant={mode === "single" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("single")}
          >
            {pick({ tr: "Tek Kaynak", en: "Single Source" })}
          </Button>
          <Button
            type="button"
            variant={mode === "batch" ? "default" : "outline"}
            size="sm"
            onClick={() => setMode("batch")}
          >
            <LayersIcon className="size-4" />
            {pick({ tr: "Toplu Ekle (JSON)", en: "Batch Import (JSON)" })}
          </Button>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-4">
          {mode === "single" ? (
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>{pick({ tr: "Ad", en: "Name" })}</Label>
                <Input value={name} onChange={(event) => setName(event.target.value)} />
              </div>
              <div className="space-y-2">
                <Label>{pick({ tr: "Kaynak türü", en: "Source type" })}</Label>
                <Select value={kind} onValueChange={(value) => setKind((value ?? "drupal") as typeof kind)}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {SOURCE_KINDS.map((value) => (
                      <SelectItem key={value} value={value}>{value.replaceAll("_", " ")}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label>URL</Label>
                <Input value={url} onChange={(event) => setUrl(event.target.value)} placeholder="https://…" />
              </div>
              <div className="space-y-2">
                <Label>{pick({ tr: "İçerik türü", en: "Content type" })}</Label>
                <Select value={recordType} onValueChange={(value) => setRecordType(value ?? "announcement")}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["announcement", "calendar", "event", "service_status", "guide", "course", "policy"].map((value) => (
                      <SelectItem key={value} value={value}>{value.replaceAll("_", " ")}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2 sm:col-span-2">
                <Label>{pick({ tr: "Gelişmiş çıkarma ayarları", en: "Advanced extraction settings" })}</Label>
                <Textarea className="min-h-28 font-mono text-xs" value={config} onChange={(event) => setConfig(event.target.value)} />
                <p className={cn("text-xs text-muted-foreground", !validConfig && "text-destructive")}>
                  {validConfig
                    ? pick({ tr: "Seçiciler ve alan eşlemeleri için isteğe bağlı JSON nesnesi.", en: "Optional JSON object for selectors and field mappings." })
                    : pick({ tr: "Geçerli bir JSON nesnesi gerekli.", en: "A valid JSON object is required." })}
                </p>
              </div>
            </div>
          ) : (
            <div className="space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label>{pick({ tr: "JSON Kaynak Dizisi", en: "JSON Source Array" })}</Label>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setBatchJson(JSON.stringify(SAMPLE_BATCH_TEMPLATES, null, 2))}
                  >
                    <SparklesIcon className="size-3.5 text-primary" />
                    {pick({ tr: "Örnek şablonları yükle", en: "Load sample templates" })}
                  </Button>
                  {batchJson ? (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setBatchJson("")}
                    >
                      {pick({ tr: "Temizle", en: "Clear" })}
                    </Button>
                  ) : null}
                </div>
              </div>

              <Textarea
                className="h-64 min-h-[14rem] max-h-[42vh] w-full resize-y font-mono text-xs leading-relaxed"
                value={batchJson}
                onChange={(event) => setBatchJson(event.target.value)}
                placeholder={`[\n  {\n    "name": "METU Cafeteria",\n    "kind": "drupal",\n    "url": "https://kafeterya.metu.edu.tr",\n    "authority": 95,\n    "config": { ... }\n  }\n]`}
              />

              <div className="flex items-center justify-between text-xs">
                {batchParsed.error ? (
                  <p className="text-destructive font-medium">{batchParsed.error}</p>
                ) : isBatchValid ? (
                  <p className="text-primary font-medium">
                    ✓ {batchParsed.items.length} {pick({ tr: "kaynak algılandı ve hazır", en: "sources detected and ready" })}
                  </p>
                ) : (
                  <p className="text-muted-foreground">
                    {pick({ tr: "Kaynak nesnelerinden oluşan bir JSON dizisi girin.", en: "Enter a JSON array of source objects." })}
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        <DialogFooter className="p-4 px-6 border-t bg-muted/20 shrink-0">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {pick({ tr: "Vazgeç", en: "Cancel" })}
          </Button>
          {mode === "single" ? (
            <Button
              disabled={name.trim().length < 2 || !validConfig || singleMutation.isPending}
              onClick={() => singleMutation.mutate()}
            >
              {pick({ tr: "Taslağı oluştur", en: "Create draft" })}
            </Button>
          ) : (
            <Button
              disabled={!isBatchValid || batchMutation.isPending}
              onClick={() => batchMutation.mutate()}
            >
              <LayersIcon className="size-4" />
              {batchParsed.items.length > 0
                ? `${batchParsed.items.length} ${pick({ tr: "Taslağı Toplu Oluştur", en: "Drafts Batch Create" })}`
                : pick({ tr: "Toplu Oluştur", en: "Batch Create" })}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function SourceDialog({ source, onOpenChange, onDone }: { source: KnowledgeSource | null; onOpenChange: (open: boolean) => void; onDone: () => void }) {
  const { pick } = useLocale();
  const query = useQuery({ queryKey: ["admin", "source", source?.id], queryFn: () => adminGet<KnowledgeSourceDetail>(`sources/${source!.id}`), enabled: Boolean(source) });
  const revision = query.data?.revision_history[0];
  const preview = useMutation({ mutationFn: () => adminMutate<{ count: number }>(`sources/${source!.id}/revisions/${revision!.id}/preview`, "POST", {}), onSuccess: (data) => toast.success(`${data.count} ${pick({ tr: "kayıt önizlendi", en: "records previewed" })}`), onError: (error) => toast.error(error.message) });
  const publish = useMutation({ mutationFn: () => adminMutate(`sources/${source!.id}/revisions/${revision!.id}/publish`, "POST", {}), onSuccess: () => { toast.success(pick({ tr: "Kaynak yayınlandı ve içe aktarma sıraya alındı", en: "Source published and ingestion queued" })); onDone(); void query.refetch(); }, onError: (error) => toast.error(error.message) });
  const ingest = useMutation({ mutationFn: () => adminMutate(`sources/${source!.id}/ingest`, "POST", {}), onSuccess: () => { toast.success(pick({ tr: "Yenileme sıraya alındı", en: "Refresh queued" })); onDone(); }, onError: (error) => toast.error(error.message) });
  return <Dialog open={Boolean(source)} onOpenChange={onOpenChange}><DialogContent className="sm:max-w-2xl"><DialogHeader><DialogTitle>{source?.name}</DialogTitle><DialogDescription>{source?.url ?? source?.kind}</DialogDescription></DialogHeader>{query.isLoading ? <Skeleton className="h-52" /> : revision ? <div className="space-y-4"><div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl border bg-muted/25 p-3"><p className="text-xs text-muted-foreground">{pick({ tr: "Son revizyon", en: "Latest revision" })}</p><p className="mt-1 font-semibold">#{revision.revision}</p></div><div className="rounded-xl border bg-muted/25 p-3"><p className="text-xs text-muted-foreground">{pick({ tr: "Doğrulama", en: "Validation" })}</p><div className="mt-1"><StatusBadge value={revision.validation.ok ? "success" : "failed"} /></div></div><div className="rounded-xl border bg-muted/25 p-3"><p className="text-xs text-muted-foreground">{pick({ tr: "Durum", en: "Status" })}</p><div className="mt-1"><StatusBadge value={revision.status} /></div></div></div>{revision.validation.errors.length ? <div className="rounded-xl border border-destructive/25 bg-destructive/5 p-3 text-sm text-destructive">{revision.validation.errors.join(" · ")}</div> : null}<pre className="max-h-48 overflow-auto rounded-xl border bg-muted/25 p-3 text-xs">{JSON.stringify(revision.config, null, 2)}</pre></div> : <EmptyState title={pick({ tr: "Revizyon bulunamadı", en: "No revision found" })} />}<DialogFooter className="flex-wrap"><Button variant="outline" disabled={!revision || preview.isPending} onClick={() => preview.mutate()}><EyeIcon />{pick({ tr: "Önizle", en: "Preview" })}</Button><Button variant="outline" disabled={!source?.active_revision_id || ingest.isPending} onClick={() => ingest.mutate()}><RefreshCwIcon />{pick({ tr: "Şimdi yenile", en: "Refresh now" })}</Button><Button disabled={!revision?.validation.ok || publish.isPending} onClick={() => publish.mutate()}><RocketIcon />{pick({ tr: "Yayınla", en: "Publish" })}</Button></DialogFooter></DialogContent></Dialog>;
}

function CreateGroupDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (open: boolean) => void; onDone: () => void }) {
  const { pick } = useLocale();
  const [course, setCourse] = useState("");
  const [section, setSection] = useState("");
  const [url, setUrl] = useState("");
  const [validUntil, setValidUntil] = useState("");
  const mutation = useMutation({
    mutationFn: () => adminMutate("course-groups", "POST", { course_code: course, section: section || null, invite_url: url, eligibility: {}, valid_until: validUntil ? new Date(validUntil).toISOString() : null }),
    onSuccess: () => { toast.success(pick({ tr: "Korumalı grup eklendi", en: "Protected group added" })); setCourse(""); setSection(""); setUrl(""); setValidUntil(""); onDone(); },
    onError: (error) => toast.error(error.message),
  });
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>{pick({ tr: "Ders grubu ekle", en: "Add course group" })}</DialogTitle><DialogDescription>{pick({ tr: "Bağlantı şifrelenir, arama dizinine eklenmez ve dönemden bağımsız olarak güncel kayıtla doğrulanır.", en: "The link is encrypted, never indexed, and verified against current enrollment without storing a term." })}</DialogDescription></DialogHeader><div className="grid gap-4 sm:grid-cols-2"><div className="space-y-2"><Label>{pick({ tr: "Ders kodu", en: "Course code" })}</Label><Input value={course} onChange={(event) => setCourse(event.target.value)} placeholder="CENG213" /></div><div className="space-y-2"><Label>{pick({ tr: "Şube (isteğe bağlı)", en: "Section (optional)" })}</Label><Input value={section} onChange={(event) => setSection(event.target.value)} /></div><div className="space-y-2 sm:col-span-2"><Label>{pick({ tr: "WhatsApp davet bağlantısı", en: "WhatsApp invite link" })}</Label><Input value={url} onChange={(event) => setUrl(event.target.value)} type="url" /></div><div className="space-y-2 sm:col-span-2"><Label>{pick({ tr: "Geçerlilik sonu (isteğe bağlı)", en: "Expires at (optional)" })}</Label><Input type="datetime-local" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} /></div></div><DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>{pick({ tr: "Vazgeç", en: "Cancel" })}</Button><Button disabled={course.length < 2 || url.length < 10 || mutation.isPending} onClick={() => mutation.mutate()}><BookOpenIcon />{pick({ tr: "Grubu ekle", en: "Add group" })}</Button></DialogFooter></DialogContent></Dialog>;
}
