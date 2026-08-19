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

const SectionDialog = ({ open, parentId, onClose, onSubmit }) => {
  const { register, handleSubmit, reset, formState: { errors, isSubmitting } } = useForm({
    defaultValues: {
      sectionNumber: '',
      sectionName: '',
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
          <SheetTitle>Create New Section</SheetTitle>
          <SheetDescription>
            Add a new section to the selected zone
          </SheetDescription>
        </SheetHeader>
        
        <div className="mt-6">
        <form onSubmit={handleSubmit(submitForm)} className="space-y-4">
          <div className="grid gap-2">
            <Label htmlFor="sectionNumber">Section Number <span className="text-red-500">*</span></Label>
            <Input
              id="sectionNumber"
              placeholder="e.g., 1.1"
              {...register('sectionNumber', { required: 'Section number is required' })}
            />
            {errors.sectionNumber && (
              <p className="text-sm text-red-500">{errors.sectionNumber.message}</p>
            )}
          </div>
          
          <div className="grid gap-2">
            <Label htmlFor="sectionName">Section Name <span className="text-red-500">*</span></Label>
            <Input
              id="sectionName"
              placeholder="e.g., Project Management"
              {...register('sectionName', { required: 'Section name is required' })}
            />
            {errors.sectionName && (
              <p className="text-sm text-red-500">{errors.sectionName.message}</p>
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
              {isSubmitting ? 'Creating...' : 'Create Section'}
            </Button>
          </SheetFooter>
        </form>
        </div>
      </SheetContent>
    </Sheet>
  );
};

export default SectionDialog;
