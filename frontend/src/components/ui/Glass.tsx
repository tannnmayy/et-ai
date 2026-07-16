import React from 'react';

export type GlassVariant = 'subtle' | 'strong' | 'floating' | 'solid';

const VARIANT_CLASS: Record<GlassVariant, string> = {
  /** Light elevation — list rows, secondary cards */
  subtle: 'ui-glass ui-glass-subtle',
  /** Primary elevated surfaces — main cards, panels */
  strong: 'ui-glass ui-glass-strong',
  /** Floating map overlays, tooltips, popovers */
  floating: 'ui-glass ui-glass-floating',
  /** Opaque dark card — no blur (dense lists / performance) */
  solid: 'bg-apple-card/90 border border-apple-border',
};

export interface GlassProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: GlassVariant;
  /** Extra rounded corners (default: rounded-2xl via class) */
  as?: 'div' | 'section' | 'aside' | 'article';
  children: React.ReactNode;
}

/**
 * Selective glassmorphism surface for hierarchy / elevation.
 * Prefer solid backgrounds for full-page chrome; use Glass for cards & panels.
 */
export default function Glass({
  variant = 'subtle',
  as: Tag = 'div',
  className = '',
  children,
  ...rest
}: GlassProps) {
  return (
    <Tag className={`${VARIANT_CLASS[variant]} ${className}`.trim()} {...rest}>
      {children}
    </Tag>
  );
}
