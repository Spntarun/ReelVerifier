---
version: 1.0.0
name: ReelVerifier-Instagram-Design-System
description: A clean, modern design system for Reel Verifier inspired by Instagram's minimalist design language, mobile-first feed cards, Reels video player chrome, and story verification stickers. Built with light and dark mode tokens, subtle hairline borders, authentic Instagram gradients, and accessible typography.

brand:
  name: Reel Verifier
  voice: Clear, objective, trustworthy, and modern social fact-checking.
  inspiration: Instagram Reels, Threads, and Meta modern consumer interfaces.

colors:
  # Base Canvas & Surfaces
  canvas-light: "#FFFFFF"
  canvas-subtle-light: "#FAFAFA"
  surface-card-light: "#FFFFFF"
  surface-elevated-light: "#FFFFFF"
  hairline-light: "#DBDBDB"
  hairline-soft-light: "#EFEFEF"

  canvas-dark: "#000000"
  canvas-subtle-dark: "#121212"
  surface-card-dark: "#121212"
  surface-elevated-dark: "#1C1C1C"
  hairline-dark: "#262626"
  hairline-soft-dark: "#363636"

  # Core Brand & Interaction
  ig-blue: "#0095F6"
  ig-blue-hover: "#1877F2"
  ig-blue-subtle: "rgba(0, 149, 246, 0.1)"
  
  # Signature Instagram Gradient
  ig-gradient: "linear-gradient(45deg, #F58529, #FEDA77, #DD2A7B, #8134AF, #515BD4)"
  ig-gradient-story: "linear-gradient(135deg, #FD1D1D, #E1306C, #C13584, #833AB4)"
  ig-gradient-subtle: "linear-gradient(135deg, rgba(225, 48, 108, 0.08), rgba(129, 52, 175, 0.08))"

  # Typography & Text
  text-primary-light: "#000000"
  text-secondary-light: "#737373"
  text-muted-light: "#8E8E8E"
  
  text-primary-dark: "#F5F5F5"
  text-secondary-dark: "#A8A8A8"
  text-muted-dark: "#737373"

  # Verification Verdict Semantic Colors (Sticker Style)
  verdict-verified:
    bg: "#E8F9EE"
    bg-dark: "#0A2917"
    border: "#25D366"
    badge: "#00BA88"
    text: "#065F46"
    text-dark: "#4ADE80"
    label: "Verified"

  verdict-partial:
    bg: "#FFF9EB"
    bg-dark: "#2E1C03"
    border: "#F59E0B"
    badge: "#F59E0B"
    text: "#92400E"
    text-dark: "#FDE68A"
    label: "Partly matched"

  verdict-unverified:
    bg: "#F5F5F5"
    bg-dark: "#1F1F1F"
    border: "#8E8E8E"
    badge: "#737373"
    text: "#262626"
    text-dark: "#D4D4D4"
    label: "Couldn't verify"

  verdict-suspicious:
    bg: "#FEF2F2"
    bg-dark: "#300A0E"
    border: "#ED4956"
    badge: "#ED4956"
    text: "#991B1B"
    text-dark: "#FCA5A5"
    label: "Warning signs"

typography:
  font-family: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
  font-family-display: '"Plus Jakarta Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif'
  font-family-mono: '"JetBrains Mono", monospace'

  scales:
    title-xl: { size: "2.25rem", weight: 800, line-height: 1.2 }
    title-lg: { size: "1.75rem", weight: 700, line-height: 1.25 }
    title-md: { size: "1.25rem", weight: 700, line-height: 1.3 }
    body-lg:  { size: "1rem", weight: 400, line-height: 1.5 }
    body-md:  { size: "0.875rem", weight: 400, line-height: 1.4 }
    label-bold: { size: "0.875rem", weight: 600, line-height: 1.4 }
    caption: { size: "0.75rem", weight: 500, line-height: 1.3 }

components:
  buttons:
    primary:
      bg: "var(--ig-blue)"
      color: "#FFFFFF"
      hover: "var(--ig-blue-hover)"
      radius: "8px"
      padding: "8px 16px"
      font-weight: 600
    secondary:
      bg: "transparent"
      border: "1px solid var(--hairline)"
      color: "var(--text-primary)"
      hover: "var(--hairline-soft)"
      radius: "8px"
    gradient:
      bg: "var(--ig-gradient)"
      color: "#FFFFFF"
      radius: "20px"

  cards:
    radius: "16px"
    border: "1px solid var(--hairline)"
    shadow: "0 1px 2px rgba(0, 0, 0, 0.04)"
    padding: "20px"

  dropzone:
    style: "Instagram 'Create New Post' modal appearance"
    icon: "Instagram media frame outline with gradient dot"
    drag-hover-border: "var(--ig-blue)"
    radius: "16px"

  verdict-badge:
    style: "Instagram verified badge / alert pill"
    radius: "24px"
    font-weight: 700
    padding: "6px 14px"
---

