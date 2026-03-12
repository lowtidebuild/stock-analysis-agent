# Color System Reference

This file defines the complete Tailwind CSS color palette and Chart.js color configuration for Mode C dashboard generation.

**Design Philosophy**: Professional, restrained light theme. Company-branded blue as primary color. Green/red only for semantic up/down values. White cards with subtle shadows. No gradients on badges.

---

## Tailwind CSS Classes

### Base Layout
```
Background: bg-gray-50 (page)
Cards: white background, rounded-xl, shadow-sm, hover:shadow-md + hover:translateY(-2px)
Text primary: text-gray-800
Text secondary: text-gray-600
Text muted: text-gray-400 / text-gray-500
Borders: border-gray-200
```

### Primary / Brand
```
Color: blue (company-branded, adjustable per company)
- Text heading: text-gray-900
- Section icon: text-blue-500
- Link/emphasis: text-blue-600
- Badge: bg-blue-50 text-blue-700
- Stat card accent: border-left: 4px solid #3b82f6
- Header gradient: linear-gradient(135deg, #0d1b38 0%, #1e3f80 30%, #2a56b0 60%, #3367d6 100%)
```

### Positive / Bullish
```
Color: green
- Text: text-green-600
- Background (subtle): bg-green-50
- Border accent: border-green-500
- Icon: text-green-600
```

### Negative / Bearish
```
Color: red
- Text: text-red-600
- Background (subtle): bg-red-50
- Border accent: border-red-500
- Icon: text-red-600
```

### Warning / Neutral / Caution
```
Color: yellow/amber (used sparingly)
- Text: text-yellow-600
- Background: bg-yellow-50
- Border: border-yellow-500
```

---

## Card Component

```css
.card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.06);
  transition: transform 0.2s, box-shadow 0.2s;
}
.card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 14px rgba(0,0,0,0.1);
}
.stat-card {
  border-left: 4px solid;
}
```

---

## Data Mode Badges

```html
<!-- Enhanced Mode -->
<span class="bg-green-50 text-green-700 text-xs font-semibold px-2.5 py-1 rounded-full border border-green-200">
  Enhanced Mode
</span>

<!-- Standard Mode (US) -->
<span class="bg-yellow-50 text-yellow-700 text-xs font-semibold px-2.5 py-1 rounded-full border border-yellow-200">
  Standard Mode
</span>

<!-- Korean Stock -->
<span class="bg-blue-50 text-blue-700 text-xs font-semibold px-2.5 py-1 rounded-full border border-blue-200">
  KR DART Mode
</span>
```

---

## R/R Score Badge

```html
<!-- R/R Score > 3 (Attractive) -->
<div class="bg-green-600 text-white text-2xl font-bold px-6 py-3 rounded-xl inline-block">
  R/R Score: {value}
  <div class="text-sm font-normal text-green-100">Attractive</div>
</div>

<!-- R/R Score 1–3 (Neutral) -->
<div class="bg-gray-600 text-white text-2xl font-bold px-6 py-3 rounded-xl inline-block">
  R/R Score: {value}
  <div class="text-sm font-normal text-gray-200">Neutral</div>
</div>

<!-- R/R Score < 1 (Unfavorable) -->
<div class="bg-red-600 text-white text-2xl font-bold px-6 py-3 rounded-xl inline-block">
  R/R Score: {value}
  <div class="text-sm font-normal text-red-100">Unfavorable</div>
</div>
```

---

## Scenario Cards (inside dark header gradient)

```html
<!-- Bull scenario card -->
<div class="bg-white/10 backdrop-blur-sm rounded-xl p-5 text-center border border-green-400/30">
  <p class="text-green-300 text-sm font-semibold mb-1">Bull Case</p>
  <p class="text-3xl font-extrabold text-white">{CURRENCY_SYMBOL}{target}</p>
  <p class="text-green-300 text-sm mt-1">{return_pct}</p>
  <p class="text-blue-200/40 text-xs mt-2">{key_assumption}</p>
</div>

<!-- Base scenario card (emphasized) -->
<div class="bg-white/15 backdrop-blur-sm rounded-xl p-5 text-center border-2 border-blue-300/50 scale-105">
  <p class="text-blue-200 text-sm font-semibold mb-1">Base Case</p>
  <p class="text-4xl font-extrabold text-white">{CURRENCY_SYMBOL}{target}</p>
  <p class="text-green-300 text-sm mt-1">{return_pct}</p>
  <p class="text-blue-200/40 text-xs mt-2">{key_assumption}</p>
</div>

<!-- Bear scenario card -->
<div class="bg-white/10 backdrop-blur-sm rounded-xl p-5 text-center border border-red-400/30">
  <p class="text-red-300 text-sm font-semibold mb-1">Bear Case</p>
  <p class="text-3xl font-extrabold text-white">{CURRENCY_SYMBOL}{target}</p>
  <p class="text-red-300 text-sm mt-1">{return_pct}</p>
  <p class="text-blue-200/40 text-xs mt-2">{key_assumption}</p>
</div>
```

---

## Thesis Cards (light background, inside main content)

```html
<!-- Strengths / Bull Case -->
<div class="card p-6 border-l-4 border-green-500">
  <h3 class="text-lg font-bold text-green-700 mb-3">Strengths / Bull Case</h3>
  <div class="space-y-3 text-sm text-gray-700">
    <div class="bg-green-50 rounded-lg p-3">
      <p class="font-semibold text-green-800 mb-1">Variant View</p>
      <p>{content}</p>
    </div>
  </div>
</div>

<!-- Risks / Bear Case -->
<div class="card p-6 border-l-4 border-red-500">
  <h3 class="text-lg font-bold text-red-700 mb-3">Risks / Bear Case</h3>
  <div class="space-y-3 text-sm text-gray-700">
    <div class="bg-red-50 rounded-lg p-3">
      <p class="font-semibold text-red-800 mb-1">Key Risk</p>
      <p>{content}</p>
    </div>
  </div>
</div>
```

---

## Verdict Badge

```html
<!-- Overweight / 비중확대 / Buy -->
<span class="bg-green-50 text-green-700 font-bold px-4 py-1.5 rounded-lg border border-green-200">Overweight</span>

<!-- Neutral / 중립 / Hold -->
<span class="bg-gray-100 text-gray-700 font-bold px-4 py-1.5 rounded-lg border border-gray-200">Neutral</span>

<!-- Underweight / 비중축소 / Sell -->
<span class="bg-red-50 text-red-700 font-bold px-4 py-1.5 rounded-lg border border-red-200">Underweight</span>
```

---

## Source Tag Styles (inline in text)

All source tags use the same muted style — differentiated by text color only:

```html
<code class="bg-gray-100 text-blue-600 text-xs px-1.5 py-0.5 rounded">[API]</code>
<code class="bg-gray-100 text-green-600 text-xs px-1.5 py-0.5 rounded">[Calculated]</code>
<code class="bg-gray-100 text-gray-600 text-xs px-1.5 py-0.5 rounded">[Web]</code>
<code class="bg-gray-100 text-yellow-600 text-xs px-1.5 py-0.5 rounded">[1S]</code>
<code class="bg-gray-100 text-red-500 text-xs px-1.5 py-0.5 rounded">[Unverified]</code>
<code class="bg-gray-100 text-purple-600 text-xs px-1.5 py-0.5 rounded">[DART]</code>
<code class="bg-gray-100 text-blue-500 text-xs px-1.5 py-0.5 rounded">[네이버]</code>
<code class="bg-gray-100 text-gray-500 text-xs px-1.5 py-0.5 rounded">[KR-Web]</code>
```

---

## Chart.js Color Configuration

### Price Chart (Line)
```javascript
priceChart: {
  borderColor: '#3b82f6',                    // blue-500
  backgroundColor: 'rgba(59,130,246,0.06)',
  borderWidth: 2.5,
  pointRadius: 4,
  pointBackgroundColor: '#3b82f6',
  fill: true,
  tension: 0.3
}
```

### Revenue Bar Chart
```javascript
revenueBar: {
  backgroundColor: 'rgba(59,130,246,0.55)',  // blue-500
  borderColor: 'rgba(59,130,246,1)',
  borderWidth: 1,
  borderRadius: 6
}
operatingIncomeLine: {
  type: 'line',
  borderColor: 'rgba(52,168,83,1)',          // green
  backgroundColor: 'rgba(52,168,83,0.1)',
  borderWidth: 2.5,
  pointRadius: 5,
  pointBackgroundColor: 'rgba(52,168,83,1)',
  fill: false
}
```

### Margin Trend Chart (Multi-line)
```javascript
grossMarginLine: {
  borderColor: '#10b981',   // green
  borderWidth: 2,
  pointRadius: 3,
  tension: 0.3
}
operatingMarginLine: {
  borderColor: '#3b82f6',   // blue
  borderWidth: 2,
  pointRadius: 3,
  tension: 0.3
}
netMarginLine: {
  borderColor: '#6b7280',   // gray-500
  borderWidth: 2,
  pointRadius: 3,
  tension: 0.3
}
```

### Segment / Peer Bar
```javascript
segmentBar: {
  backgroundColor: [
    'rgba(59,130,246,0.7)',    // blue
    'rgba(52,168,83,0.7)',     // green
    'rgba(251,188,5,0.7)',     // yellow (sparingly)
    'rgba(59,130,246,0.35)',   // blue-light
    'rgba(107,114,128,0.5)'   // gray
  ],
  borderWidth: 1,
  borderRadius: 6
}
```

---

## Global Chart.js Options (Light Theme)

```javascript
const globalChartOptions = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: {
    legend: {
      position: 'bottom',
      labels: { color: '#4b5563', font: { size: 11 }, usePointStyle: true }
    },
    tooltip: {
      backgroundColor: '#1f2937',
      titleColor: '#f9fafb',
      bodyColor: '#d1d5db',
      borderColor: '#374151',
      borderWidth: 1
    }
  },
  scales: {
    x: {
      grid: { display: false },
      ticks: { color: '#6b7280', font: { size: 10 } }
    },
    y: {
      grid: { color: 'rgba(0,0,0,0.05)' },
      ticks: { color: '#6b7280', font: { size: 10 } }
    }
  }
};
```

---

## Typography & Font

For all outputs (EN and KR), use Inter as primary:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap" rel="stylesheet">
```

For Korean output, add Noto Sans KR as fallback:
```html
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&family=Noto+Sans+KR:wght@300;400;500;700&display=swap" rel="stylesheet">
```

Apply:
```css
* { font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Noto Sans KR', sans-serif; }
```

---

## Scrollbar Styling

```css
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
```
