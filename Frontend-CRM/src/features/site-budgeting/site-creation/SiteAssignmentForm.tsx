import React, { useState, useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2 } from 'lucide-react';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { useToast } from '@/components/ui/use-toast';
import siteService from './services/site.service';
import facilityService from './services/facility.service';
import { useStudyTeam } from '@/lib/queries/useStudies';

const formSchema = z.object({
  siteCode: z.string().optional(),
  study: z.string().min(1, 'Please select a study'),
  facility: z.string().min(1, 'Please select a facility'),
  principalInvestigator: z.string().min(1, 'Please select a principal investigator'),
  status: z.string().default('PENDING'),
  monitoring: z.object({ visitFrequency: z.string().default('MONTHLY') }).optional(),
});

type FormValues = z.infer<typeof formSchema>;

const facilityInlineSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  location: z.string().min(1, 'Location is required'),
  type: z.string().default('HOSPITAL'),
  contact: z.object({ phone: z.string().optional(), email: z.string().optional() }).optional(),
});

type FacilityInlineValues = z.infer<typeof facilityInlineSchema>;

interface SiteAssignmentFormProps {
  site?: Record<string, any> | null;
  /** The study currently in context (Study Setup). The site is always created for
   *  THIS study — the form no longer asks the user to pick one. */
  selectedStudyId?: string | null;
  onSubmit: (data: any) => void;
  onCancel: () => void;
  submitting?: boolean;
}

const SiteAssignmentForm: React.FC<SiteAssignmentFormProps> = ({
  site,
  selectedStudyId,
  onSubmit,
  onCancel,
  submitting = false,
}) => {
  const [showNewFacilitySheet, setShowNewFacilitySheet] = useState(false);
  const [showNewUserSheet, setShowNewUserSheet] = useState(false);
  const [isSearchingNPI, setIsSearchingNPI] = useState(false);
  const [newFacilities, setNewFacilities] = useState<any[]>([]);

  const [apiFacilities, setApiFacilities] = useState<any[]>([]);
  const [loadingFacilities, setLoadingFacilities] = useState(true);

  // Principal Investigators come from IAM (the same /study-team source the
  // Users / Study Team tab shows) scoped to THIS study — only users granted the
  // PI role for the selected study are eligible (empty if none).
  const studyIdForPIs = site?.study || selectedStudyId || '';
  const teamQuery = useStudyTeam(studyIdForPIs, { enabled: Boolean(studyIdForPIs) });
  const loadingPIs = teamQuery.isFetching;
  const loadingData = loadingFacilities;

  const { toast } = useToast();

  const {
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<FormValues>({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    resolver: zodResolver(formSchema) as any,
    defaultValues: {
      siteCode: site?.siteCode || '',
      // Study is taken from the current Study Setup context, not chosen in the form.
      study: site?.study || selectedStudyId || '',
      facility: site?.facility || '',
      principalInvestigator: site?.principalInvestigator || '',
      status: site?.status || 'PENDING',
      monitoring: site?.monitoring || { visitFrequency: 'MONTHLY' },
    },
  });

  const facilityForm = useForm<FacilityInlineValues>({
    defaultValues: { name: '', location: '', type: 'HOSPITAL', contact: { phone: '', email: '' } },
  });

  useEffect(() => {
    reset({
      siteCode: site?.siteCode || '',
      // Study is taken from the current Study Setup context, not chosen in the form.
      study: site?.study || selectedStudyId || '',
      facility: site?.facility || '',
      principalInvestigator: site?.principalInvestigator || '',
      status: site?.status || 'PENDING',
      monitoring: site?.monitoring || { visitFrequency: 'MONTHLY' },
    });
  }, [site, selectedStudyId, reset]);

  // Facilities live in their own service (not the api axios instance), so
  // they stay on a one-shot useEffect; studies + users come from cached
  // TanStack Query hooks that the rest of the app already populates.
  useEffect(() => {
    let cancelled = false;
    setLoadingFacilities(true);
    facilityService
      .getFacilities({ limit: 100 })
      .then((res) => {
        if (cancelled) return;
        setApiFacilities(res.success ? (res.data || []) : []);
      })
      .catch((err) => {
        console.error('Error loading facilities:', err);
        if (!cancelled) setApiFacilities([]);
      })
      .finally(() => {
        if (!cancelled) setLoadingFacilities(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const allFacilities = [...apiFacilities, ...newFacilities];
  // Only Principal Investigators assigned to THIS study in IAM. A study-team row
  // carries the user's per-study access in `studies[]` ({ id, study_id, role }), so
  // pick the entry for the selected study and keep it only if its role is PI. Role
  // strings vary (PRINCIPAL_INVESTIGATOR / principal.investigator / PI), so normalise.
  const isPIRole = (role?: string | null) => {
    const r = (role || '').toLowerCase().replace(/[\s.]+/g, '_');
    return r === 'principal_investigator' || r === 'investigator' || r === 'pi';
  };
  const usersToShow = ((teamQuery.data?.data ?? []) as any[])
    .filter(
      (row) =>
        Array.isArray(row.studies) &&
        row.studies.some(
          (s: any) =>
            (s.id === studyIdForPIs || s.study_id === studyIdForPIs) && isPIRole(s.role),
        ),
    )
    .map((row) => ({ user_id: row.user_id, name: row.name, email: row.email }));

  const onFormSubmit = (data: any) => {
    onSubmit(siteService.transformFormForAPI(data));
  };

  const handleCreateFacility = async (data: FacilityInlineValues) => {
    const res = await facilityService.createFacility({
      name: data.name,
      facilityType: data.type,
      location: data.location,
      address: { street: data.location, city: data.location, country: 'Unknown', postalCode: '00000' },
    });
    if (res.success) {
      setNewFacilities((prev) => [...prev, res.data]);
      setShowNewFacilitySheet(false);
      facilityForm.reset();
      toast({ title: 'Facility created', description: `${data.name} added successfully.` });
    } else {
      toast({ title: 'Error', description: res.error || 'Failed to create facility', variant: 'destructive' });
    }
  };

  const searchNPI = async (npi: string) => {
    setIsSearchingNPI(true);
    try {
      const res = await fetch(`https://npiregistry.cms.hhs.gov/api/?version=2.1&number=${npi}&pretty=true`);
      const data = await res.json();
      if (data.result_count > 0) {
        const r = data.results[0];
        const addr = r.addresses[0];
        facilityForm.setValue('name', r.basic.organization_name || '');
        facilityForm.setValue('location', [addr.city, addr.state].filter(Boolean).join(', '));
        toast({ title: 'Facility found', description: 'Info auto-filled from NPI Registry.' });
      } else {
        toast({ title: 'No results', description: 'No facility found for this NPI.', variant: 'destructive' });
      }
    } catch {
      toast({ title: 'Error', description: 'Could not reach NPI Registry.', variant: 'destructive' });
    } finally {
      setIsSearchingNPI(false);
    }
  };

  const errMsg = (key: keyof FormValues) =>
    errors[key] ? <p className="text-xs text-red-500 mt-1">{errors[key]?.message as string}</p> : null;

  return (
    <>
      <form onSubmit={handleSubmit(onFormSubmit)} className="space-y-4">
        {/* Study is taken from the current Study Setup context — no selector here.
            The created site always belongs to the study the user is already in. */}

        {/* Facility */}
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">Facility *</label>
          <Controller
            control={control}
            name="facility"
            render={({ field: f }) => (
              <Select value={f.value} onValueChange={f.onChange} disabled={loadingData}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={loadingData ? 'Loading facilities…' : 'Select a facility'} />
                </SelectTrigger>
                <SelectContent style={{ zIndex: 9999 }}>
                  {allFacilities.length === 0 ? (
                    <SelectItem value="__none" disabled>No facilities — add one first</SelectItem>
                  ) : (
                    allFacilities.map((fac: any) => {
                      const fid = fac._id || fac.id || fac.facilityId || fac.facilityCode;
                      return fid ? (
                        <SelectItem key={String(fid)} value={String(fid)}>
                          {fac.name || fac.facilityName || 'Unnamed'} — {fac.address?.city || fac.location || ''}
                        </SelectItem>
                      ) : null;
                    })
                  )}
                </SelectContent>
              </Select>
            )}
          />
          {errMsg('facility')}
        </div>

        {/* Principal Investigator */}
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">Principal Investigator *</label>
          <Controller
            control={control}
            name="principalInvestigator"
            render={({ field: f }) => (
              <Select value={f.value} onValueChange={f.onChange} disabled={loadingPIs}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder={loadingPIs ? 'Loading…' : 'Select a principal investigator'} />
                </SelectTrigger>
                <SelectContent style={{ zIndex: 9999 }}>
                  {usersToShow.length === 0 ? (
                    <SelectItem value="__none" disabled>No principal investigators for this study</SelectItem>
                  ) : (
                    usersToShow.map((u: any) => {
                      const uid = u._id || u.id || u.user_id;
                      const displayName = u.name || `${u.firstName || ''} ${u.lastName || ''}`.trim() || u.user_id || uid;
                      return uid ? (
                        <SelectItem key={uid} value={String(uid)}>
                          {displayName}{u.email ? ` — ${u.email}` : ''}
                        </SelectItem>
                      ) : null;
                    })
                  )}
                </SelectContent>
              </Select>
            )}
          />
          {errMsg('principalInvestigator')}
        </div>

        {/* Status — read-only. Derived from site milestones, not picked by hand. */}
        <div>
          <label className="text-sm font-medium text-gray-700 mb-1 block">Status</label>
          <Controller
            control={control}
            name="status"
            render={({ field: f }) => {
              const opt = siteService
                .getStatusOptions()
                .find((s) => s.value === (f.value || 'PENDING').toUpperCase())
              return (
                <div>
                  <Badge variant="outline">{opt?.label ?? 'Pending'}</Badge>
                  <p className="text-xs text-gray-500 mt-1">
                    Set automatically by site milestones — a site becomes Active once
                    its Site Selection Outcome is “Selected”.
                  </p>
                </div>
              )
            }}
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onCancel}>Cancel</Button>
          <Button type="submit" disabled={submitting}>
            {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {site ? 'Update Site' : 'Create Site'}
          </Button>
        </div>
      </form>

      {/* Quick-create Facility Sheet */}
      <Sheet open={showNewFacilitySheet} onOpenChange={setShowNewFacilitySheet}>
        <SheetContent
          side="right"
          className="w-full sm:max-w-md overflow-y-auto"
          onPointerDownOutside={(e) => e.preventDefault()}
        >
          <SheetHeader>
            <SheetTitle>Add New Facility</SheetTitle>
          </SheetHeader>
          <div className="mt-6 space-y-4">
            <div>
              <label className="text-sm font-medium mb-1 block">NPI Number (optional)</label>
              <div className="flex gap-2">
                <Input
                  placeholder="10-digit NPI"
                  onChange={(e) => { if (e.target.value.length === 10) searchNPI(e.target.value); }}
                />
                {isSearchingNPI && <Loader2 className="h-5 w-5 animate-spin mt-2" />}
              </div>
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Facility Name *</label>
              <Input {...facilityForm.register('name')} placeholder="e.g. City General Hospital" />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Location *</label>
              <Input {...facilityForm.register('location')} placeholder="City, State" />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">Type</label>
              <Controller
                control={facilityForm.control}
                name="type"
                render={({ field: f }) => (
                  <Select value={f.value} onValueChange={f.onChange}>
                    <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                    <SelectContent style={{ zIndex: 9999 }}>
                      <SelectItem value="HOSPITAL">Hospital</SelectItem>
                      <SelectItem value="CLINIC">Clinic</SelectItem>
                      <SelectItem value="RESEARCH_CENTER">Research Center</SelectItem>
                      <SelectItem value="PHYSICIAN_OFFICE">Physician Office</SelectItem>
                      <SelectItem value="OTHER">Other</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-sm font-medium mb-1 block">Phone</label>
                <Input type="tel" {...facilityForm.register('contact.phone')} />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Email</label>
                <Input type="email" {...facilityForm.register('contact.email')} />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setShowNewFacilitySheet(false)}>Cancel</Button>
              <Button type="button" onClick={facilityForm.handleSubmit(handleCreateFacility)}>Create Facility</Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>

      {/* User info Sheet */}
      <Sheet open={showNewUserSheet} onOpenChange={setShowNewUserSheet}>
        <SheetContent side="right" className="w-full sm:max-w-md">
          <SheetHeader><SheetTitle>Add New User</SheetTitle></SheetHeader>
          <div className="mt-6 space-y-3">
            <p className="text-sm text-gray-500">
              Users are managed in the User Management section. Create a user there first, then return here to assign them as Principal Investigator.
            </p>
            <div className="flex justify-end">
              <Button type="button" variant="outline" onClick={() => setShowNewUserSheet(false)}>Close</Button>
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
};

export default SiteAssignmentForm;
