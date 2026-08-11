import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

/** Single stroke system: 1.6px, round caps, 20px grid. */
const base = {
  width: 18,
  height: 18,
  viewBox: '0 0 20 20',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
} as const

export const PenIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <path d="M13.2 3.6a1.7 1.7 0 0 1 2.4 2.4L7.3 14.3l-3.1.8.8-3.1 8.2-8.4Z" />
    <path d="M11.8 5 14.6 7.8" />
  </svg>
)

export const BookIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <path d="M4 4.6A1.6 1.6 0 0 1 5.6 3H16v12.4H5.6A1.6 1.6 0 0 0 4 17V4.6Z" />
    <path d="M4 15.4A1.6 1.6 0 0 1 5.6 13.8H16" />
    <path d="M7.4 6.6h5" />
  </svg>
)

export const NodeIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <circle cx="10" cy="4.6" r="2" />
    <circle cx="4.8" cy="14.6" r="2" />
    <circle cx="15.2" cy="14.6" r="2" />
    <path d="M8.7 6.4 6 12.7M11.3 6.4 14 12.7" />
  </svg>
)

export const GridIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <rect x="3.2" y="3.2" width="5.6" height="5.6" rx="1.4" />
    <rect x="11.2" y="3.2" width="5.6" height="5.6" rx="1.4" />
    <rect x="3.2" y="11.2" width="5.6" height="5.6" rx="1.4" />
    <rect x="11.2" y="11.2" width="5.6" height="5.6" rx="1.4" />
  </svg>
)

export const ChartIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <path d="M3.4 16.6h13.2" />
    <path d="M6 16.6v-4.4M10 16.6V6.2M14 16.6v-6.8" />
  </svg>
)

export const GearIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <circle cx="10" cy="10" r="2.4" />
    <path d="M10 2.8v1.8M10 15.4v1.8M17.2 10h-1.8M4.6 10H2.8M15.1 4.9l-1.3 1.3M6.2 13.8l-1.3 1.3M15.1 15.1l-1.3-1.3M6.2 6.2 4.9 4.9" />
  </svg>
)

/** Sliders — configuration you set, distinct from the gear that opens Settings. */
export const SlidersIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <path d="M3 5.6h4.4M11.2 5.6H17M3 14.4h5.8M12.6 14.4H17" />
    <circle cx="9.3" cy="5.6" r="1.9" />
    <circle cx="10.7" cy="14.4" r="1.9" />
  </svg>
)

export const CheckIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <path d="m4.6 10.4 3.3 3.3 7.5-7.5" />
  </svg>
)

export const ArrowIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <path d="M4 10h11M11 6l4 4-4 4" />
  </svg>
)

export const AiIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <path d="M10 3.2 11.5 7 15.3 8.5 11.5 10 10 13.8 8.5 10 4.7 8.5 8.5 7 10 3.2Z" />
    <path d="M15.2 13.4 15.8 15l1.6.6-1.6.6-.6 1.6-.6-1.6-1.6-.6 1.6-.6.6-1.6Z" />
  </svg>
)

export const AlertIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <circle cx="10" cy="10" r="6.8" />
    <path d="M10 6.6v4M10 13.2h.01" />
  </svg>
)

export const MicIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <rect x="7.5" y="2.5" width="5" height="9" rx="2.5" />
    <path d="M4.5 9a5.5 5.5 0 0 0 11 0" />
    <path d="M10 14.5v3M7.5 17.5h5" />
  </svg>
)

export const StopIcon = (props: IconProps) => (
  <svg {...base} {...props}>
    <rect x="5.5" y="5.5" width="9" height="9" rx="1.5" fill="currentColor" />
  </svg>
)
