# Screenshots — what to capture and how

## Required sizes

### Apple App Store (mandatory)
| Device | Size (px, portrait) | How many |
|---|---|---|
| iPhone 6.9" (16 Pro Max / 15 Pro Max) | 1320 × 2868 | 3–10 (this set is reused for smaller iPhones) |
| iPad Pro 13" — only if you keep `supportsTablet: true` | 2064 × 2752 | 3–10 |

> `app.json` currently declares `supportsTablet: true`, so **iPad screenshots are
> required**. If you would rather not produce them, set it to `false` and rebuild.

### Google Play (mandatory)
| Asset | Size | Notes |
|---|---|---|
| Phone screenshots | min 1080 × 1920, 16:9 or 9:16 | 2–8 required |
| App icon | 512 × 512 PNG | flat, no transparency |
| Feature graphic | 1024 × 500 PNG/JPG | shown at the top of the listing |
| Tablet screenshots | 7" and 10" | optional, but needed for "Designed for tablets" |

## Shot list (same five for both stores, in this order)

1. **Home / dashboard** — take-home card, Self Assessment estimate and cash-flow
   chart visible. Caption: *"What you earned, what you owe, what's yours."*
2. **Tax screen** — a tax year selected, the estimate receipt showing.
   Caption: *"A live Self Assessment estimate, all year."*
3. **Invoice detail** — a finished invoice with the payment block.
   Caption: *"Invoices in under a minute."*
4. **Expenses with a receipt thumbnail** — ideally mid-scan.
   Caption: *"Photograph the receipt. That's the whole job."*
5. **Settings in dark mode** — shows theme, Face ID lock, card customisation.
   Caption: *"Yours to arrange. Light or dark."*

Use the seeded demo account so the numbers look real (`scripts/seed_demo.py`).

## Capturing them

**iOS** — run the production build on the iPhone 16 Pro Max simulator:
```bash
cd frontend
npx expo run:ios --device "iPhone 16 Pro Max" --configuration Release
# then ⌘S in the simulator, or:
xcrun simctl io booted screenshot ~/Desktop/asets-01.png
```
Simulator screenshots are already at the exact App Store resolution.

**Android** — Pixel 8 Pro emulator (1008 × 2244 → upscale, or use a 1080p profile):
```bash
adb exec-out screencap -p > ~/Desktop/asets-android-01.png
```

**Feature graphic (1024 × 500)** — the logo mark on the `#F6F9FC` background with
"ASETS — invoices, expenses, tax" in the brand blue `#3E6FA8`. Keep text away
from the outer 50 px; Play crops it on some surfaces.

## Rules that get screenshots rejected
- No device frames with a different phone's bezel on Apple's 6.9" slot.
- No HMRC logo, crest, or anything implying a government partnership.
- Nothing that reads as a guarantee ("never overpay tax again") — keep the word
  *estimate* visible in the tax screenshot.
- No real client names, real UTRs, or real bank details. Use the seeded data.
