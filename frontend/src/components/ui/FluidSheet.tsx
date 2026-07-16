import React from 'react';
import { Drawer } from 'vaul';

export interface FluidSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  children: React.ReactNode;
  /** Accessible title for the sheet */
  title?: string;
  /** snug = max 55vh, tall = max 85vh */
  size?: 'snug' | 'tall';
  /** Optional footer pinned to bottom */
  footer?: React.ReactNode;
}

/**
 * Bottom drawer (Vaul) with glass surface and calm drag physics.
 * Use for detail panels that shouldn't fight the map/list above.
 */
export default function FluidSheet({
  open,
  onOpenChange,
  children,
  title,
  size = 'tall',
  footer,
}: FluidSheetProps) {
  const maxH = size === 'snug' ? 'max-h-[55vh]' : 'max-h-[85vh]';

  return (
    <Drawer.Root open={open} onOpenChange={onOpenChange} shouldScaleBackground={false}>
      <Drawer.Portal>
        <Drawer.Overlay className="fixed inset-0 z-[60] bg-black/55 backdrop-blur-[2px]" />
        <Drawer.Content
          className={`fixed bottom-0 left-0 right-0 z-[70] outline-none ${maxH} flex flex-col rounded-t-[28px] ui-glass ui-glass-strong border-t border-x border-white/12 shadow-[0_-20px_60px_rgba(0,0,0,0.55)]`}
        >
          <div className="flex justify-center pt-3 pb-1 shrink-0" aria-hidden>
            <div className="w-10 h-1 rounded-full bg-white/25" />
          </div>
          {title && (
            <Drawer.Title className="px-5 pb-2 text-sm font-bold text-white tracking-tight shrink-0">
              {title}
            </Drawer.Title>
          )}
          {/* Visually hidden description for a11y when title alone is used */}
          <Drawer.Description className="sr-only">
            {title ? `${title} details` : 'Detail sheet'}
          </Drawer.Description>
          <div className="flex-1 overflow-y-auto overscroll-contain px-4 sm:px-5 pb-4 min-h-0">
            {children}
          </div>
          {footer && (
            <div className="shrink-0 border-t border-white/10 px-4 sm:px-5 py-3 bg-black/30">
              {footer}
            </div>
          )}
        </Drawer.Content>
      </Drawer.Portal>
    </Drawer.Root>
  );
}
