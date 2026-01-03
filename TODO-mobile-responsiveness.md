# Mobile Responsiveness Implementation Plan

## Overview

Make the Messenger Archive web app mobile-friendly by implementing a collapsible sidebar with slide-in animation.

## Current Issues

1. **Sidebar is always visible** (`w-64` fixed) - takes up 256px on all screen sizes
2. **Header search is fixed width** (`w-80` = 320px) - too wide for mobile
3. **Room selector has min-width** (`min-w-[180px]`) - combined with search = ~500px minimum
4. **No hamburger menu** - no way to toggle sidebar on mobile
5. **Main content padding** (`p-6`) - 24px is excessive on small screens

## Design Decisions

- **Search**: Keep in header, make full-width on mobile
- **Room selector**: Move to sidebar
- **Dark mode toggle**: Move to sidebar
- **Logout button**: Move to sidebar
- **Navigation pattern**: Slide-in sidebar from left (drawer pattern)
- **Backdrop**: Semi-transparent black (`bg-black/50`)

## Files to Change

| File | Action | Description |
|------|--------|-------------|
| `web/src/contexts/sidebar-context.tsx` | **CREATE** | Context for sidebar open/closed state |
| `web/src/app/layout.tsx` | **EDIT** | Wrap app with SidebarProvider |
| `web/src/components/layout/app-layout.tsx` | **EDIT** | Add mobile sidebar overlay/backdrop logic |
| `web/src/components/layout/sidebar.tsx` | **EDIT** | Add room selector, dark mode, logout, close button; make slide-in responsive |
| `web/src/components/layout/header.tsx` | **EDIT** | Add hamburger menu; remove room selector, dark mode, logout; make search full-width |

## Implementation Details

### 1. `sidebar-context.tsx` (NEW)

Simple context with:
- `isOpen: boolean`
- `open(): void`
- `close(): void`
- `toggle(): void`

### 2. `layout.tsx`

- Import and wrap with `<SidebarProvider>`

### 3. `header.tsx`

**Remove:**
- Room selector dropdown (entire component)
- Dark mode toggle button
- Logout button

**Add:**
- Hamburger menu button (left side, `md:hidden`)

**Modify:**
- Search: change `w-80` → `flex-1 max-w-xl` (full width on mobile, capped on desktop)

**Mobile layout:**
```
[☰] [🔍 Search messages...              ]
```

**Desktop layout:**
```
[🔍 Search messages...    ]              
```

### 4. `sidebar.tsx`

**New structure:**
```
┌─────────────────────┐
│ Messenger Archive [X]│  ← X only on mobile (md:hidden)
├─────────────────────┤
│ [Room Selector ▼]   │  ← moved from header
├─────────────────────┤
│ # Current Room      │
│   8,544 messages    │
├─────────────────────┤
│ Dashboard           │
│ Search              │
│ Messages            │
│ ...                 │
├─────────────────────┤
│ [☀/🌙] Dark Mode    │  ← moved from header
│ [→] Logout          │  ← moved from header
└─────────────────────┘
```

**Behavior:**
- Clicking any nav link → calls `close()` on mobile
- Close button (X) visible only on mobile
- Responsive slide-in animation with transform

### 5. `app-layout.tsx`

**Structure:**
```tsx
<div className="flex h-screen">
  {/* Backdrop - mobile only, when sidebar open */}
  {isOpen && (
    <div 
      className="fixed inset-0 bg-black/50 z-40 md:hidden" 
      onClick={close}
    />
  )}
  
  {/* Sidebar - slides in on mobile */}
  <div className={cn(
    "fixed inset-y-0 left-0 z-50 w-64 transform transition-transform duration-200 md:relative md:translate-x-0",
    isOpen ? "translate-x-0" : "-translate-x-full"
  )}>
    <Sidebar />
  </div>
  
  {/* Main content */}
  <div className="flex flex-1 flex-col overflow-hidden">
    <Header />
    <main className="flex-1 overflow-auto p-4 md:p-6">{children}</main>
  </div>
</div>
```

## Implementation Order

1. [x] Create `sidebar-context.tsx`
2. [x] Update `layout.tsx` (add provider)
3. [x] Update `header.tsx` (add hamburger, remove other elements, responsive search)
4. [x] Update `sidebar.tsx` (add room selector, dark mode, logout, close button, nav click closes)
5. [x] Update `app-layout.tsx` (add backdrop, wire up sidebar visibility)
6. [ ] Test on mobile viewport
7. [ ] Deploy
