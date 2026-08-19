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
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FileText, Building2, User2, Pencil, Trash2, Loader2, Plus, MapPin, ChevronLeft, ChevronRight } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import SiteAssignmentForm from './SiteAssignmentForm';
import { Badge } from "@/components/ui/badge";
import { useToast } from "@/components/ui/use-toast";
import siteService from './services/site.service';
import { useStudySite } from '../../../contexts/StudySiteContext';
import { cn } from '@/lib/utils';
import { Card, CardContent } from "@/components/ui/card";

const SiteAssignmentManagement: React.FC = () => {
  const [showDialog, setShowDialog] = useState(false);
  const [selectedSite, setSelectedSite] = useState<any>(null);
  const [sites, setSites] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [pagination, setPagination] = useState({
    page: 1,
    limit: 10,
    total: 0,
    pages: 0
  });

  const { toast } = useToast();
  const { refreshSites: refreshStudySiteContext, selectedStudyId } = useStudySite();

  const loadSites = useCallback(async () => {
    try {
      setLoading(true);
      // Sites are always scoped to the currently selected study — no other
      // filters are exposed in the UI.
      const params: Record<string, any> = {
        page: pagination.page,
        limit: pagination.limit,
        ...(selectedStudyId && { study: selectedStudyId })
      };

      const response = await siteService.getAllSites(params);

      if (response) {
        const sitesData = response.data || response;
        const sitesArray = Array.isArray(sitesData) ? sitesData : [];

        if (sitesArray.length > 0 || response.data) {
          setSites(sitesArray.map((site: any) => siteService.formatSiteForDisplay(site)));
          setPagination(prev => ({
            ...prev,
            total: response.pagination?.total || response.total || sitesArray.length,
            pages: response.pagination?.pages || response.pages || Math.ceil(
              (response.pagination?.total || response.total || sitesArray.length) / pagination.limit
            )
          }));
        } else {
          setSites([]);
          setPagination(prev => ({ ...prev, total: 0, pages: 0 }));
        }
      }
    } catch (error) {
      console.error('Error loading sites:', error);
      toast({ title: "Error", description: "Failed to load sites", variant: "destructive" });
      setSites([]);
    } finally {
      setLoading(false);
    }
  }, [selectedStudyId, pagination.page, pagination.limit, toast]);

  useEffect(() => {
    loadSites();
  }, [loadSites]);

  // Reset to the first page whenever the active study changes so we never land
  // on a now-out-of-range page from the previous study's site count.
  useEffect(() => {
    setPagination(prev => ({ ...prev, page: 1 }));
  }, [selectedStudyId]);

  const handleDelete = async (siteId: string) => {
    if (!window.confirm('Are you sure you want to delete this site?')) return;

    try {
      setSubmitting(true);
      const response = await siteService.deleteSite(siteId);

      if (response && (response.success || response.data)) {
        toast({ title: "Success", description: "Site deleted successfully" });
        await loadSites();
        // Mirror the change into the global StudySite context so navbar /
        // conversations / monitoring pickers drop the deleted site without a
        // page refresh.
        await refreshStudySiteContext();
      } else {
        throw new Error('Delete failed - invalid response');
      }
    } catch (error: any) {
      console.error('Error deleting site:', error);
      toast({
        title: "Error",
        description: error.response?.data?.error || error.message || "Failed to delete site",
        variant: "destructive"
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleSaveSite = async (data: any) => {
    try {
      setSubmitting(true);
      const apiData = siteService.transformFormForAPI(data);

      let response;
      if (selectedSite) {
        response = await siteService.updateSite(selectedSite._id || selectedSite.id, apiData);
      } else {
        response = await siteService.createSite(apiData);
      }

      if (response && (response.success || response.data)) {
        toast({
          title: "Success",
          description: selectedSite ? "Site updated successfully" : "Site created successfully"
        });
        setShowDialog(false);
        setSelectedSite(null);
        await loadSites();
        // Mirror the new/updated site into the global StudySite context so
        // every other picker (navbar, conversations, …) sees it instantly.
        await refreshStudySiteContext();
      } else {
        throw new Error('Save operation failed - invalid response');
      }
    } catch (error: any) {
      console.error('Error saving site:', error);
      toast({
        title: "Error",
        description: error.response?.data?.error || error.message || "Failed to save site",
        variant: "destructive"
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleEdit = (site: any) => {
    setSelectedSite(site);
    setShowDialog(true);
  };

  const handleDialogClose = (open: boolean) => {
    if (!open) {
      setShowDialog(false);
      setSelectedSite(null);
    }
  };

  const handlePageChange = (newPage: number) => {
    setPagination(prev => ({ ...prev, page: newPage }));
  };

  const handleLimitChange = (newLimit: string) => {
    setPagination(prev => ({ ...prev, limit: parseInt(newLimit), page: 1 }));
  };

  if (loading && sites.length === 0) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin" />
        <span className="ml-2">Loading sites...</span>
      </div>
    );
  }

  return (
    <Card className="mt-4">
      <CardContent className="p-6">
        {/* Header */}
        <div className="flex justify-between items-center mb-6">
          <div>
            <h2 className="text-2xl font-semibold">Site Assignments</h2>
            <p className="text-sm text-muted-foreground mt-1">
              Manage unique combinations of studies, facilities, and assigned personnel
            </p>
          </div>
          <Button onClick={() => { setSelectedSite(null); setShowDialog(true); }} disabled={submitting} data-testid="site-add-button">
            <Plus className="mr-2 h-4 w-4" />
            Add New Site
          </Button>
        </div>

        {/* Table */}
        <div className="flex-1 min-h-0">
          <div className="h-full rounded-lg border bg-card shadow-sm flex flex-col" data-testid="site-assignments-table">
            <div className="overflow-x-auto overflow-y-auto flex-1">
              {loading ? (
                <div className="flex justify-center items-center h-64">
                  <Loader2 className="h-8 w-8 animate-spin mx-auto mb-3 text-muted-foreground" />
                </div>
              ) : sites.length === 0 ? (
                <div className="flex justify-center items-center h-64">
                  <div className="text-center">
                    <MapPin className="w-12 h-12 text-muted-foreground mx-auto mb-4" />
                    <p className="text-sm font-medium">No sites found</p>
                    <p className="text-xs text-muted-foreground">
                      {selectedStudyId ? 'No sites for this study yet — add a new site' : 'Select a study to view its sites'}
                    </p>
                  </div>
                </div>
              ) : (
                <TooltipProvider>
                  <Table className="w-full">
                    <TableHeader className="sticky top-0 bg-card z-10 border-b">
                      <TableRow className="hover:bg-muted/50 h-9">
                        <TableHead className="text-xs h-9 py-2 w-[120px] sticky left-0 bg-card z-20 border-r">Site Code</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[250px] max-w-[250px]">Study</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[220px] max-w-[220px]">Facility</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[200px] max-w-[200px]">Personnel</TableHead>
                        <TableHead className="text-xs h-9 py-2 w-[100px]">Status</TableHead>
                        <TableHead className="text-xs h-9 py-2 text-right w-[100px] sticky right-0 bg-card z-20 border-l">Actions</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {sites.map((site: any) => (
                        <TableRow key={site._id || site.id || site.siteCode} className="group hover:bg-muted/50 transition-colors">
                          <TableCell className="py-2 sticky left-0 bg-background z-10 border-r">
                            <Badge variant="outline" className="font-mono text-[10px] h-5">{site.siteCode}</Badge>
                          </TableCell>
                          <TableCell className="py-2 w-[250px] max-w-[250px]">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <div className="flex items-center gap-2 min-w-0">
                                  <div className="w-5 h-5 rounded bg-slate-700 flex items-center justify-center flex-shrink-0">
                                    <FileText className="h-3 w-3 text-white" />
                                  </div>
                                  <span className="font-medium text-[11px] leading-tight truncate block min-w-0 flex-1">
                                    {site.studyTitle || 'N/A'}
                                  </span>
                                </div>
                              </TooltipTrigger>
                              {site.studyTitle && (
                                <TooltipContent side="top" className="max-w-sm">
                                  <p className="break-words">{site.studyTitle}</p>
                                </TooltipContent>
                              )}
                            </Tooltip>
                          </TableCell>
                          <TableCell className="py-2 w-[220px] max-w-[220px]">
                            <div className="flex items-center gap-2 min-w-0">
                              <div className="w-5 h-5 rounded bg-slate-700 flex items-center justify-center flex-shrink-0">
                                <Building2 className="h-3 w-3 text-white" />
                              </div>
                              <div className="min-w-0 flex-1 overflow-hidden">
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <div className="font-medium text-[11px] leading-tight truncate">
                                      {site.facilityName || 'N/A'}
                                    </div>
                                  </TooltipTrigger>
                                  {site.facilityName && (
                                    <TooltipContent side="top" className="max-w-sm">
                                      <p className="break-words">{site.facilityName}</p>
                                    </TooltipContent>
                                  )}
                                </Tooltip>
                                <div className="text-[10px] text-muted-foreground truncate mt-0.5">
                                  {site.facility?.location || 'N/A'} • {site.facility?.type || 'N/A'}
                                </div>
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="py-2 w-[200px] max-w-[200px]">
                            <div className="flex items-center gap-2 min-w-0">
                              <div className="w-5 h-5 rounded bg-slate-700 flex items-center justify-center flex-shrink-0">
                                <User2 className="h-3 w-3 text-white" />
                              </div>
                              <div className="min-w-0 flex-1 overflow-hidden">
                                <div className="font-medium text-[11px] leading-tight truncate">
                                  {site.principalInvestigatorName || 'N/A'}
                                </div>
                                <div className="text-[10px] text-muted-foreground truncate mt-0.5">
                                  {site.principalInvestigator?.role || 'N/A'}
                                </div>
                              </div>
                            </div>
                          </TableCell>
                          <TableCell className="py-2">
                            <Badge
                              variant="outline"
                              className={cn(
                                "text-[10px] h-5",
                                site.statusColor === 'green' && 'text-emerald-700 border-emerald-300 bg-emerald-50',
                                site.statusColor === 'yellow' && 'text-amber-700 border-amber-300 bg-amber-50',
                                site.statusColor === 'red' && 'text-red-700 border-red-300 bg-red-50'
                              )}
                            >
                              {site.status}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-right py-2 sticky right-0 bg-background z-10 border-l">
                            <div className="flex justify-end gap-1">
                              <Button
                                variant="ghost" size="sm"
                                className="h-7 w-7 p-0"
                                onClick={() => handleEdit(site)}
                                disabled={submitting}
                              >
                                <Pencil className="h-3.5 w-3.5" />
                              </Button>
                              <Button
                                variant="ghost" size="sm"
                                className="h-7 w-7 p-0"
                                onClick={() => handleDelete(site._id || site.id)}
                                disabled={submitting}
                              >
                                <Trash2 className="h-3.5 w-3.5 text-destructive" />
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TooltipProvider>
              )}
            </div>
          </div>
        </div>

        {/* Pagination */}
        {sites.length > 0 && pagination.pages > 1 && (
          <div className="flex items-center justify-between mt-4 pt-4 border-t">
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">Rows per page:</span>
                <Select value={pagination.limit.toString()} onValueChange={handleLimitChange}>
                  <SelectTrigger className="w-[70px] h-8 text-xs"><SelectValue /></SelectTrigger>
                  <SelectContent style={{ zIndex: 9999 }}>
                    <SelectItem value="10">10</SelectItem>
                    <SelectItem value="20">20</SelectItem>
                    <SelectItem value="50">50</SelectItem>
                    <SelectItem value="100">100</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="text-sm text-muted-foreground">
                Showing {((pagination.page - 1) * pagination.limit) + 1} to {Math.min(pagination.page * pagination.limit, pagination.total)} of {pagination.total} sites
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline" size="sm" className="h-8"
                onClick={() => handlePageChange(pagination.page - 1)}
                disabled={pagination.page === 1 || loading}
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <div className="flex items-center gap-1">
                {Array.from({ length: Math.min(5, pagination.pages) }, (_, i) => {
                  let pageNum: number;
                  if (pagination.pages <= 5) pageNum = i + 1;
                  else if (pagination.page <= 3) pageNum = i + 1;
                  else if (pagination.page >= pagination.pages - 2) pageNum = pagination.pages - 4 + i;
                  else pageNum = pagination.page - 2 + i;
                  return (
                    <Button
                      key={pageNum}
                      variant={pagination.page === pageNum ? "default" : "outline"}
                      size="sm" className="h-8 w-8 p-0"
                      onClick={() => handlePageChange(pageNum)}
                      disabled={loading}
                    >
                      {pageNum}
                    </Button>
                  );
                })}
              </div>
              <Button
                variant="outline" size="sm" className="h-8"
                onClick={() => handlePageChange(pagination.page + 1)}
                disabled={pagination.page >= pagination.pages || loading}
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        )}

        {/* Add/Edit Site Drawer */}
        <Sheet open={showDialog} onOpenChange={handleDialogClose}>
          <SheetContent
            side="right"
            className="w-full sm:max-w-2xl overflow-y-auto"
            onPointerDownOutside={(e) => e.preventDefault()}
          >
            <SheetHeader>
              <SheetTitle>{selectedSite ? 'Edit Site' : 'Add New Site'}</SheetTitle>
            </SheetHeader>
            <div className="mt-6">
              <SiteAssignmentForm
                site={selectedSite ? siteService.transformSiteForForm(selectedSite) : null}
                selectedStudyId={selectedStudyId}
                onSubmit={handleSaveSite}
                onCancel={() => { setShowDialog(false); setSelectedSite(null); }}
                submitting={submitting}
              />
            </div>
          </SheetContent>
        </Sheet>
      </CardContent>
    </Card>
  );
};

export default SiteAssignmentManagement;
