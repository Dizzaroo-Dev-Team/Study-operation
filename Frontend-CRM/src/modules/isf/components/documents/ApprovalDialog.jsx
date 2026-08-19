import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/components/ui/use-toast";
import isfClinicalTrialsService from '@/services/isfClinicalTrials.service';

const ApprovalDialog = ({ open, onClose, document, onApproved }) => {
  const [comments, setComments] = useState('');
  const [signature, setSignature] = useState('');
  const [loading, setLoading] = useState(false);
  const { toast } = useToast();
  const user = JSON.parse(localStorage.getItem('user')) || {};
  const approverId = user.id || 'demo-approver-id';
  const approverName = user.name || 'Demo Approver';

  const handleApprove = async () => {
    try {
      setLoading(true);
      await isfClinicalTrialsService.submitDocumentApproval(document._id, {
        approverId,
        approverName,
        status: 'APPROVED',
        comments,
        signature: signature || 'Signed by ' + approverName
      });
      toast({
        title: "Document Approved",
        description: "The document has been approved successfully.",
      });
      onApproved();
      onClose();
    } catch (error) {
      toast({
        title: "Error",
        description: error.message || "Failed to approve document",
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  };

  if (!open) return null;
  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Approve Document</DialogTitle>
          <DialogDescription>
            Review and approve the document: {document?.title || 'Untitled'}
          </DialogDescription>
        </DialogHeader>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Comments</label>
            <Textarea
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Enter approval comments..."
              className="min-h-[80px]"
            />
          </div>
          
          <div>
            <label className="block text-sm font-medium mb-1">Signature</label>
            <Textarea
              value={signature}
              onChange={(e) => setSignature(e.target.value)}
              placeholder="Enter your signature..."
              className="min-h-[60px]"
            />
          </div>
        </div>
        
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button type="button" onClick={handleApprove} disabled={loading}>
            {loading ? 'Approving...' : 'Approve'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export default ApprovalDialog;
