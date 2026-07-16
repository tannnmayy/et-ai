import React from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { calmSpring, hoverScale, pressScale } from './motion';
import Glass, { type GlassVariant } from './Glass';

export interface MotionCardProps {
  children: React.ReactNode;
  className?: string;
  glass?: GlassVariant;
  /** Enable hover lift / press (default true for clickable cards) */
  interactive?: boolean;
  onClick?: () => void;
  role?: string;
  tabIndex?: number;
  'aria-label'?: string;
}

/**
 * Elevated glass card with optional calm hover/press feedback.
 */
export default function MotionCard({
  children,
  className = '',
  glass = 'subtle',
  interactive = true,
  onClick,
  role,
  tabIndex,
  'aria-label': ariaLabel,
}: MotionCardProps) {
  const reduceMotion = useReducedMotion();
  const clickable = Boolean(onClick) || interactive;

  return (
    <motion.div
      role={role ?? (onClick ? 'button' : undefined)}
      tabIndex={tabIndex ?? (onClick ? 0 : undefined)}
      aria-label={ariaLabel}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
      whileHover={
        clickable && !reduceMotion ? { scale: hoverScale, y: -2 } : undefined
      }
      whileTap={clickable && !reduceMotion ? { scale: pressScale } : undefined}
      transition={calmSpring}
      className={clickable ? 'cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-brand-blue/50 rounded-2xl' : undefined}
    >
      <Glass variant={glass} className={`rounded-2xl ${className}`.trim()}>
        {children}
      </Glass>
    </motion.div>
  );
}
