import * as React from 'react';
import { cn } from '@/lib/utils';
import { Checkbox } from '@/components/ui/checkbox';

export interface TreeItem {
  id: string;
  label: string;
  children?: TreeItem[];
}

export interface TreeProps {
  items: TreeItem[];
  selectedIds: string[];
  onSelectionChange: (selectedIds: string[]) => void;
  className?: string;
}

export function Tree({ items, selectedIds, onSelectionChange, className }: TreeProps) {
  const handleToggle = (id: string) => {
    if (selectedIds.includes(id)) {
      onSelectionChange(selectedIds.filter((item) => item !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  };

  const renderItems = (items: TreeItem[], level = 0) => {
    return items.map((item) => (
      <div key={item.id} style={{ marginLeft: `${level * 1.5}rem` }}>
        <div className="flex items-center gap-2 py-1">
          <Checkbox
            id={item.id}
            checked={selectedIds.includes(item.id)}
            onCheckedChange={() => handleToggle(item.id)}
          />
          <label
            htmlFor={item.id}
            className="text-sm font-medium leading-none cursor-pointer"
          >
            {item.label}
          </label>
        </div>
        {item.children && renderItems(item.children, level + 1)}
      </div>
    ));
  };

  return <div className={cn('space-y-1', className)}>{renderItems(items)}</div>;
}
