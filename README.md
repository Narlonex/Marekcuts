# MAREK CUTS — premium barber shop website

A premium, fully responsive barber-shop website for **Marek Cuts**.

It is **built with Python and deployed as pure static files**. `build.py` reads
your content, prepares the assets and renders `dist/` — plain HTML5, CSS3 and
vanilla JavaScript. The deployed site needs **no** Python server, no Flask, no
Django, no FastAPI, no Node backend, no database and no API. You can delete
Python entirely after a build and the site still works.

```
content/  ──►  build.py  ──►  dist/  ──►  Render Static Site
 (you edit)     (Python)      (deploy)
```

---

## Table of contents

1. [Project overview](#1-project-overview)
2. [Tech stack](#2-tech-stack)
3. [Quick start](#3-quick-start)
4. [Editing business information](#4-editing-business-information)
5. [Updating the logo](#5-updating-the-logo)
6. [Replacing the photography](#6-replacing-the-photography)
7. [Services, prices and durations](#7-services-prices-and-durations)
8. [Opening hours](#8-opening-hours)
9. [Testimonials](#9-testimonials--demo-content)
10. [How the booking system works](#10-how-the-booking-system-works)
11. [Language system](#11-language-system-sk--en)
12. [Legal pages and cookies](#12-legal-pages-and-cookies)
13. [Deploying to Render](#13-deploying-to-render)
14. [Image attributions](#14-image-attributions)
15. [Accessibility, performance and SEO](#15-accessibility-performance-and-seo)
16. [Project structure](#16-project-structure)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Project overview

Marek Cuts is a modern barber shop site with a single long-scrolling page plus
four legal pages. It covers: a cinematic hero, a brand story, a service menu
with demo pricing, a photo gallery with a lightbox, testimonials, a six-step
booking wizard with a custom calendar, contact details, opening hours, a map
placeholder and a full legal section.

**Everything is demo-safe by design.** This is an MVP: there is no backend, the
booking system simulates the confirmation, and all testimonials and prices are
clearly marked as demo content. Nothing on the site claims a booking was really
created, and no invented business data (address, phone, email, IČO) is ever
published — those stay visible `[PLACEHOLDERS]` until you fill them in.

---

## 2. Tech stack

| Layer | What is used |
| --- | --- |
| Build / generation | **Python 3** (standard library only — no `pip install`) |
| Output | **HTML5**, **CSS3**, **vanilla JavaScript** (no framework, no bundler) |
| Fonts | Spectral (display) + Inter (body), self-hosted woff2 |
| Icons | Inline SVG sprite in the page |
| Hosting | Any static host — Render Static Sites, Netlify, GitHub Pages, S3 |

`build.py` imports nothing outside the Python standard library. In particular it
does **not** need Pillow: image trimming, scaling, alpha compositing and PNG
re-encoding are implemented with `zlib` + `struct`.

JavaScript is split into six readable modules under `src/js/` and concatenated
into a single `dist/script.js` at build time (one request, no bundler):

| Module | Responsibility |
| --- | --- |
| `01-core.js` | DOM helpers, i18n engine, formatting, scroll reveal, focus traps |
| `02-nav.js` | Sticky header, scrollspy, smooth scrolling, mobile drawer |
| `03-gallery.js` | Gallery lightbox (keyboard, touch, wrap-around) |
| `04-reviews.js` | Testimonial carousel with dots on small screens |
| `05-booking.js` | The demo booking wizard, calendar and validation |
| `06-consent.js` | Cookie consent banner, preferences modal, `mcConsent` API |

### Typography

Two families, with a deliberately strict division of labour:

| Family | Used for | Not used for |
| --- | --- | --- |
| **Spectral** (display) | Hero headline, section titles, step titles, legal titles, service names and prices, drawer links | Body copy, labels, prices inside the wizard, hour rows |
| **Inter** (body/UI) | Everything else: body copy, buttons, nav, form fields, calendar, summary values, cards, hour rows | — |

The display serif is reserved for **large headings only** (roughly 1.3rem and up).
Small text — prices in the picker, review names, hour rows, summary values — uses
Inter, because a high-contrast serif loses its thin strokes at those sizes and
becomes genuinely hard to read. The design system therefore uses the serif where
it reads as premium, and the sans where legibility matters more than flourish.

To change either family:

1. update `FONT_CSS_URL` in `build.py` (request only the weights you actually
   use — the display family is currently needed at just 400 and 600);
2. update `--font-display` / `--font-body` in `:root` in `src/styles.css`;
3. run `python build.py --refresh`. Orphaned woff2 files from the previous
   family are pruned automatically.

---

## 3. Quick start

Requirements: **Python 3.9+** (tested on 3.14). Nothing else.

```bash
# from the project root
python build.py
```

That single command:

1. validates `content/*.json`;
2. trims `assets-src/logo.png`, builds favicons, downloads and self-hosts the
   fonts, and downloads the photos at three widths each;
3. writes the finished site to `dist/`.

Then open it:

```bash
python -m http.server 8080 --directory dist
# → http://127.0.0.1:8080
```

> Open the site through a local server rather than double-clicking the HTML
> file. `file://` blocks the relative font and image requests in some browsers,
> and the language preference uses `localStorage`.

### Build flags

| Command | Effect |
| --- | --- |
| `python build.py` | Incremental build. Reuses anything already downloaded. |
| `python build.py --refresh` | Re-downloads every remote asset (fonts, photos). |
| `python build.py --offline` | Never touches the network; fails if an asset is missing. |
| `python build.py --clean` | Deletes `dist/` and `.cache/` first, then builds. |

**Deploy `dist/` — not the project root.** Everything the host needs is inside
`dist/`.

### Where the editing happens

```
content/        ← you edit these
templates/      ← HTML shell ({{TOKENS}})
src/styles.css  ← the design system
src/js/*.js     ← behaviour
assets-src/     ← your logo (and your own photos, if you prefer)
build.py        ← the builder
dist/           ← GENERATED, never edit by hand
```

Rebuild after every change. `build.py` **overwrites** `dist/`.

---

## 4. Editing business information

**All business data lives in one file: [`content/business.json`](content/business.json).**
It feeds the page, the meta tags, the Open Graph tags, the JSON-LD and the legal
pages, so there is exactly one place to edit and no risk of the values drifting
apart.

```json
{
  "businessName": "Marek Cuts",
  "address": "[BARBER SHOP ADDRESS]",
  "addressLines": ["[STREET AND NUMBER]", "[POSTAL CODE, CITY]"],
  "phone": "[PHONE NUMBER]",
  "email": "[EMAIL ADDRESS]",
  "instagram": "[INSTAGRAM URL]",
  "facebook": "[FACEBOOK URL]",
  "tiktok": "[TIKTOK URL]",
  "siteUrl": "https://example.com/"
}
```

| What you want to change | Where |
| --- | --- |
| Shop name | `businessName` |
| Address (contact card, map card, footer) | `address`, `addressLines` |
| Phone | `phone` |
| Email | `email` |
| Social links | `instagram`, `facebook`, `tiktok` |
| Real domain (canonical, sitemap, Open Graph) | `siteUrl` |
| Browser bar colour | `themeColor` |
| Footer copyright year | `copyrightYear` |
| Legal operator details | `legal.*` |

### Placeholders are intentional

Anything still written as `[LIKE THIS]` is treated as *unfilled*. The build
prints every remaining placeholder at the end, and the UI degrades honestly:

* **Social links** render as dimmed, non-clickable icons with a tooltip instead
  of pretending to be real profiles.
* **Phone and email** render as plain text, not as `tel:`/`mailto:` links.
* **JSON-LD structured data omits `address`, `telephone` and `email`** while they
  are placeholders, so no invented business data is ever published in a form
  that search engines or AI assistants will read back as fact.
* The address card and opening hours carry a visible note that the bracketed
  details are placeholders.

Replace them with real values and the site starts linking and emitting them
automatically.

For the map, `content/business.json` also drives the "Open in Google Maps" link.
To embed a real map, follow the commented instructions inside the `.map` block in
`templates/index.html` — load the iframe **after consent**, because Google Maps
sets its own cookies.

---

## 5. Updating the logo

Replace **`assets-src/logo.png`** with your logo and rebuild.

```bash
cp my-new-logo.png assets-src/logo.png
python build.py
```

The build then, automatically:

* trims the transparent padding so the lock-up has predictable proportions;
* fades the crop edge so the soft glow behind the mark never ends in a hard
  rectangle;
* writes two sizes — `dist/assets/logo.png` (hero, sized for the largest place
  it is displayed) and `dist/assets/logo-sm.png` (header, mobile drawer, footer,
  where a 630px-wide file would be wasted bytes);
* generates `favicon.svg`, `favicon-32.png`, `favicon-96.png` and
  `apple-touch-icon.png`, compositing the monogram onto an ink plate — necessary
  because the supplied mark is ivory on transparency and would otherwise be
  invisible in a light browser tab.

Requirements for the file: **8-bit RGBA PNG with a transparent background**. If
you supply something else the build stops with a clear message instead of
producing a broken logo.

Two knobs, if you want to trade fidelity against weight:

| Constant in `build.py` | Default | Meaning |
| --- | --- | --- |
| `LOGO_HERO_MAX_HEIGHT` | `372` | Hero artwork height in px (2× the 186px CSS display size) |
| `LOGO_SM_HEIGHT` | `120` | Small lock-up height (≈2.5× of the 46px header display) |

---

## 6. Replacing the photography

Every image is described in **[`content/gallery.json`](content/gallery.json)**.

Each entry has a list of candidate `sources`. The builder downloads the first
one that works and **falls back to the next if a URL dies**, so a dead link can
never break your build. Each image is downloaded at three widths, which the HTML
then offers through `srcset`/`sizes` so phones fetch a small file and desktops a
large one.

```json
{
  "id": "g1",
  "role": "gallery",
  "span": "tall",
  "alt": { "sk": "Barber strihá klienta strojčekom", "en": "Barber cutting a client's hair" },
  "sources": [{ "url": "https://images.unsplash.com/photo-…" }]
}
```

* `role` — `hero`, `about` or `gallery`.
* `span` — `normal`, `tall` or `wide` (drives the gallery grid composition).
* `alt` — **required**, in both Slovak and English. It is used for the `alt`
  attribute, the lightbox caption and the zoom button's accessible name.

**The best option is to use the shop's own photos.** Put them in `assets-src/`
and point `sources` at the local path; `build.py` copies local files instead of
downloading them.

Attribute every photo you use — see
[Image attributions](#14-image-attributions).

Download quality is set by `qualities.download` in `content/gallery.json`
(default `78`). Lower it to shrink the files.

---

## 7. Services, prices and durations

Edit **[`content/services.json`](content/services.json)**:

```json
{
  "id": "skin-fade",
  "icon": "clipper",
  "price": 26,
  "duration": 45,
  "sk": { "name": "Skin Fade", "description": "Čistý a precízny fade strih…" },
  "en": { "name": "Skin Fade", "description": "Clean and precise fade…" }
}
```

* `id` — used by the booking wizard to preselect the service. **Must be unique.**
* `icon` — one of `scissors`, `clipper`, `razor`, `beard`, `comb`, `head`
  (all present in the SVG sprite).
* `price` / `duration` — numbers only, no symbols. Currency comes from
  `currency`; the € symbol is placed correctly per language (`22 €` in Slovak,
  `€22` in English).

Adding or removing an entry updates the service grid **and** the booking
wizard's service list at the same time — they are generated from this one file.

Prices ship as clearly-labelled demo values. The page shows a visible note that
they are illustrative, and JSON-LD deliberately publishes service names without
prices so demo prices are never indexed as real ones.

---

## 8. Opening hours

Edit the `days` array in **[`content/hours.json`](content/hours.json)**.

Times ship as `XX:XX` on purpose: real opening hours are business data and must
not be invented. Change `displayPlaceholder` (or give individual days their own
values), set `"closed": true` for closed days, and the table renders the
localised "Closed"/"Zatvorené" label automatically.

> `hours.json` is what the site *displays*. `availability.json` is what the demo
> booking calendar *offers*. After launch, mirror your real hours into
> `availability.json` so the two agree.

---

## 9. Testimonials — demo content

> **These are fictional reviews for layout purposes.**
> They are **not** verified reviews and the section never claims they are
> customers. Replace them with real reviews before public launch.

Edit `items` in **[`content/testimonials.json`](content/testimonials.json)**.
Each entry needs `name`, `rating` (1–5), a `date`, an optional `service`, and the
review text in `sk` and `en`. Ten demo reviews ship by default, deliberately
varied in length and tone.

The section contains no fake Google badges, no invented star averages, no
customer counts and no "verified" icons. Each card carries a small **Demo** tag,
and a visible note under the grid states that the reviews are illustrative.

The component renders as a responsive grid on desktop and a swipeable carousel
with dots and arrow buttons below 1024px.

---

## 10. How the booking system works

### It is a demo — and it says so

`submitBooking()` is a clearly-named **simulation**. It waits briefly so the
button feels real, then shows the confirmation screen. It **never** sends a
request anywhere: a build-time check greps the generated `script.js` for
`fetch(`, `XMLHttpRequest`, `sendBeacon`, `EventSource` and `WebSocket` and fails
the build if any of them appear outside a comment.

The confirmation screen, the wizard disclaimer, the booking terms page and the
README all state plainly:

> *Toto je demo rezervačný systém. Skutočná rezervácia nebola vytvorená.*
> *This is a demo booking system. No real appointment has been created.*

Nothing is stored on a server. The only thing kept is a draft of the wizard in
the visitor's own browser (`localStorage` key `mc-booking`), which is deleted the
moment a booking is confirmed or the visitor starts a new one.

### The six steps

1. **Service** — pick one. The ✓/highlight and the summary update immediately.
2. **Date** — a custom calendar, not a browser `<input type="date">`.
3. **Time** — slots are generated from `availability.json`.
4. **Details** — name, email, phone, optional note + the required GDPR consent.
5. **Review** — a full summary, with an **Edit** button on every row that jumps
   back to the relevant step.
6. **Confirmation** — the demo success screen.

### Configuring availability

**[`content/availability.json`](content/availability.json)** is the whole
configuration:

| Key | Meaning |
| --- | --- |
| `slotStart`, `slotEnd` | The opening and closing time of the working day |
| `slotStepMinutes` | Slot granularity (30 → 09:00, 09:30, 10:00 …) |
| `leadTimeMinutes` | Hide slots too close to now (e.g. 120 = nothing within 2 hours) |
| `windowDays` | How far ahead bookings can be made |
| `closedWeekdays` | Closed days, `Date.getDay()` numbering (`0` = Sunday) |
| `blackoutDates` | ISO dates shown as fully booked (holidays, days off) |
| `busyRatio` | Fraction of otherwise-free slots hidden, to demonstrate unavailable slots |
| `weekdayBusyRatio` | Per-weekday override, e.g. `{"6": 0.5}` for a busier Saturday |
| `explicitUnavailable` | Hand-pick exact date/time slots to block |
| `seed` | Seeds the pseudo-random generator |

The generator is **seeded**, so the same date always produces the same pattern —
available slots do not shuffle on every reload.

### Connecting a real backend later

The JavaScript is structured so this is a small, contained change:

* the public API is already exposed as **`window.MarekCutsBooking`**, with
  `getAvailableDates()`, `getAvailableTimes()`, `selectService()`,
  `selectDate()`, `selectTime()`, `validateBooking()`, `submitBooking()`,
  `getState()` and `reset()`;
* central configuration is already available as `window.siteConfig`,
  `window.services`, `window.openingHours`, `window.availability`,
  `window.testimonials`, `window.gallery` and `window.translations`;
* inside `submitBooking()` there is a commented `TODO (real backend)` block
  showing exactly which `fetch(...)` call to drop in. Nothing else in the file
  needs to change.

Since the build refuses to ship with a live network call in `script.js`, you will
get that check out of the way deliberately when you wire up the endpoint.

---

## 11. Language system (SK / EN)

Slovak is the default. The SK | EN switcher sits in the header (and in the mobile
drawer) and stores the choice in `localStorage` (`mc-lang`), so it survives
reloads and carries across pages — including the legal ones.

Two mechanisms cooperate, and the split matters:

* **Static strings — `content/i18n.json`** (`content/i18n.json`, ~215 keys).
  Translated at runtime by swapping text on elements carrying `data-i18n="key"`
  or `data-i18n-attr="attr:key"`. The `{placeholders}` in a value are filled from
  `data-i18n-vars='{"n": 1}'`.
* **Content generated from the other content files** — service names, review
  texts, hour rows, legal documents. These are rendered **twice**, in both
  languages, and CSS shows only the active one
  (`html[data-lang="sk"] [data-lang-text="en"] { display: none }`).

Because of that split, **the Slovak copy is baked into the HTML**. The site is
readable and complete with JavaScript disabled — only the interactive wizard and
the language switcher need it.

To add a string: add it to `content/i18n.json` with both an `sk` and an `en`
value, then reference it from a template. The build fails if a template
references a key that is missing or has an empty translation in either language.

---

## 12. Legal pages and cookies

Four legal pages are included, each fully bilingual:

| Page | URL |
| --- | --- |
| Privacy Policy | `legal/privacy.html` |
| GDPR / Personal Data Processing | `legal/gdpr.html` |
| Cookie Policy | `legal/cookies.html` |
| Booking Terms & Conditions | `legal/terms.html` |

They are generated from [`content/legal/*.json`](content/legal/) and linked from
the footer. The text lives in JSON, so you can edit it without touching HTML.

> ### ⚠️ These legal documents are templates
>
> They must be **reviewed and customised by the actual business / operator — ideally
> with legal advice — before public launch.** Adding these pages does **not** by
> itself make a website legally compliant.
>
> Every page displays this warning to the reader, and the build keeps `legalName`,
> `legalAddress`, `companyId`, `email` and `phone` as visible
> `[PLACEHOLDERS]` — these are never invented.

### Cookie consent

The banner offers **Accept all / Reject / Settings**, with a preferences modal
for the *Analytics* and *Marketing* categories.

**No analytics or marketing tool is bundled.** Essential storage (the chosen
language and the consent record itself) works without any consent, because the
site is unusable without it. The other categories default to **off**.

To add a tool later, gate it on consent:

```js
window.mcConsent.onGrant('analytics', function () {
  // load your analytics script here
});
```

The callback runs immediately if consent was already given, and otherwise waits.
Bump `VERSION` in `src/js/06-consent.js` when the policy changes to re-ask
everyone. `window.mcConsent` also exposes `has()`, `all()`, `open()` and
`clear()`.

---

## 13. Deploying to Render

`render.yaml` in this repository describes the static site, so you can deploy it
as a Blueprint. The manual route works the same way.

### 1. Put the project on GitHub

```bash
git init
git add .
git commit -m "Marek Cuts — initial site"
git branch -M main
git remote add origin https://github.com/<you>/marek-cuts.git
git push -u origin main
```

`dist/` and `.cache/` are ignored by `.gitignore`. Decide how you want to handle
that:

* **Recommended — let Render build it.** Commit the sources and follow step 3
  below; Render runs `python build.py` for you on every push.
* **Or commit the output.** Remove `dist/` from `.gitignore` and commit it, then
  publish `dist` with no build command at all. Simpler, but the assets are
  checked in and the site only changes when you rebuild locally.

### 2. Create the service

1. Sign in to <https://dashboard.render.com>.
2. **New → Static Site**.
3. Connect your GitHub account and select the repository.

### 3. Settings

| Setting | Value |
| --- | --- |
| **Branch** | `main` |
| **Root Directory** | *(leave empty if the repo root is the project root)* |
| **Build Command** | `python build.py` |
| **Publish Directory** | `dist` |

That is the whole configuration. **Do not** create a web service, and **do not**
run a Python server — Render only needs to run the build once and then serve the
files in `dist`.

### 4. Deploy

Press **Create Static Site**. Render runs the build, then serves the contents of
`dist` from its CDN.

### 5. Afterwards

* Point your domain at it under **Settings → Custom Domains**.
* Update `siteUrl` in `content/business.json` to the final domain and rebuild, so
  the canonical URL, `sitemap.xml`, `robots.txt` and the Open Graph URLs are
  correct.
* The build emits a `_headers` file (nosniff, referrer policy and long-lived
  caching for fonts and images), which Render reads automatically.

The build also writes `sitemap.xml` and `robots.txt` into `dist/`.

---

## 14. Image attributions

The demo photography comes from **Unsplash** and **Pexels**, whose licences allow
free commercial use without attribution. Attribution is still recorded here as
good practice, and because you should replace these images with the shop's own
photography anyway.

Each entry downloads from its **first** listed source; the ordered fallbacks are
in `content/gallery.json`.

| Entry | Role | Source | URL |
| --- | --- | --- | --- |
| `hero` | hero | Unsplash | https://images.unsplash.com/photo-1503951914875-452162b0f3f1 |
| `about` | about | Unsplash | https://images.unsplash.com/photo-1600948836101-f9ffda59d250 |
| `g1` | gallery | Unsplash | https://images.unsplash.com/photo-1622286342621-4bd786c2447c |
| `g2` | gallery | Unsplash | https://images.unsplash.com/photo-1599351431202-1e0f0137899a |
| `g3` | gallery | Unsplash | https://images.unsplash.com/photo-1585747860715-2ba37e788b70 |
| `g4` | gallery | Unsplash | https://images.unsplash.com/photo-1517832606299-7ae9b720a186 |
| `g5` | gallery | Unsplash | https://images.unsplash.com/photo-1596728325488-58c87691e9af |
| `g6` | gallery | Unsplash | https://images.unsplash.com/photo-1503443207922-dff7d543fd0e |
| `g7` | gallery | Unsplash | https://images.unsplash.com/photo-1605497788044-5a32c7078486 |
| `g8` | gallery | Unsplash | https://images.unsplash.com/photo-1580618672591-eb180b1a973f |
| `g9` | gallery | Unsplash | https://images.unsplash.com/photo-1634449571010-02389ed0f9b0 |
| `g10` | gallery | Unsplash | https://images.unsplash.com/photo-1532710093739-9470acff878f |
| `g11` | gallery | Unsplash | https://images.unsplash.com/photo-1512690459411-b9245aed614b |
| `g12` | gallery | Unsplash | https://images.unsplash.com/photo-1493256338651-d82f7acb2b38 |

`assets-src/logo.png` is the supplied Marek Cuts logo and is the only real brand
asset in the project.

---

## 15. Accessibility, performance and SEO

**Accessibility**

* Semantic landmarks: `header`, `nav`, `main`, `section`, `footer`, one `<h1>`
  and a proper heading hierarchy.
* A skip link, visible focus rings, and labelled form fields.
* Modals (lightbox, cookie preferences, mobile drawer) trap focus, restore it on
  close, close on `ESC`, and lock background scrolling.
* The calendar and time slots are real buttons with `aria-disabled` (so they stay
  reachable) and localised accessible names — the calendar uses a roving
  `tabindex`, so it is fully keyboard operable.
* Validation errors are announced with `role="alert"` and linked via
  `aria-describedby`; the wizard announces step changes through an
  `aria-live` region.
* `prefers-reduced-motion: reduce` disables the reveal animations, smooth
  scrolling, hover transforms and the hero image zoom.
* A `<noscript>` notice explains that the interactive calendar needs JavaScript
  and points to phone and email instead.

**Performance**

* No framework, no bundler, no runtime dependencies.
* One CSS file, one JS file, one inline SVG sprite.
* Self-hosted woff2 fonts (latin + latin-ext, which carries the Slovak
  diacritics) with `font-display: swap`.
* Three-width `srcset`/`sizes` for every photo, lazy loading on everything except
  the hero, explicit `width`/`height` to prevent layout shift, and long-lived
  cache headers via `_headers`.

**SEO**

* Slovak `<title>`, meta description, canonical placeholder and Open Graph /
  Twitter tags, all switched client-side when the language changes.
* `<title>` and `og:title` are page-specific (the legal pages use their own, for
  example `Privacy Policy | Marek Cuts`).
* `sitemap.xml`, `robots.txt` and `HairSalon` JSON-LD.
* JSON-LD omits any field that is still a placeholder.

---

## 16. Project structure

```
marek-cuts/
├── build.py                 the Python builder (stdlib only)
├── render.yaml              Render Blueprint
├── README.md
│
├── content/                 ← EDIT: the single source of truth
│   ├── business.json        name, address, phone, email, socials, legal operator
│   ├── services.json        services, demo prices, durations, icons
│   ├── hours.json           displayed opening hours
│   ├── availability.json    demo booking slots
│   ├── testimonials.json    demo reviews (SK + EN)
│   ├── gallery.json         images, alt text, fallback sources
│   ├── i18n.json            every UI string in both languages
│   └── legal/               privacy.json, gdpr.json, cookies.json, terms.json
│
├── templates/
│   ├── index.html           the page shell ({{TOKENS}})
│   ├── legal.html           the legal page shell
│   └── partials/consent.html
│
├── src/
│   ├── styles.css           design system
│   └── js/01-core … 06-consent
│
├── assets-src/
│   └── logo.png             ← REPLACE with your logo
│
└── dist/                    GENERATED — this is what you deploy
    ├── index.html
    ├── styles.css
    ├── script.js
    ├── robots.txt, sitemap.xml, _headers
    ├── legal/{privacy,gdpr,cookies,terms}.html
    └── assets/
        ├── logo.png, logo-sm.png
        ├── fonts/*.woff2
        └── img/*.jpg, favicon.svg, favicon-32.png, apple-touch-icon.png
```

---

## 17. Troubleshooting

**The build stops asking for an RGBA PNG.**
`assets-src/logo.png` must be an 8-bit PNG with a transparent background
(PNG-32). Re-export it from your design tool. This is deliberate: guessing would
produce a logo with a black box around it.

**Photos are missing and the build reports a dead source.**
A remote URL has stopped working. Add another candidate to that entry's
`sources` in `content/gallery.json`, or drop a local file into `assets-src/` and
point `sources` at it. The builder always tries sources in order.

**The site looks unstyled or the fonts fall back.**
Almost always because it was opened as a `file://` path. Serve it:
`python -m http.server 8080 --directory dist`.

**Fonts fell back to Google Fonts.**
The build could not reach `fonts.googleapis.com`, so it emitted a `<link>`
instead of self-hosting. Run `python build.py --refresh` on a machine with
network access to vendor them locally.

**"i18n key missing" or a build failure at validation.**
A template references a `data-i18n` key that is not in `content/i18n.json`, or
the entry is missing one of its `sk`/`en` values. The error names the key and the
file that used it.

**A changed photo or logo did not appear.**
Assets are cached by a stamp of their inputs. `python build.py --refresh` forces a
full re-download; `--clean` also wipes `dist/` and `.cache/`.

**The design's brand colours.**
The palette lives in the `:root` block at the top of `src/styles.css`
(ink/graphite, warm ivory, brushed pewter and a restrained antique-bronze
accent). `INK_PLATE` in `build.py` must match `--ink-900`, because it is the
plate the favicons are composited onto.

---

## Licence and credits

Project code: written for Marek Cuts. Demo photography: Unsplash and Pexels
(see [attributions](#14-image-attributions)). Fonts: Spectral and Inter, both
under the SIL Open Font License. The Marek Cuts logo is the property of its
owner.
