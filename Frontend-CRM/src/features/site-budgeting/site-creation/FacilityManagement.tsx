import React, { useState, useEffect, useCallback } from 'react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Building2,
  Loader2,
  Search,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
} from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/use-toast";
import { Card, CardContent } from "@/components/ui/card";
import { cn } from '@/lib/utils';
import facilityService from './services/facility.service';
import FacilityDetailSheet from './FacilityDetailSheet';

const FACILITY_TYPES = [
  { value: 'HOSPITAL', label: 'Hospital' },
  { value: 'CLINIC', label: 'Clinic' },
  { value: 'RESEARCH_CENTER', label: 'Research Center' },
  { value: 'PHYSICIAN_OFFICE', label: 'Physician Office' },
  { value: 'OTHER', label: 'Other' },
];

const STATUS_OPTIONS = [
  { value: 'ACTIVE', label: 'Active' },
  { value: 'INACTIVE', label: 'Inactive' },
  { value: 'ARCHIVED', label: 'Archived' },
];

const getStatusColors = (status: string): string => {
  switch (status) {
    case 'ACTIVE':
      return 'text-emerald-700 border-emerald-300 bg-emerald-50';
    case 'INACTIVE':
      return 'text-amber-700 border-amber-300 bg-amber-50';
    case 'ARCHIVED':
      return 'text-red-700 border-red-300 bg-red-50';
    default:
      return '';
  }
};

const formatFacilityType = (type: string): string => {
  const found = FACILITY_TYPES.find((t) => t.value === type);
  return found ? found.label : type;
};

const formatTimestamp = (iso?: string): string => {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString();
};

const joinNonEmpty = (parts: Array<string | undefined | null>, sep = ', '): string =>
  parts.filter((p) => p && String(p).trim() !== '').join(sep);

const FacilityManagement: React.FC = () => {
  const [selectedFacility, setSelectedFacility] = useState<any>(null);
  const [showDetail, setShowDetail] = useState(false);
  const [facilities, setFacilities] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    search: '',
    siteType: 'all',
    status: 'all',
  });
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 10,
    total: 0,
    pages: 0,
  });

  const { toast } = useToast();

  const loadFacilities = useCallback(async () => {
    try {
      setLoading(true);
      const params: Record<string, unknown> = {
        page: pagination.page,
        limit: pagination.limit,
        ...(filters.search && { search: filters.search }),
        ...(filters.siteType !== 'all' && { siteType: filters.siteType }),
        ...(filters.status !== 'all' && { status: filters.status }),
      };

      const response = await facilityService.getFacilities(params);

      if (response.success) {
        const data = response.data || [];
        setFacilities(Array.isArray(data) ? data : []);
        setPagination((prev) => ({
          ...prev,
          total: response.pagination?.total ?? response.total ?? data.length,
          pages:
            response.pagination?.pages ??
            Math.ceil(
              (response.pagination?.total ?? response.total ?? data.length) /
                pagination.limit
            ),
        }));
      } else {
        setFacilities([]);
        setPagination((prev) => ({ ...prev, total: 0, pages: 0 }));
        toast({
          title: 'Error',
          description: (response as any).error || 'Failed to load facilities',
          variant: 'destructive',
        });
      }
    } catch (error) {
      console.error('Error loading facilities:', error);
      toast({
        title: 'Error',
        description: 'Failed to load facilities',
        variant: 'destructive',
      });
      setFacilities([]);
    } finally {
      setLoading(false);
    }
  }, [filters, pagination.page, pagination.limit, toast]);

  useEffect(() => {
    loadFacilities();
  }, [loadFacilities]);

  const handleFilterChange = (key: string, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value }));
    setPagination((prev) => ({ ...prev, page: 1 }));
  };

  const handleRowClick = (facility: any) => {
    setSelectedFacility(facility);
    setShowDetail(true);
  };

  const handleDetailClose = (open: boolean) => {
    if (!open) {
      setShowDetail(false);
      setSelectedFacility(null);
    }
  };

  const handlePageChange = (newPage: number) => {
    setPagination((prev) => ({ ...prev, page: newPage }));
  };

  const handleLimitChange = (newLimit: string) => {
    setPagination((prev) => ({ ...prev, limit: parseInt(newLimit), page: 1 }));
  };

  if (loading && facilities.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">Loading facilities...</span>
      </div>
    );
  }

  return (
    <Card className="mt-4">
      <CardContent className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-2xl font-semibold">Facilities</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Read-only list pulled from the external facilities service. Click a row for full details.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => loadFacilities()}
            disabled={loading}
            title="Refresh facilities"
          >
            <RefreshCw className={cn('h-4 w-4 mr-2', loading && 'animate-spin')} />
            Refresh
          </Button>
        </div>

        {/* Filters */}
        <div className="mb-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-muted-foreground" />
              <Input
                placeholder="Search facilities..."
                value={filters.search}
                onChange={(e) => handleFilterChange('search', e.target.value)}
                className="pl-8 h-9 text-xs"
              />
            </div>

            <Select
              value={filters.siteType}
              onValueChange={(v) => handleFilterChange('siteType', v)}
            >
              <SelectTrigger className="w-[180px] h-9 text-xs">
                <SelectValue placeholder="All Types" />
              </SelectTrigger>
              <SelectContent style={{ zIndex: 9999 }}>
                <SelectItem value="all">All Types</SelectItem>
                {FACILITY_TYPES.map((type) => (
                  <SelectItem key={type.value} value={type.value}>
                    {type.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={filters.status}
              onValueChange={(v) => handleFilterChange('status', v)}
            >
              <SelectTrigger className="w-[160px] h-9 text-xs">
                <SelectValue placeholder="All Statuses" />
              </SelectTrigger>
              <SelectContent style={{ zIndex: 9999 }}>
                <SelectItem value="all">All Statuses</SelectItem>
                {STATUS_OPTIONS.map((s) => (
                  <SelectItem key={s.value} value={s.value}>
                    {s.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* Table */}
        <div className="flex-1 min-h-0">
          <div className="h-full rounded-lg border bg-card shadow-sm flex flex-col">
            <div className="overflow-x-auto overflow-y-auto flex-1">
              {loading ? (
                <div className="flex justify-center items-center h-64">
                  <Loader2 className="h-8 w-8 animate-spin mx-auto mb-3 text-muted-foreground" />
                </div>
              ) : facilities.length === 0 ? (
                <div className="flex justify-center items-center h-64">
                  <div className="text-center">
                    <Building2 className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                    <p className="text-sm font-medium">No facilities found</p>
                    <p className="text-xs text-muted-foreground">
                      Try adjusting your filters.
                    </p>
                  </div>
                </div>
              ) : (
                <TooltipProvider>
                  <Table className="w-full">
                    <TableHeader className="sticky top-0 bg-card z-10 border-b">
                      <TableRow className="hover:bg-muted/50 h-9">
                        <TableHead className="text-xs h-9 py-2 w-[140px] sticky left-0 bg-card z-20 border-r">
                          Facility ID
                        </TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[220px] max-w-[220px]">
                          Name
                        </TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[160px]">Type</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[140px]">Campus</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[260px]">Address</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[200px]">Department</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[160px]">Dept. Contact</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[100px]">Status</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[150px]">Created</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[150px]">Updated</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {facilities.map((facility: any) => {
                        const fullAddress = joinNonEmpty([
                          facility.address?.street,
                          facility.address?.addressLine2,
                          facility.address?.city,
                          facility.address?.state,
                          facility.address?.country,
                          facility.address?.postalCode,
                        ]);
                        const deptContact = joinNonEmpty(
                          [facility.deptEmail, facility.deptPhone],
                          ' · '
                        );
                        return (
                          <TableRow
                            key={facility._id || facility.id || facility.facilityId}
                            className="group hover:bg-muted/50 transition-colors cursor-pointer"
                            onClick={() => handleRowClick(facility)}
                          >
                            {/* Facility ID */}
                            <TableCell className="py-2 sticky left-0 bg-background z-10 border-r">
                              <Badge variant="outline" className="font-mono text-[10px] h-5">
                                {facility.facilityId || facility.facilityCode || 'N/A'}
                              </Badge>
                            </TableCell>

                            {/* Name */}
                            <TableCell className="py-2 w-[220px] max-w-[220px]">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <div className="flex items-center gap-2 min-w-0">
                                    <div className="w-5 h-5 rounded bg-slate-700 flex items-center justify-center flex-shrink-0">
                                      <Building2 className="h-3 w-3 text-white" />
                                    </div>
                                    <span className="font-medium text-[11px] leading-tight truncate block min-w-0 flex-1">
                                      {facility.name || 'Unnamed Facility'}
                                    </span>
                                  </div>
                                </TooltipTrigger>
                                {facility.name && (
                                  <TooltipContent side="top" className="max-w-sm">
                                    <p className="break-words">{facility.name}</p>
                                  </TooltipContent>
                                )}
                              </Tooltip>
                            </TableCell>

                            {/* Type */}
                            <TableCell className="py-2">
                              <span className="text-[11px] text-muted-foreground">
                                {formatFacilityType(facility.facilityType || facility.siteType || '') || '—'}
                              </span>
                            </TableCell>

                            {/* Campus */}
                            <TableCell className="py-2">
                              <span className="text-[11px]">{facility.campusName || '—'}</span>
                            </TableCell>

                            {/* Address */}
                            <TableCell className="py-2">
                              <Tooltip>
                                <TooltipTrigger asChild>
                                  <span className="text-[11px] truncate block max-w-[260px]">
                                    {fullAddress || '—'}
                                  </span>
                                </TooltipTrigger>
                                {fullAddress && (
                                  <TooltipContent side="top" className="max-w-sm">
                                    <p className="break-words">{fullAddress}</p>
                                  </TooltipContent>
                                )}
                              </Tooltip>
                            </TableCell>

                            {/* Department */}
                            <TableCell className="py-2">
                              <div className="text-[11px] leading-tight">
                                <div className="font-medium truncate">{facility.deptName || '—'}</div>
                                {facility.deptAddress && (
                                  <div className="text-muted-foreground truncate">{facility.deptAddress}</div>
                                )}
                              </div>
                            </TableCell>

                            {/* Department Contact */}
                            <TableCell className="py-2">
                              <span className="text-[11px] truncate block max-w-[160px]">
                                {deptContact || '—'}
                              </span>
                            </TableCell>

                            {/* Status */}
                            <TableCell className="py-2">
                              <Badge
                                variant="outline"
                                className={cn(
                                  'text-[10px] h-5',
                                  getStatusColors(facility.status)
                                )}
                              >
                                {facility.status || 'N/A'}
                              </Badge>
                            </TableCell>

                            {/* Created */}
                            <TableCell className="py-2">
                              <span className="text-[11px] text-muted-foreground">
                                {formatTimestamp(facility.createdAt)}
                              </span>
                            </TableCell>

                            {/* Updated */}
                            <TableCell className="py-2">
                              <span className="text-[11px] text-muted-foreground">
                                {formatTimestamp(facility.updatedAt)}
                              </span>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </TooltipProvider>
              )}
            </div>
          </div>
        </div>

        {/* Pagination */}
        {facilities.length > 0 && pagination.pages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Rows per page:</span>
                <Select
                  value={pagination.limit.toString()}
                  onValueChange={handleLimitChange}
                >
                  <SelectTrigger className="w-[70px] h-8 text-xs">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent style={{ zIndex: 9999 }}>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="20">20</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="text-sm text-muted-foreground">
                Showing {(pagination.page - 1) * pagination.limit + 1} to{' '}
                {Math.min(pagination.page * pagination.limit, pagination.total)} of{' '}
                {pagination.total} facilities
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={() => handlePageChange(pagination.page - 1)}
                disabled={pagination.page === 1 || loading}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="flex items-center gap-1">
                {Array.from(
                  { length: Math.min(5, pagination.pages) },
                  (_, i) => {
                    let pageNum: number;
                    if (pagination.pages <= 5) pageNum = i + 1;
                    else if (pagination.page <= 3) pageNum = i + 1;
                    else if (pagination.page >= pagination.pages - 2)
                      pageNum = pagination.pages - 4 + i;
                    else pageNum = pagination.page - 2 + i;
                    return (
                      <Button
                        key={pageNum}
                        variant={pagination.page === pageNum ? 'default' : 'outline'}
                        size="sm"
                        className="h-8 w-8 p-0"
                        onClick={() => handlePageChange(pageNum)}
                        disabled={loading}
                      >
                        {pageNum}
                      </Button>
                    );
                  }
                )}
              </div>
              <Button
                variant="outline"
                size="sm"
                className="h-8"
                onClick={() => handlePageChange(pagination.page + 1)}
                disabled={pagination.page >= pagination.pages || loading}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        <FacilityDetailSheet
          open={showDetail}
          facility={selectedFacility}
          onOpenChange={handleDetailClose}
        />
      </CardContent>
    </Card>
  );
};

export default FacilityManagement;
