import React, { useEffect, useState } from 'react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Building2,
  MapPin,
  Mail,
  Phone,
  Calendar,
  Copy,
  Check,
  ExternalLink,
  Cross,
  Stethoscope,
  FlaskConical,
  UserRound,
  Hash,
  Globe2,
  Clock,
  Pencil,
} from 'lucide-react';
import { cn } from '@/lib/utils';

type Facility = Record<string, any>;

interface Props {
  open: boolean;
  facility: Facility | null;
  onOpenChange: (open: boolean) => void;
}

const FACILITY_TYPE_LABEL: Record<string, string> = {
  HOSPITAL: 'Hospital',
  CLINIC: 'Clinic',
  RESEARCH_CENTER: 'Research Center',
  PHYSICIAN_OFFICE: 'Physician Office',
  OTHER: 'Other',
};

// Each facility type gets its own accent colour so the hero gradient + icon
// give an at-a-glance visual cue.
const TYPE_THEME: Record<
  string,
  { gradient: string; iconBg: string; ring: string; accent: string; Icon: React.ElementType }
> = {
  HOSPITAL: {
    gradient: 'from-rose-500/90 via-rose-500/80 to-rose-700/80',
    iconBg: 'bg-rose-100 text-rose-700',
    ring: 'ring-rose-200',
    accent: 'text-rose-700',
    Icon: Cross,
  },
  CLINIC: {
    gradient: 'from-teal-500/90 via-teal-500/80 to-emerald-700/80',
    iconBg: 'bg-teal-100 text-teal-700',
    ring: 'ring-teal-200',
    accent: 'text-teal-700',
    Icon: Stethoscope,
  },
  RESEARCH_CENTER: {
    gradient: 'from-violet-500/90 via-violet-500/80 to-fuchsia-700/80',
    iconBg: 'bg-violet-100 text-violet-700',
    ring: 'ring-violet-200',
    accent: 'text-violet-700',
    Icon: FlaskConical,
  },
  PHYSICIAN_OFFICE: {
    gradient: 'from-sky-500/90 via-sky-500/80 to-blue-700/80',
    iconBg: 'bg-sky-100 text-sky-700',
    ring: 'ring-sky-200',
    accent: 'text-sky-700',
    Icon: UserRound,
  },
  OTHER: {
    gradient: 'from-slate-500/90 via-slate-500/80 to-slate-700/80',
    iconBg: 'bg-slate-100 text-slate-700',
    ring: 'ring-slate-200',
    accent: 'text-slate-700',
    Icon: Building2,
  },
};

const STATUS_DOT: Record<string, string> = {
  ACTIVE: 'bg-emerald-500',
  INACTIVE: 'bg-amber-500',
  ARCHIVED: 'bg-rose-500',
};

const STATUS_PILL: Record<string, string> = {
  ACTIVE: 'bg-emerald-500/15 text-emerald-50 border-emerald-300/40',
  INACTIVE: 'bg-amber-500/15 text-amber-50 border-amber-300/40',
  ARCHIVED: 'bg-rose-500/15 text-rose-50 border-rose-300/40',
};

const formatRelative = (iso?: string): string => {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  const diffMs = Date.now() - d.getTime();
  const sec = Math.round(diffMs / 1000);
  if (Math.abs(sec) < 60) return 'just now';
  const min = Math.round(sec / 60);
  if (Math.abs(min) < 60) return `${min}m ago`;
  const hr = Math.round(min / 60);
  if (Math.abs(hr) < 24) return `${hr}h ago`;
  const day = Math.round(hr / 24);
  if (Math.abs(day) < 30) return `${day}d ago`;
  const month = Math.round(day / 30);
  if (Math.abs(month) < 12) return `${month}mo ago`;
  const yr = Math.round(month / 12);
  return `${yr}y ago`;
};

const formatAbsolute = (iso?: string): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
};

const joinNonEmpty = (parts: Array<string | undefined | null>, sep = ', '): string =>
  parts.filter((p) => p && String(p).trim() !== '').join(sep);

const useCopy = () => {
  const [copiedKey, setCopiedKey] = useState<string | null>(null);
  const copy = (text: string, key: string) => {
    if (!text) return;
    void navigator.clipboard.writeText(text).then(() => {
      setCopiedKey(key);
      window.setTimeout(() => setCopiedKey((curr) => (curr === key ? null : curr)), 1500);
    });
  };
  return { copiedKey, copy };
};

const CopyButton: React.FC<{
  value?: string;
  copyKey: string;
  copiedKey: string | null;
  onCopy: (v: string, k: string) => void;
  label?: string;
}> = ({ value, copyKey, copiedKey, onCopy, label }) => {
  if (!value) return null;
  const isCopied = copiedKey === copyKey;
  return (
    <button
      type="button"
      onClick={() => onCopy(value, copyKey)}
      className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground transition-colors group"
      title={label || 'Copy'}
    >
      {isCopied ? (
        <>
          <Check className="h-3 w-3 text-emerald-600" />
          <span className="text-emerald-600">Copied</span>
        </>
      ) : (
        <>
          <Copy className="h-3 w-3 group-hover:scale-110 transition-transform" />
          <span>Copy</span>
        </>
      )}
    </button>
  );
};

const InfoTile: React.FC<{
  icon: React.ElementType;
  label: string;
  value: React.ReactNode;
  iconClass?: string;
}> = ({ icon: Icon, label, value, iconClass }) => (
  <div className="flex items-start gap-3 rounded-lg border bg-card p-3 hover:shadow-sm transition-shadow">
    <div className={cn('shrink-0 rounded-md p-2', iconClass || 'bg-muted text-muted-foreground')}>
      <Icon className="h-4 w-4" />
    </div>
    <div className="min-w-0 flex-1">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <div className="mt-0.5 text-sm font-medium text-foreground break-words">
        {value || <span className="text-muted-foreground italic">—</span>}
      </div>
    </div>
  </div>
);

const FacilityDetailSheet: React.FC<Props> = ({ open, facility, onOpenChange }) => {
  const { copiedKey, copy } = useCopy();
  const [animateIn, setAnimateIn] = useState(false);

  // Trigger entrance animation each time the sheet opens.
  useEffect(() => {
    if (open) {
      setAnimateIn(false);
      const id = window.requestAnimationFrame(() => setAnimateIn(true));
      return () => window.cancelAnimationFrame(id);
    }
  }, [open, facility?.id]);

  if (!facility) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="right" className="w-full sm:max-w-2xl overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Facility</SheetTitle>
          </SheetHeader>
        </SheetContent>
      </Sheet>
    );
  }

  const type = (facility.facilityType || facility.siteType || 'OTHER') as string;
  const theme = TYPE_THEME[type] || TYPE_THEME.OTHER;
  const HeroIcon = theme.Icon;
  const status = (facility.status || 'INACTIVE') as string;
  const statusDot = STATUS_DOT[status] || 'bg-slate-400';
  const statusPill = STATUS_PILL[status] || 'bg-slate-500/15 text-slate-50 border-slate-300/40';
  const facilityCode = facility.facilityId || facility.facilityCode;

  const fullAddress = joinNonEmpty([
    facility.address?.street,
    facility.address?.addressLine2,
    facility.address?.city,
    facility.address?.state,
    facility.address?.country,
    facility.address?.postalCode,
  ]);
  const mapsHref = fullAddress
    ? `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(fullAddress)}`
    : null;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full sm:max-w-2xl p-0 overflow-hidden flex flex-col">
        {/* Hidden title for a11y */}
        <SheetHeader className="sr-only">
          <SheetTitle>{facility.name || 'Facility'}</SheetTitle>
        </SheetHeader>

        {/* Hero */}
        <div
          className={cn(
            'relative overflow-hidden bg-gradient-to-br text-white px-6 pt-6 pb-5 transition-all duration-300 ease-out',
            theme.gradient,
            animateIn ? 'translate-y-0 opacity-100' : '-translate-y-2 opacity-0'
          )}
        >
          {/* Decorative blob */}
          <div className="pointer-events-none absolute -right-12 -top-12 h-40 w-40 rounded-full bg-white/10 blur-2xl" />
          <div className="pointer-events-none absolute -left-10 bottom-0 h-32 w-32 rounded-full bg-white/10 blur-3xl" />

          <div className="relative flex items-start gap-4">
            <div className={cn('flex h-14 w-14 shrink-0 items-center justify-center rounded-xl ring-4 ring-white/20', theme.iconBg)}>
              <HeroIcon className="h-7 w-7" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2 text-[11px] font-medium tracking-wide uppercase text-white/80">
                <span>{FACILITY_TYPE_LABEL[type] || type}</span>
                <span className="text-white/40">•</span>
                <span className="inline-flex items-center gap-1.5">
                  <span className={cn('relative flex h-2 w-2', statusDot)}>
                    <span
                      className={cn(
                        'absolute inline-flex h-full w-full rounded-full opacity-75',
                        status === 'ACTIVE' ? 'animate-ping bg-emerald-400' : '',
                        statusDot
                      )}
                    />
                    <span className={cn('relative inline-flex h-2 w-2 rounded-full', statusDot)} />
                  </span>
                  <span>{status}</span>
                </span>
              </div>
              <h2 className="mt-1 text-2xl font-bold leading-tight break-words">
                {facility.name || 'Unnamed Facility'}
              </h2>
              {facilityCode && (
                <div className="mt-2 inline-flex items-center gap-2">
                  <Badge
                    variant="outline"
                    className={cn('font-mono text-[10px] h-5 border-white/40 bg-white/10 text-white', statusPill && '')}
                  >
                    <Hash className="h-3 w-3 mr-1" />
                    {facilityCode}
                  </Badge>
                  <button
                    type="button"
                    onClick={() => copy(facilityCode, 'code')}
                    className="text-[10px] text-white/80 hover:text-white inline-flex items-center gap-1 transition-colors"
                    title="Copy code"
                  >
                    {copiedKey === 'code' ? (
                      <>
                        <Check className="h-3 w-3" /> Copied
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" /> Copy
                      </>
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>

          {/* Quick stats strip */}
          <div
            className={cn(
              'relative mt-5 grid grid-cols-3 gap-2 transition-all duration-300 ease-out delay-75',
              animateIn ? 'translate-y-0 opacity-100' : 'translate-y-2 opacity-0'
            )}
          >
            <div className="rounded-lg bg-white/15 backdrop-blur-sm px-3 py-2 border border-white/20">
              <p className="text-[9px] uppercase tracking-wide text-white/70">Location</p>
              <p className="mt-0.5 text-xs font-semibold flex items-center gap-1 truncate">
                <MapPin className="h-3 w-3 shrink-0" />
                <span className="truncate">
                  {joinNonEmpty([facility.address?.city, facility.address?.country]) || '—'}
                </span>
              </p>
            </div>
            <div className="rounded-lg bg-white/15 backdrop-blur-sm px-3 py-2 border border-white/20">
              <p className="text-[9px] uppercase tracking-wide text-white/70">Department</p>
              <p className="mt-0.5 text-xs font-semibold truncate">{facility.deptName || '—'}</p>
            </div>
            <div className="rounded-lg bg-white/15 backdrop-blur-sm px-3 py-2 border border-white/20">
              <p className="text-[9px] uppercase tracking-wide text-white/70">Updated</p>
              <p className="mt-0.5 text-xs font-semibold flex items-center gap-1 truncate">
                <Clock className="h-3 w-3 shrink-0" />
                <span className="truncate">{formatRelative(facility.updatedAt) || '—'}</span>
              </p>
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5">
          <Tabs defaultValue="overview" className="w-full">
            <TabsList className="grid grid-cols-4 w-full">
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="address">Address</TabsTrigger>
              <TabsTrigger value="department">Department</TabsTrigger>
              <TabsTrigger value="activity">Activity</TabsTrigger>
            </TabsList>

            {/* OVERVIEW */}
            <TabsContent value="overview" className="mt-4 space-y-3">
              <InfoTile
                icon={Building2}
                label="Name"
                value={facility.name}
                iconClass={theme.iconBg}
              />
              <InfoTile
                icon={HeroIcon}
                label="Type"
                value={FACILITY_TYPE_LABEL[type] || type}
                iconClass={theme.iconBg}
              />
              <InfoTile
                icon={Globe2}
                label="Campus"
                value={facility.campusName}
                iconClass="bg-muted text-muted-foreground"
              />
              <InfoTile
                icon={Hash}
                label="Internal UUID"
                value={
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-xs">{facility.id || facility._id || '—'}</span>
                    <CopyButton
                      value={facility.id || facility._id}
                      copyKey="uuid"
                      copiedKey={copiedKey}
                      onCopy={copy}
                    />
                  </span>
                }
                iconClass="bg-muted text-muted-foreground"
              />
            </TabsContent>

            {/* ADDRESS */}
            <TabsContent value="address" className="mt-4">
              <div className="rounded-lg border bg-card overflow-hidden">
                <div className="bg-gradient-to-r from-muted/60 to-muted/20 px-4 py-3 flex items-center justify-between border-b">
                  <div className="flex items-center gap-2">
                    <MapPin className={cn('h-4 w-4', theme.accent)} />
                    <p className="text-sm font-semibold">Postal Address</p>
                  </div>
                  <div className="flex items-center gap-3">
                    <CopyButton
                      value={fullAddress}
                      copyKey="address"
                      copiedKey={copiedKey}
                      onCopy={copy}
                    />
                    {mapsHref && (
                      <a
                        href={mapsHref}
                        target="_blank"
                        rel="noreferrer"
                        className={cn(
                          'inline-flex items-center gap-1 text-[10px] font-medium hover:underline',
                          theme.accent
                        )}
                      >
                        Open in Maps
                        <ExternalLink className="h-3 w-3" />
                      </a>
                    )}
                  </div>
                </div>
                <div className="p-4 space-y-1 text-sm">
                  {fullAddress ? (
                    <>
                      {facility.address?.street && (
                        <p className="text-foreground">{facility.address.street}</p>
                      )}
                      {facility.address?.addressLine2 && (
                        <p className="text-foreground">{facility.address.addressLine2}</p>
                      )}
                      <p className="text-foreground">
                        {joinNonEmpty([
                          facility.address?.city,
                          facility.address?.state,
                          facility.address?.postalCode,
                        ])}
                      </p>
                      {facility.address?.country && (
                        <p className="text-muted-foreground text-xs uppercase tracking-wide">
                          {facility.address.country}
                        </p>
                      )}
                    </>
                  ) : (
                    <p className="text-muted-foreground italic">No address on file.</p>
                  )}
                </div>
              </div>
            </TabsContent>

            {/* DEPARTMENT */}
            <TabsContent value="department" className="mt-4 space-y-3">
              <InfoTile
                icon={Building2}
                label="Department"
                value={facility.deptName}
                iconClass={theme.iconBg}
              />
              <InfoTile
                icon={MapPin}
                label="Department Address"
                value={facility.deptAddress}
                iconClass="bg-muted text-muted-foreground"
              />
              <InfoTile
                icon={Mail}
                label="Email"
                iconClass="bg-blue-100 text-blue-700"
                value={
                  facility.deptEmail ? (
                    <span className="flex items-center gap-2">
                      <a
                        href={`mailto:${facility.deptEmail}`}
                        className="text-blue-700 hover:underline break-all"
                      >
                        {facility.deptEmail}
                      </a>
                      <CopyButton
                        value={facility.deptEmail}
                        copyKey="email"
                        copiedKey={copiedKey}
                        onCopy={copy}
                      />
                    </span>
                  ) : null
                }
              />
              <InfoTile
                icon={Phone}
                label="Phone"
                iconClass="bg-emerald-100 text-emerald-700"
                value={
                  facility.deptPhone ? (
                    <span className="flex items-center gap-2">
                      <a
                        href={`tel:${facility.deptPhone}`}
                        className="text-emerald-700 hover:underline"
                      >
                        {facility.deptPhone}
                      </a>
                      <CopyButton
                        value={facility.deptPhone}
                        copyKey="phone"
                        copiedKey={copiedKey}
                        onCopy={copy}
                      />
                    </span>
                  ) : null
                }
              />
            </TabsContent>

            {/* ACTIVITY */}
            <TabsContent value="activity" className="mt-4">
              <ol className="relative ml-3 border-l-2 border-dashed border-muted pl-5 space-y-5">
                <li className="relative">
                  <span className={cn('absolute -left-[27px] top-0 h-4 w-4 rounded-full ring-4 ring-background', theme.iconBg)} />
                  <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                    <Calendar className="h-3.5 w-3.5" /> Created
                  </div>
                  <p className="mt-0.5 text-sm">{formatAbsolute(facility.createdAt)}</p>
                  {facility.createdAt && (
                    <p className="text-[11px] text-muted-foreground">{formatRelative(facility.createdAt)}</p>
                  )}
                </li>
                <li className="relative">
                  <span className={cn('absolute -left-[27px] top-0 h-4 w-4 rounded-full ring-4 ring-background', theme.iconBg)} />
                  <div className="flex items-center gap-2 text-xs font-semibold text-foreground">
                    <Pencil className="h-3.5 w-3.5" /> Last updated
                  </div>
                  <p className="mt-0.5 text-sm">{formatAbsolute(facility.updatedAt)}</p>
                  {facility.updatedAt && (
                    <p className="text-[11px] text-muted-foreground">{formatRelative(facility.updatedAt)}</p>
                  )}
                </li>
              </ol>
            </TabsContent>
          </Tabs>
        </div>

        {/* Footer */}
        <div className="border-t bg-muted/30 px-6 py-3 flex items-center justify-between">
          <span className="text-[10px] text-muted-foreground">
            Read-only · sourced from external facilities service
          </span>
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default FacilityDetailSheet;
