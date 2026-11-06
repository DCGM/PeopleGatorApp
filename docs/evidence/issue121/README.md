# Scan sidebar evidence (#121)

Captured in Chromium from this issue branch with the real local API and Vite,
a fresh migrated PostgreSQL database and disposable local storage, after two
successful real seed CLI runs. All records and scans are synthetic. The page is
`scan-sidebar-1` with the Mentions tab scoped to **This page**.

| State | Desktop — 1440 × 900 CSS pixels | Mobile — 390 × 844 CSS pixels |
| --- | --- | --- |
| Light | ![Sidebar resized to 560px with the focused handle; long mention context wraps](desktop-light.png) | ![Stacked sidebar; long mention context wraps](mobile-light.png) |
| Dark | ![Default 400px sidebar with the focused handle in dark mode](desktop-dark.png) | ![Stacked sidebar in dark mode](mobile-dark.png) |

Desktop captures focus the **Resize sidebar** handle with the keyboard; the light
capture is dragged from the default 400px to about 560px. The app has no theme
toggle, so dark captures add the `dark` class to the document root.
