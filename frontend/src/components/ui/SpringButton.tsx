import React from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { calmSpring, pressScale } from './motion';

export type SpringButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'pill';

const VARIANT_CLASS: Record<SpringButtonVariant, string> = {
  primary:
    'bg-brand-blue text-white border border-brand-blue/80 shadow-lg shadow-brand-blue/20 hover:bg-brand-blue/90',
  secondary:
    'bg-white/[0.06] text-white border border-white/12 hover:bg-white/[0.1] hover:border-white/20',
  ghost:
    'bg-transparent text-apple-secondary border border-transparent hover:text-white hover:bg-white/[0.06]',
  danger:
    'bg-brand-red/15 text-brand-red border border-brand-red/30 hover:bg-brand-red/25',
  pill:
    'bg-apple-card text-apple-secondary border border-apple-border hover:text-white hover:border-white/25',
};

export interface SpringButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, 'onDrag' | 'onDragStart' | 'onDragEnd' | 'onAnimationStart'> {
  variant?: SpringButtonVariant;
  /** Compact height for dense toolbars */
  size?: 'sm' | 'md' | 'lg';
  children: React.ReactNode;
}

const SIZE_CLASS = {
  sm: 'min-h-[36px] px-3 text-[11px] rounded-xl gap-1.5',
  md: 'min-h-[44px] px-4 text-sm rounded-2xl gap-2',
  lg: 'min-h-[48px] px-6 text-sm rounded-2xl gap-2',
};

/**
 * Primary interactive control with instant pointer-down scale (calm spring).
 */
export default function SpringButton({
  variant = 'primary',
  size = 'md',
  className = '',
  disabled,
  children,
  type = 'button',
  ...rest
}: SpringButtonProps) {
  const reduceMotion = useReducedMotion();

  return (
    <motion.button
      type={type}
      disabled={disabled}
      whileTap={reduceMotion || disabled ? undefined : { scale: pressScale }}
      transition={calmSpring}
      className={[
        'inline-flex items-center justify-center font-semibold select-none',
        'transition-colors duration-150 outline-none',
        'focus-visible:ring-2 focus-visible:ring-brand-blue/60 focus-visible:ring-offset-2 focus-visible:ring-offset-black',
        'disabled:opacity-50 disabled:pointer-events-none',
        'cursor-pointer',
        VARIANT_CLASS[variant],
        SIZE_CLASS[size],
        className,
      ]
        .filter(Boolean)
        .join(' ')}
      {...rest}
    >
      {children}
    </motion.button>
  );
}
