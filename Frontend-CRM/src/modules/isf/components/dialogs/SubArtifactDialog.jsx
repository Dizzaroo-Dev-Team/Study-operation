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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const SubArtifactDialog = ({ open, parentId, onClose, onSubmit }) => {
  const { register, handleSubmit, reset, formState: { errors, isSubmitting }, setValue, watch } = useForm({
    defaultValues: {
      subArtifactName: '',
      isRequired: true,
      isActive: true,
    }
  });

  const submitForm = async (data) => {
    // Transform placeholders string to array
    
    const formattedData = {
      ...data,
      
    };
   
    await onSubmit(formattedData);
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
          <SheetTitle>Create New Sub-Artifact</SheetTitle>
          <SheetDescription>
            Add a new sub-artifact to the selected artifact
          </SheetDescription>
        </SheetHeader>
        
        <div className="mt-6">
        <form onSubmit={handleSubmit(submitForm)} className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="subArtifactName">Sub-Artifact Name <span className="text-red-500">*</span></Label>
            <Input
              id="subArtifactName"
              placeholder="e.g., Site Management Plan"
              {...register('subArtifactName', { required: 'Sub-artifact name is required' })}
            />
            {errors.subArtifactName && (
              <p className="text-sm text-red-500">{errors.subArtifactName.message}</p>
            )}
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
              {isSubmitting ? 'Creating...' : 'Create Sub-Artifact'}
            </Button>
          </SheetFooter>
        </form>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default SubArtifactDialog;
