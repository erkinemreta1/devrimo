"use client";

import { useMemo, useState, type FormEvent } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ActivityIcon,
  BotIcon,
  Building2Icon,
  CheckCircle2Icon,
  ChevronRightIcon,
  ClipboardListIcon,
  ExternalLinkIcon,
  GaugeIcon,
  MenuIcon,
  RefreshCwIcon,
  SearchIcon,
  Settings2Icon,
  ShieldCheckIcon,
  SlidersHorizontalIcon,
  TriangleAlertIcon,
  UserCogIcon,
  UsersIcon,
} from "lucide-react";
import { toast } from "sonner";
import { useLocale } from "@/components/locale-provider";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { adminGet, adminMutate } from "@/lib/admin/client";
import type { AdminPrincipal, AdminUser, AgentRow, Overview, RuntimeSettings } from "@/lib/admin/types";

type Section = "overview" | "users" | "agents" | "integrations" | "audit" | "access" | "runtime" | "system";
type Copy = { tr: string; en: string };

type AdminUserDetail = {
  status: string;
  last_seen_at: string | null;
  agent: { status: string } | null;
  sessions: { count: number };
  campus: { connected: boolean; enabled_tools: string[] };
};

type SystemHealth = {
  broker: string;
  database: string;
  posthog: string;
  posthog_dashboard_url: string | null;
  supabase_admin: string;
  agent_runtime: string;
  resident_agents: number;
  pool_capacity: number;
  checked_at: string;
};

const NAV: Array<{ id: Section; label: Copy; icon: typeof GaugeIcon; permission: string }> = [
  { id: "overview", label: { tr: "Genel bakış", en: "Overview" }, icon: GaugeIcon, permission: "overview:read" },
  { id: "users", label: { tr: "Kullanıcılar", en: "Users" }, icon: UsersIcon, permission: "users:read" },
  { id: "agents", label: { tr: "Ajanlar", en: "Agents" }, icon: BotIcon, permission: "agents:read" },
  { id: "integrations", label: { tr: "Entegrasyonlar", en: "Integrations" }, icon: Building2Icon, permission: "integrations:read" },
  { id: "audit", label: { tr: "Denetim kaydı", en: "Audit log" }, icon: ClipboardListIcon, permission: "audit:read" },
  { id: "access", label: { tr: "Yönetici erişimi", en: "Admin access" }, icon: UserCogIcon, permission: "memberships:manage" },
  { id: "runtime", label: { tr: "Ajan varsayılanları", en: "Agent defaults" }, icon: SlidersHorizontalIcon, permission: "runtime:read" },
  { id: "system", label: { tr: "Sistem", en: "System" }, icon: ActivityIcon, permission: "system:read" },
];

function formatDate(value: string | null | undefined) {
  return value ? new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function StatusBadge({ value }: { value: string | null }) {
  const bad = value === "error" || value === "suspended" || value === "deletion_pending" || value === "failed";
  const good = value === "active" || value === "running" || value === "success" || value === "ok";
  return <Badge variant={bad ? "destructive" : good ? "secondary" : "outline"}>{value?.replaceAll("_", " ") ?? "—"}</Badge>;
}

function LoadingCards() {
  return <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-28 rounded-xl" />)}</div>;
}

function ErrorState({ error, retry }: { error: Error; retry: () => void }) {
  const { pick } = useLocale();
  return (
    <Card className="border-destructive/30">
      <CardContent className="flex items-center justify-between gap-4">
        <div><p className="font-medium text-destructive">{pick({ tr: "Bu bölüm yüklenemedi", en: "This section could not load" })}</p><p className="text-muted-foreground">{error.message}</p></div>
        <Button variant="outline" onClick={retry}><RefreshCwIcon />{pick({ tr: "Yeniden dene", en: "Retry" })}</Button>
      </CardContent>
    </Card>
  );
}

export function AdminDashboard({ principal }: { principal: AdminPrincipal }) {
  const { pick } = useLocale();
  const [section, setSection] = useState<Section>("overview");
  const [navQuery, setNavQuery] = useState("");
  const available = useMemo(
    () => NAV.filter((item) => principal.permissions.includes(item.permission) && pick(item.label).toLowerCase().includes(navQuery.toLowerCase())),
    [navQuery, pick, principal.permissions],
  );
  const active = NAV.find((item) => item.id === section) ?? NAV[0];

  return (
    <main className="campus-grid flex min-h-0 flex-1 bg-background">
      <aside className="hidden w-64 shrink-0 border-r bg-sidebar/90 p-3 backdrop-blur-xl lg:block">
        <div className="mb-4 rounded-xl border bg-card/80 p-3">
          <div className="flex items-center gap-2 font-semibold"><ShieldCheckIcon className="size-4 text-primary" />{pick({ tr: "Yönetim merkezi", en: "Admin center" })}</div>
          <p className="mt-1 text-xs text-muted-foreground">METU · {principal.role.replaceAll("_", " ")}</p>
        </div>
        <div className="relative mb-2"><SearchIcon className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" /><Input value={navQuery} onChange={(event) => setNavQuery(event.target.value)} placeholder={pick({ tr: "Bölüm ara…", en: "Find a section…" })} className="pl-8" /></div>
        <nav className="space-y-1" aria-label={pick({ tr: "Yönetim bölümleri", en: "Admin sections" })}>
          {available.map((item) => <NavButton key={item.id} item={item} active={section === item.id} onClick={() => setSection(item.id)} />)}
        </nav>
        <div className="mt-6 rounded-xl border border-primary/15 bg-primary/5 p-3 text-xs text-muted-foreground">
          <p className="font-medium text-foreground">{pick({ tr: "Gizlilik sınırı", en: "Privacy boundary" })}</p>
          <p className="mt-1">{pick({ tr: "Mesajlar, ders kayıtları, e-posta içerikleri ve kimlik bilgileri bu panelde gösterilmez.", en: "Messages, academic records, email contents, and credentials are never shown here." })}</p>
        </div>
      </aside>

      <div className="min-w-0 flex-1">
        <div className="sticky top-0 z-20 flex items-center gap-3 border-b bg-background/90 px-4 py-3 backdrop-blur-xl lg:px-6">
          <MenuIcon className="size-4 lg:hidden" />
          <select aria-label={pick({ tr: "Bölüm", en: "Section" })} value={section} onChange={(event) => setSection(event.target.value as Section)} className="h-9 max-w-56 rounded-lg border bg-card px-3 text-sm lg:hidden">
            {NAV.filter((item) => principal.permissions.includes(item.permission)).map((item) => <option key={item.id} value={item.id}>{pick(item.label)}</option>)}
          </select>
          <div className="hidden items-center gap-2 text-sm text-muted-foreground lg:flex"><span>Admin</span><ChevronRightIcon className="size-3" /><span className="font-medium text-foreground">{pick(active.label)}</span></div>
          <div className="ml-auto flex items-center gap-2"><Badge variant="outline">{principal.bootstrap ? "bootstrap · " : ""}{principal.role.replaceAll("_", " ")}</Badge></div>
        </div>
        <div className="mx-auto max-w-[1500px] p-4 lg:p-6">
          <header className="mb-5"><h1 className="text-2xl font-semibold tracking-tight">{pick(active.label)}</h1><p className="mt-1 text-sm text-muted-foreground">{sectionDescription(section, pick)}</p></header>
          {section === "overview" && <OverviewPanel />}
          {section === "users" && <UsersPanel principal={principal} />}
          {section === "agents" && <AgentsPanel principal={principal} />}
          {section === "integrations" && <IntegrationsPanel />}
          {section === "audit" && <AuditPanel principal={principal} />}
          {section === "access" && <AccessPanel />}
          {section === "runtime" && <RuntimePanel />}
          {section === "system" && <SystemPanel principal={principal} />}
        </div>
      </div>
    </main>
  );
}

function NavButton({ item, active, onClick }: { item: (typeof NAV)[number]; active: boolean; onClick: () => void }) {
  const { pick } = useLocale();
  const Icon = item.icon;
  return <button onClick={onClick} className={cn("flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm transition-colors", active ? "bg-primary text-primary-foreground" : "text-sidebar-foreground hover:bg-sidebar-accent")}><Icon className="size-4" />{pick(item.label)}</button>;
}

function sectionDescription(section: Section, pick: (copy: Copy) => string) {
  const descriptions: Record<Section, Copy> = {
    overview: { tr: "Hesap ve çalışma zamanı durumunun operasyonel özeti.", en: "Operational summary of accounts and runtime health." },
    users: { tr: "Gizlilik güvenli hesap desteği, davet ve yaşam döngüsü işlemleri.", en: "Privacy-safe account support, invitations, and lifecycle actions." },
    agents: { tr: "Yerleşik ajan durumları ve korumalı çalışma zamanı işlemleri.", en: "Resident agent state and guarded runtime actions." },
    integrations: { tr: "METU araçlarının benimsenmesi, doğrulanması ve dağıtılan sürümleri.", en: "METU tool adoption, verification, and deployed versions." },
    audit: { tr: "Yönetici mutasyonlarının değiştirilemez, içeriksiz kaydı.", en: "Append-only, content-free record of admin mutations." },
    access: { tr: "Yönetici üyelikleri ve rol atamaları.", en: "Admin memberships and role assignments." },
    runtime: { tr: "Yeni ajanlar için model ve güvenli davranış varsayılanları.", en: "Model and safe behavior defaults for newly built agents." },
    system: { tr: "Broker, veri kaynakları ve çalışma zamanı havuzu sağlığı.", en: "Broker, data sources, and runtime pool health." },
  };
  return pick(descriptions[section]);
}

function OverviewPanel() {
  const { pick } = useLocale();
  const query = useQuery({ queryKey: ["admin", "overview"], queryFn: () => adminGet<Overview>("overview"), refetchInterval: 60_000, refetchIntervalInBackground: false });
  if (query.isLoading) return <LoadingCards />;
  if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data!;
  const metrics = [
    [pick({ tr: "Toplam hesap", en: "Total accounts" }), data.users, UsersIcon],
    [pick({ tr: "Aktif hesap", en: "Active accounts" }), data.active_users, CheckCircle2Icon],
    [pick({ tr: "Onboarding tamamlandı", en: "Onboarding complete" }), data.onboarding_completed, ClipboardListIcon],
    [pick({ tr: "METU bağlı", en: "METU connected" }), data.campus_connected, Building2Icon],
  ] as const;
  return <div className="space-y-4">
    <div className="flex justify-end"><Button variant="outline" size="sm" onClick={() => void query.refetch()} disabled={query.isFetching}><RefreshCwIcon className={cn(query.isFetching && "animate-spin")} />{pick({ tr: "Yenile", en: "Refresh" })}</Button></div>
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{metrics.map(([label, value, Icon]) => <Card key={label}><CardContent><div className="flex items-start justify-between"><div><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 text-3xl font-semibold tabular-nums">{value}</p></div><span className="rounded-lg bg-primary/10 p-2 text-primary"><Icon className="size-5" /></span></div></CardContent></Card>)}</div>
    <div className="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
      <Card><CardHeader><CardTitle>{pick({ tr: "Operasyonel dikkat", en: "Operational attention" })}</CardTitle><CardDescription>{pick({ tr: "Askıya alınmış hesaplar ve hata durumundaki ajanlar.", en: "Suspended accounts and agents currently in an error state." })}</CardDescription></CardHeader><CardContent>{data.attention.length ? <div className="divide-y">{data.attention.map((item) => <div key={item.user_id} className="flex items-center justify-between gap-3 py-3"><div className="min-w-0"><p className="truncate font-medium">{item.email ?? item.user_id}</p><p className="text-xs text-muted-foreground">{item.user_id}</p></div><div className="flex gap-2"><StatusBadge value={item.account_status} /><StatusBadge value={item.agent_status} /></div></div>)}</div> : <Empty text={pick({ tr: "Dikkat gerektiren öğe yok.", en: "Nothing needs attention." })} />}</CardContent></Card>
      <Card><CardHeader><CardTitle>{pick({ tr: "Ajan kullanılabilirliği", en: "Agent availability" })}</CardTitle><CardDescription>{pick({ tr: "Durum veritabanı + bu brokerdaki yerleşik çalışma zamanları.", en: "Database state plus runtimes resident on this broker." })}</CardDescription></CardHeader><CardContent className="space-y-3">{Object.entries(data.agents).map(([key, value]) => <div key={key} className="flex items-center justify-between"><StatusBadge value={key} /><span className="font-semibold tabular-nums">{value}</span></div>)}<div className="flex items-center justify-between border-t pt-3"><span>{pick({ tr: "Şu anda yerleşik", en: "Resident now" })}</span><span className="font-semibold tabular-nums">{data.resident_agents}</span></div><p className="pt-2 text-xs text-muted-foreground">{pick({ tr: "Son yenileme", en: "Fresh at" })}: {formatDate(data.fresh_at)}</p></CardContent></Card>
    </div>
  </div>;
}

function UsersPanel({ principal }: { principal: AdminPrincipal }) {
  const { pick } = useLocale();
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [selected, setSelected] = useState<AdminUser | null>(null);
  const [actionUser, setActionUser] = useState<AdminUser | null>(null);
  const [action, setAction] = useState<"suspend" | "reactivate" | "delete" | null>(null);
  const query = useQuery({ queryKey: ["admin", "users", search, status, cursor], queryFn: () => adminGet<{ items: AdminUser[]; next_cursor: string | null }>(`users?q=${encodeURIComponent(search)}${status ? `&account_status=${status}` : ""}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`) });
  return <div className="space-y-4">
    <div className="flex flex-col gap-2 sm:flex-row"><div className="relative flex-1"><SearchIcon className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input value={search} onChange={(event) => { setSearch(event.target.value); setCursor(null); }} placeholder={pick({ tr: "Ad veya e-posta ara", en: "Search name or email" })} className="pl-9" /></div><select value={status} onChange={(event) => { setStatus(event.target.value); setCursor(null); }} className="h-9 rounded-lg border bg-card px-3 text-sm"><option value="">{pick({ tr: "Tüm durumlar", en: "All statuses" })}</option><option value="active">active</option><option value="suspended">suspended</option></select><Button render={<Link href="/api/admin/exports/users" />} variant="outline">CSV</Button>{principal.permissions.includes("users:invite") && <Button onClick={() => setInviteOpen(true)}>{pick({ tr: "Kullanıcı davet et", en: "Invite user" })}</Button>}</div>
    {query.isLoading ? <Skeleton className="h-72 rounded-xl" /> : query.error ? <ErrorState error={query.error} retry={() => void query.refetch()} /> : <Card><CardContent className="overflow-x-auto px-0"><table className="w-full min-w-[760px] text-left text-sm"><thead className="border-b text-xs uppercase text-muted-foreground"><tr><th className="px-4 py-3">{pick({ tr: "Kullanıcı", en: "User" })}</th><th className="px-4 py-3">{pick({ tr: "Hesap", en: "Account" })}</th><th className="px-4 py-3">{pick({ tr: "Ajan", en: "Agent" })}</th><th className="px-4 py-3">{pick({ tr: "Son görülme", en: "Last seen" })}</th><th className="px-4 py-3"><span className="sr-only">Actions</span></th></tr></thead><tbody className="divide-y">{query.data?.items.map((user) => <tr key={user.user_id} className="hover:bg-muted/40"><td className="px-4 py-3"><p className="font-medium">{user.display_name || user.email || "—"}</p><p className="text-xs text-muted-foreground">{user.email}</p></td><td className="px-4 py-3"><StatusBadge value={user.status} /></td><td className="px-4 py-3"><StatusBadge value={user.agent_status} /></td><td className="px-4 py-3 text-muted-foreground">{formatDate(user.last_seen_at)}</td><td className="px-4 py-3"><Button variant="ghost" size="sm" onClick={() => setSelected(user)}>{pick({ tr: "İncele", en: "Inspect" })}</Button></td></tr>)}</tbody></table>{!query.data?.items.length && <Empty text={pick({ tr: "Eşleşen kullanıcı yok.", en: "No matching users." })} />}{query.data?.next_cursor && <div className="flex justify-end border-t p-3"><Button variant="outline" size="sm" onClick={() => setCursor(query.data.next_cursor)}>{pick({ tr: "Sonraki sayfa", en: "Next page" })}<ChevronRightIcon /></Button></div>}</CardContent></Card>}
    <InviteDialog open={inviteOpen} onOpenChange={setInviteOpen} onDone={() => void client.invalidateQueries({ queryKey: ["admin", "users"] })} />
    <UserDialog user={selected} onOpenChange={(open) => !open && setSelected(null)} principal={principal} onAction={(nextAction) => { setActionUser(selected); setSelected(null); setAction(nextAction); }} />
    <UserActionDialog user={actionUser} action={action} onOpenChange={(open) => { if (!open) { setAction(null); setActionUser(null); } }} onDone={() => { setActionUser(null); void client.invalidateQueries({ queryKey: ["admin"] }); }} />
  </div>;
}

function InviteDialog({ open, onOpenChange, onDone }: { open: boolean; onOpenChange: (open: boolean) => void; onDone: () => void }) {
  const { pick } = useLocale(); const [email, setEmail] = useState("");
  const mutation = useMutation({ mutationFn: () => adminMutate("invitations", "POST", { email }), onSuccess: () => { toast.success(pick({ tr: "Davet gönderildi", en: "Invitation sent" })); onOpenChange(false); setEmail(""); onDone(); }, onError: (error) => toast.error(error.message) });
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>{pick({ tr: "Kullanıcı davet et", en: "Invite user" })}</DialogTitle><DialogDescription>{pick({ tr: "Supabase güvenli davet akışını kullanır; parola ayarlanmaz veya gösterilmez.", en: "Uses Supabase’s secure invitation flow; no password is set or shown." })}</DialogDescription></DialogHeader><Label htmlFor="invite-email">E-mail</Label><Input id="invite-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} /><DialogFooter><Button onClick={() => mutation.mutate()} disabled={!email || mutation.isPending}>{pick({ tr: "Daveti gönder", en: "Send invite" })}</Button></DialogFooter></DialogContent></Dialog>;
}

function UserDialog({ user, onOpenChange, principal, onAction }: { user: AdminUser | null; onOpenChange: (open: boolean) => void; principal: AdminPrincipal; onAction: (action: "suspend" | "reactivate" | "delete") => void }) {
  const { pick } = useLocale();
  const query = useQuery({ queryKey: ["admin", "user", user?.user_id], queryFn: () => adminGet<AdminUserDetail>(`users/${user!.user_id}`), enabled: Boolean(user) });
  return <Dialog open={Boolean(user)} onOpenChange={onOpenChange}><DialogContent className="sm:max-w-xl"><DialogHeader><DialogTitle>{user?.display_name || user?.email}</DialogTitle><DialogDescription>{user?.user_id}</DialogDescription></DialogHeader>{query.isLoading ? <Skeleton className="h-44" /> : query.data ? <div className="grid gap-3 sm:grid-cols-2"><Detail label={pick({ tr: "Hesap durumu", en: "Account status" })}><StatusBadge value={query.data.status} /></Detail><Detail label={pick({ tr: "Son görülme", en: "Last seen" })}>{formatDate(query.data.last_seen_at)}</Detail><Detail label={pick({ tr: "Ajan", en: "Agent" })}>{query.data.agent ? <StatusBadge value={query.data.agent.status} /> : "—"}</Detail><Detail label={pick({ tr: "Oturum sayısı", en: "Session count" })}>{query.data.sessions.count}</Detail><Detail label={pick({ tr: "METU bağlantısı", en: "METU connection" })}>{query.data.campus.connected ? "Connected" : "—"}</Detail><Detail label={pick({ tr: "Etkin araçlar", en: "Enabled tools" })}>{query.data.campus.enabled_tools.join(", ") || "—"}</Detail></div> : null}<DialogFooter>{principal.permissions.includes("users:suspend") && user?.status === "active" && <Button variant="destructive" onClick={() => onAction("suspend")}>{pick({ tr: "Askıya al", en: "Suspend" })}</Button>}{principal.permissions.includes("users:suspend") && user?.status === "suspended" && <Button variant="outline" onClick={() => onAction("reactivate")}>{pick({ tr: "Yeniden etkinleştir", en: "Reactivate" })}</Button>}{principal.permissions.includes("users:delete") && user?.status === "suspended" && <Button variant="destructive" onClick={() => onAction("delete")}>{pick({ tr: "Kalıcı sil", en: "Delete permanently" })}</Button>}</DialogFooter></DialogContent></Dialog>;
}

function UserActionDialog({ user, action, onOpenChange, onDone }: { user: AdminUser | null; action: "suspend" | "reactivate" | "delete" | null; onOpenChange: (open: boolean) => void; onDone: () => void }) {
  const { pick } = useLocale(); const [reason, setReason] = useState(""); const [confirmEmail, setConfirmEmail] = useState("");
  const mutation = useMutation({ mutationFn: () => adminMutate(`users/${user!.user_id}/${action === "delete" ? "" : action}`.replace(/\/$/, ""), action === "delete" ? "DELETE" : "POST", action === "delete" ? { reason, confirm_email: confirmEmail } : { reason }), onSuccess: () => { toast.success(pick({ tr: "İşlem tamamlandı", en: "Action completed" })); setReason(""); setConfirmEmail(""); onOpenChange(false); onDone(); }, onError: (error) => toast.error(error.message) });
  return <Dialog open={Boolean(user && action)} onOpenChange={onOpenChange}><DialogContent><DialogHeader><DialogTitle>{action === "delete" ? pick({ tr: "Kalıcı silme", en: "Permanent deletion" }) : action === "suspend" ? pick({ tr: "Hesabı askıya al", en: "Suspend account" }) : pick({ tr: "Hesabı etkinleştir", en: "Reactivate account" })}</DialogTitle><DialogDescription>{action === "delete" ? pick({ tr: "Bu işlem geri alınamaz. Ön koşullar sunucuda tekrar denetlenir.", en: "This cannot be undone. Preconditions are rechecked on the server." }) : user?.email}</DialogDescription></DialogHeader><Label htmlFor="reason">{pick({ tr: "Gerekçe", en: "Reason" })}</Label><Textarea id="reason" value={reason} onChange={(event) => setReason(event.target.value)} />{action === "delete" && <><Label htmlFor="confirm-email">{pick({ tr: "Onaylamak için e-postayı yazın", en: "Type the email to confirm" })}</Label><Input id="confirm-email" value={confirmEmail} onChange={(event) => setConfirmEmail(event.target.value)} placeholder={user?.email ?? ""} /></>}<DialogFooter><Button variant={action === "reactivate" ? "default" : "destructive"} disabled={reason.length < 3 || (action === "delete" && confirmEmail.toLowerCase() !== user?.email?.toLowerCase()) || mutation.isPending} onClick={() => mutation.mutate()}>{pick({ tr: "Onayla", en: "Confirm" })}</Button></DialogFooter></DialogContent></Dialog>;
}

function Detail({ label, children }: { label: string; children: React.ReactNode }) { return <div className="rounded-lg border bg-muted/30 p-3"><p className="text-xs text-muted-foreground">{label}</p><div className="mt-1 font-medium">{children}</div></div>; }

function AgentsPanel({ principal }: { principal: AdminPrincipal }) {
  const { pick } = useLocale(); const client = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "agents"], queryFn: () => adminGet<{ items: AgentRow[] }>("agents") });
  const mutation = useMutation({ mutationFn: ({ userId, action }: { userId: string; action: string }) => adminMutate(`agents/${userId}/action`, "POST", { action, reason: "Manual admin runtime operation" }), onSuccess: () => { toast.success(pick({ tr: "Ajan işlemi tamamlandı", en: "Agent action completed" })); void client.invalidateQueries({ queryKey: ["admin"] }); }, onError: (error) => toast.error(error.message) });
  if (query.isLoading) return <Skeleton className="h-72 rounded-xl" />; if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  return <Card><CardContent className="overflow-x-auto px-0"><table className="w-full min-w-[800px] text-left text-sm"><thead className="border-b text-xs uppercase text-muted-foreground"><tr><th className="px-4 py-3">{pick({ tr: "Kullanıcı", en: "User" })}</th><th className="px-4 py-3">{pick({ tr: "Durum", en: "Status" })}</th><th className="px-4 py-3">{pick({ tr: "Yerleşik", en: "Resident" })}</th><th className="px-4 py-3">{pick({ tr: "Son etkinlik", en: "Last activity" })}</th><th className="px-4 py-3">{pick({ tr: "İşlemler", en: "Actions" })}</th></tr></thead><tbody className="divide-y">{query.data?.items.map((agent) => <tr key={agent.user_id}><td className="px-4 py-3"><p className="font-medium">{agent.display_name || agent.email}</p><p className="text-xs text-muted-foreground">{agent.email}</p></td><td className="px-4 py-3"><StatusBadge value={agent.status} /></td><td className="px-4 py-3">{agent.resident ? pick({ tr: "Evet", en: "Yes" }) : pick({ tr: "Hayır", en: "No" })}</td><td className="px-4 py-3 text-muted-foreground">{formatDate(agent.last_active_at)}</td><td className="px-4 py-3"><div className="flex gap-1"><Button variant="outline" size="sm" onClick={() => mutation.mutate({ userId: agent.user_id, action: "restart" })}>{pick({ tr: "Yeniden başlat", en: "Restart" })}</Button>{principal.permissions.includes("agents:manage") && <Button variant="ghost" size="sm" onClick={() => mutation.mutate({ userId: agent.user_id, action: agent.status === "stopped" ? "start" : "stop" })}>{agent.status === "stopped" ? "Start" : "Stop"}</Button>}</div></td></tr>)}</tbody></table></CardContent></Card>;
}

function IntegrationsPanel() {
  const { pick } = useLocale();
  const query = useQuery({ queryKey: ["admin", "integrations"], queryFn: () => adminGet<{ connected_accounts: number; items: Array<{ id: string; name_en: string; name_tr: string; adopted: number; verification_failures: number }>; commits: Record<string, string> }>("integrations") });
  if (query.isLoading) return <LoadingCards />; if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  return <div className="grid gap-4 md:grid-cols-2">{query.data?.items.map((item) => <Card key={item.id}><CardHeader><CardTitle>{pick({ tr: item.name_tr, en: item.name_en })}</CardTitle><CardDescription>{item.id}</CardDescription></CardHeader><CardContent className="grid grid-cols-2 gap-3"><Detail label={pick({ tr: "Benimseyen hesap", en: "Adopted accounts" })}>{item.adopted}</Detail><Detail label={pick({ tr: "Doğrulama hatası", en: "Verification failures" })}>{item.verification_failures}</Detail><div className="col-span-2 text-xs text-muted-foreground">Commit: <code>{query.data.commits[item.id] ?? "not installed"}</code></div></CardContent></Card>)}</div>;
}

function AuditPanel({ principal }: { principal: AdminPrincipal }) {
  const { pick } = useLocale(); const query = useQuery({ queryKey: ["admin", "audit"], queryFn: () => adminGet<{ items: Array<Record<string, string | null>> }>("audit") });
  if (query.isLoading) return <Skeleton className="h-72 rounded-xl" />; if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  return <div className="space-y-3"><div className="flex justify-end">{principal.permissions.includes("audit:export") && <Button render={<Link href="/api/admin/audit/export" />} variant="outline">{pick({ tr: "CSV dışa aktar", en: "Export CSV" })}</Button>}</div><Card><CardContent className="overflow-x-auto px-0"><table className="w-full min-w-[760px] text-left text-sm"><thead className="border-b text-xs uppercase text-muted-foreground"><tr><th className="px-4 py-3">{pick({ tr: "Zaman", en: "Time" })}</th><th className="px-4 py-3">{pick({ tr: "Eylem", en: "Action" })}</th><th className="px-4 py-3">{pick({ tr: "Sonuç", en: "Result" })}</th><th className="px-4 py-3">{pick({ tr: "Hedef", en: "Target" })}</th><th className="px-4 py-3">{pick({ tr: "Gerekçe", en: "Reason" })}</th></tr></thead><tbody className="divide-y">{query.data?.items.map((event) => <tr key={event.id}><td className="px-4 py-3 text-muted-foreground">{formatDate(event.created_at)}</td><td className="px-4 py-3 font-medium">{event.action}</td><td className="px-4 py-3"><StatusBadge value={event.result} /></td><td className="px-4 py-3 font-mono text-xs">{event.target_user_id ?? "—"}</td><td className="max-w-xs truncate px-4 py-3 text-muted-foreground">{event.reason ?? "—"}</td></tr>)}</tbody></table></CardContent></Card></div>;
}

function AccessPanel() {
  const { pick } = useLocale(); const client = useQueryClient(); const [userId, setUserId] = useState(""); const [role, setRole] = useState("campus_admin"); const [reason, setReason] = useState("");
  const query = useQuery({ queryKey: ["admin", "memberships"], queryFn: () => adminGet<{ items: Array<{ user_id: string; email: string | null; role: string; organization_id: string | null; bootstrap: boolean }> }>("memberships") });
  const mutation = useMutation({ mutationFn: () => adminMutate(`memberships/${userId}`, "PUT", { user_id: userId, role, organization_id: null, reason }), onSuccess: () => { toast.success(pick({ tr: "Yönetici rolü kaydedildi", en: "Admin role saved" })); setUserId(""); setReason(""); void client.invalidateQueries({ queryKey: ["admin", "memberships"] }); }, onError: (error) => toast.error(error.message) });
  return <div className="grid gap-4 xl:grid-cols-[1fr_360px]"><Card><CardHeader><CardTitle>{pick({ tr: "Üyelikler", en: "Memberships" })}</CardTitle></CardHeader><CardContent className="space-y-2">{query.data?.items.map((item) => <div key={item.user_id} className="flex items-center justify-between rounded-lg border p-3"><div><p className="font-medium">{item.email ?? item.user_id}</p><p className="text-xs text-muted-foreground">{item.user_id}</p></div><div className="flex gap-2"><StatusBadge value={item.role} />{item.bootstrap && <Badge variant="outline">bootstrap</Badge>}</div></div>)}{!query.data?.items.length && <Empty text={pick({ tr: "Veritabanında yönetici üyeliği yok.", en: "No database admin memberships." })} />}</CardContent></Card><Card><CardHeader><CardTitle>{pick({ tr: "Rol ata", en: "Assign role" })}</CardTitle><CardDescription>{pick({ tr: "Kullanıcı UUID'si hesap dizininde bulunmalıdır.", en: "The user UUID must exist in the account directory." })}</CardDescription></CardHeader><CardContent><form className="space-y-3" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}><div><Label htmlFor="member-id">User ID</Label><Input id="member-id" value={userId} onChange={(event) => setUserId(event.target.value)} /></div><div><Label htmlFor="member-role">Role</Label><select id="member-role" value={role} onChange={(event) => setRole(event.target.value)} className="mt-1 h-9 w-full rounded-lg border bg-background px-3 text-sm"><option value="campus_admin">campus admin</option><option value="operator">operator</option><option value="super_admin">super admin</option></select></div><div><Label htmlFor="member-reason">{pick({ tr: "Gerekçe", en: "Reason" })}</Label><Textarea id="member-reason" value={reason} onChange={(event) => setReason(event.target.value)} /></div><Button type="submit" disabled={!userId || reason.length < 3 || mutation.isPending}>{pick({ tr: "Kaydet", en: "Save" })}</Button></form></CardContent></Card></div>;
}

function RuntimePanel() {
  const query = useQuery({ queryKey: ["admin", "runtime"], queryFn: () => adminGet<RuntimeSettings>("runtime-settings") });
  if (query.isLoading) return <Skeleton className="h-96 rounded-xl" />; if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  return <RuntimeForm key={`${query.data!.revision}-${query.data!.updated_at}`} initial={query.data!} />;
}

function RuntimeForm({ initial }: { initial: RuntimeSettings }) {
  const { pick } = useLocale(); const client = useQueryClient();
  const [form, setForm] = useState(initial); const [reason, setReason] = useState("");
  const mutation = useMutation({ mutationFn: () => adminMutate<RuntimeSettings>("runtime-settings", "PUT", { model_id: form!.model_id, profile: form!.profile, max_tokens: Number(form!.max_tokens), legacy_history_runs: Number(form!.legacy_history_runs), scholar_history_runs: Number(form!.scholar_history_runs), tool_call_limit: Number(form!.tool_call_limit), learning_enabled: form!.learning_enabled, input_token_price: Number(form!.input_token_price), output_token_price: Number(form!.output_token_price), reason }), onSuccess: (data) => { toast.success(pick({ tr: "Ajan varsayılanları güncellendi", en: "Agent defaults updated" })); setReason(""); setForm(data); void client.invalidateQueries({ queryKey: ["admin"] }); }, onError: (error) => toast.error(error.message) });
  const textField = (key: "model_id" | "profile", value: string) => setForm({ ...form, [key]: value } as RuntimeSettings);
  const numberField = (key: "max_tokens" | "legacy_history_runs" | "scholar_history_runs" | "tool_call_limit" | "input_token_price" | "output_token_price", value: number) => setForm({ ...form, [key]: value });
  return <div className="grid gap-4 xl:grid-cols-[1fr_360px]"><Card><CardHeader><CardTitle>{pick({ tr: "Çalışma zamanı varsayılanları", en: "Runtime defaults" })}</CardTitle><CardDescription>{pick({ tr: "Kaydetmek yerleşik ajanları güvenle emekliye ayırır; sonraki istek güncel ayarlarla yeniden oluşturur. Kullanıcı bazlı PostHog özellik bayrakları yine önceliklidir. Token fiyatları tek bir token başınadır, milyon başına değil (örn. $3.00/1M girdi token → 0.000003).", en: "Saving safely retires resident agents; the next request rebuilds with these defaults. Per-user PostHog feature flags still take precedence. Token prices are per single token, not per million (e.g. $3.00/1M input tokens → 0.000003)." })}</CardDescription></CardHeader><CardContent><form className="grid gap-4 sm:grid-cols-2" onSubmit={(event: FormEvent) => { event.preventDefault(); mutation.mutate(); }}><div className="sm:col-span-2"><Label htmlFor="model-id">{pick({ tr: "Varsayılan model", en: "Default model" })}</Label><Input id="model-id" value={form.model_id} onChange={(event) => textField("model_id", event.target.value)} disabled={!form.editable} /></div><div><Label htmlFor="profile">Profile</Label><select id="profile" value={form.profile} onChange={(event) => textField("profile", event.target.value)} disabled={!form.editable} className="mt-1 h-9 w-full rounded-lg border bg-background px-3 text-sm"><option value="scholar">scholar</option><option value="legacy">legacy</option></select></div><NumberField id="max-tokens" label="Max tokens" value={form.max_tokens} disabled={!form.editable} onChange={(value) => numberField("max_tokens", value)} /><NumberField id="scholar-history" label="Scholar history runs" value={form.scholar_history_runs} disabled={!form.editable} onChange={(value) => numberField("scholar_history_runs", value)} /><NumberField id="legacy-history" label="Legacy history runs" value={form.legacy_history_runs} disabled={!form.editable} onChange={(value) => numberField("legacy_history_runs", value)} /><NumberField id="tool-limit" label="Tool call limit" value={form.tool_call_limit} disabled={!form.editable} onChange={(value) => numberField("tool_call_limit", value)} /><NumberField id="input-token-price" label={pick({ tr: "Girdi token fiyatı (USD)", en: "Input token price (USD)" })} value={form.input_token_price} disabled={!form.editable} step="0.000001" onChange={(value) => numberField("input_token_price", value)} /><NumberField id="output-token-price" label={pick({ tr: "Çıktı token fiyatı (USD)", en: "Output token price (USD)" })} value={form.output_token_price} disabled={!form.editable} step="0.000001" onChange={(value) => numberField("output_token_price", value)} /><label className="flex items-center gap-2 self-end pb-2"><input type="checkbox" checked={form.learning_enabled} disabled={!form.editable} onChange={(event) => setForm({ ...form, learning_enabled: event.target.checked })} />{pick({ tr: "Öğrenme etkin", en: "Learning enabled" })}</label>{form.editable && <><div className="sm:col-span-2"><Label htmlFor="runtime-reason">{pick({ tr: "Değişiklik gerekçesi", en: "Change reason" })}</Label><Textarea id="runtime-reason" value={reason} onChange={(event) => setReason(event.target.value)} /></div><div className="sm:col-span-2"><Button type="submit" disabled={reason.length < 3 || mutation.isPending}><Settings2Icon />{pick({ tr: "Varsayılanları uygula", en: "Apply defaults" })}</Button></div></>}</form></CardContent></Card><Card><CardHeader><CardTitle>{pick({ tr: "Etkin yapılandırma", en: "Effective configuration" })}</CardTitle></CardHeader><CardContent className="space-y-3"><Detail label={pick({ tr: "Revizyon", en: "Revision" })}>{form.revision}</Detail><Detail label={pick({ tr: "Kaynak", en: "Source" })}>{form.has_database_override ? "database override" : "environment defaults"}</Detail><Detail label={pick({ tr: "Son güncelleme", en: "Updated" })}>{formatDate(form.updated_at)}</Detail><p className="text-xs text-muted-foreground">{pick({ tr: "API anahtarları ve sağlayıcı uç noktaları sunucu ortamında kalır; bu panelde gösterilmez.", en: "API keys and provider endpoints remain in the server environment and are never shown here." })}</p></CardContent></Card></div>;
}

function NumberField({ id, label, value, disabled, step, onChange }: { id: string; label: string; value: number; disabled: boolean; step?: string; onChange: (value: number) => void }) { return <div><Label htmlFor={id}>{label}</Label><Input id={id} type="number" step={step} value={value} disabled={disabled} onChange={(event) => onChange(Number(event.target.value))} /></div>; }

function SystemPanel({ principal }: { principal: AdminPrincipal }) {
  const { pick } = useLocale(); const client = useQueryClient();
  const query = useQuery({ queryKey: ["admin", "system"], queryFn: () => adminGet<SystemHealth>("system"), refetchInterval: 30_000, refetchIntervalInBackground: false });
  const sync = useMutation({ mutationFn: () => adminMutate("directory/sync", "POST", {}), onSuccess: () => { toast.success(pick({ tr: "Hesap dizini eşitlendi", en: "Account directory synced" })); void client.invalidateQueries({ queryKey: ["admin"] }); }, onError: (error) => toast.error(error.message) });
  if (query.isLoading) return <LoadingCards />; if (query.error) return <ErrorState error={query.error} retry={() => void query.refetch()} />;
  const data = query.data!;
  return <div className="space-y-4"><Card className="border-primary/20 bg-primary/5"><CardContent className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center"><div><div className="flex items-center gap-2 font-semibold"><ExternalLinkIcon className="size-4 text-primary" />PostHog</div><p className="mt-1 text-sm text-muted-foreground">{pick({ tr: "LLM kullanımı, maliyet, hata, trace ve değerlendirme analitiği PostHog'da görüntülenir; bu panel bunları çoğaltmaz.", en: "LLM usage, cost, errors, traces, and evaluation analytics live in PostHog; this panel does not duplicate them." })}</p></div>{data.posthog_dashboard_url ? <Button render={<a href={data.posthog_dashboard_url} target="_blank" rel="noreferrer" />}><ExternalLinkIcon />{pick({ tr: "PostHog'u aç", en: "Open PostHog" })}</Button> : <Badge variant="outline">{pick({ tr: "Panel URL'si yapılandırılmamış", en: "Dashboard URL not configured" })}</Badge>}</CardContent></Card><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4"><HealthCard label="Broker" value={data.broker} /><HealthCard label="Database" value={data.database} /><HealthCard label="PostHog" value={data.posthog} /><HealthCard label="Supabase Admin" value={data.supabase_admin} /></div><div className="grid gap-4 xl:grid-cols-2"><Card><CardHeader><CardTitle>{pick({ tr: "Çalışma zamanı havuzu", en: "Runtime pool" })}</CardTitle></CardHeader><CardContent className="space-y-3"><Detail label={pick({ tr: "Yerleşik ajanlar", en: "Resident agents" })}>{data.resident_agents} / {data.pool_capacity}</Detail><Detail label={pick({ tr: "Çalışma zamanı", en: "Runtime" })}>{data.agent_runtime}</Detail><Detail label={pick({ tr: "Kontrol zamanı", en: "Checked at" })}>{formatDate(data.checked_at)}</Detail></CardContent></Card><Card><CardHeader><CardTitle>{pick({ tr: "Hesap dizini", en: "Account directory" })}</CardTitle><CardDescription>{pick({ tr: "Kimlik dizini normalde beş dakikada bir ve oturum açılmış isteklerde güncellenir.", en: "The identity directory normally refreshes every five minutes and on authenticated requests." })}</CardDescription></CardHeader><CardContent>{principal.permissions.includes("directory:sync") ? <Button variant="outline" onClick={() => sync.mutate()} disabled={sync.isPending}><RefreshCwIcon className={cn(sync.isPending && "animate-spin")} />{pick({ tr: "Şimdi eşitle", en: "Sync now" })}</Button> : <p className="text-sm text-muted-foreground">{pick({ tr: "Manuel eşitleme için süper yönetici gerekir.", en: "Manual sync requires a super admin." })}</p>}</CardContent></Card></div></div>;
}

function HealthCard({ label, value }: { label: string; value: string }) { const good = value === "ok" || value === "configured"; return <Card><CardContent><div className="flex items-center justify-between"><div><p className="text-sm text-muted-foreground">{label}</p><p className="mt-2 font-semibold">{value.replaceAll("_", " ")}</p></div>{good ? <CheckCircle2Icon className="size-5 text-emerald-600" /> : <TriangleAlertIcon className="size-5 text-amber-600" />}</div></CardContent></Card>; }
function Empty({ text }: { text: string }) { return <div className="p-8 text-center text-sm text-muted-foreground">{text}</div>; }
