import React from 'react';
import { useForm } from 'react-hook-form';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Button } from "@/components/ui/button";

const ArtifactDialog = ({ open, onClose, onSubmit }) => {
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm({
    defaultValues: {
      artifactNumber: '',
      artifactName: '',
      ichCode: '',
      isRequired: true,
      isActive: true
    }
  });

  const submitForm = async (data) => {
    await onSubmit(data);
    reset();
  };

  const handleClose = () => {
    reset();
    onClose();
  };

  return (
    <Sheet open={open} onOpenChange={handleClose}>
      <SheetContent side="right" className="w-full sm:max-w-md">
        <SheetHeader>
          <SheetTitle>Create New Artifact</SheetTitle>
          <SheetDescription>
            Add a new artifact to the selected section
          </SheetDescription>
        </SheetHeader>
        
        <div className="mt-6">
        <form onSubmit={handleSubmit(submitForm)} className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="artifactNumber">Artifact Number <span className="text-red-500">*</span></Label>
            <Input
              id="artifactNumber"
              placeholder="e.g., 1.1.1"
              {...register('artifactNumber', { required: 'Artifact number is required' })}
            />
            {errors.artifactNumber && (
              <p className="text-sm text-red-500">{errors.artifactNumber.message}</p>
            )}
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="artifactName">Artifact Name <span className="text-red-500">*</span></Label>
            <Input
              id="artifactName"
              placeholder="e.g., Trial Master Plan"
              {...register('artifactName', { required: 'Artifact name is required' })}
            />
            {errors.artifactName && (
              <p className="text-sm text-red-500">{errors.artifactName.message}</p>
            )}
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="ichCode">ICH Code</Label>
            <Input
              id="ichCode"
              placeholder="e.g., E6"
              {...register('ichCode')}
            />
          </div>
          
          <div className="flex items-center space-x-2">
            <Checkbox 
              id="isRequired" 
              defaultChecked={true}
              {...register('isRequired')}
            />
            <Label htmlFor="isRequired">Required</Label>
          </div>
          
          <div className="flex items-center space-x-2">
            <Checkbox 
              id="isActive" 
              defaultChecked={true}
              {...register('isActive')}
            />
            <Label htmlFor="isActive">Active</Label>
          </div>
          
          <SheetFooter className="mt-6 pt-4 border-t">
            <Button type="button" variant="outline" onClick={handleClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Creating...' : 'Create Artifact'}
            </Button>
          </SheetFooter>
        </form>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default ArtifactDialog;
